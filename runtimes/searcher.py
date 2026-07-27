"""🔍 Searcher v4 — 生产级搜索信息整理

设计原则（codebase-design）：
- 深模块：复杂内部实现，简单外部接口
- 小接口：只有 init(config) 和 execute(query)

生产级特性（匹配 KnowledgeBot v4）：
- logging / trace / metrics / circuit_breaker / cost tracking
- 统一 LLM 工厂（core.llm_factory，Mock/Real 自动切换）
- httpx 客户端（替代 requests，统一 HTTP 栈）
- 统一的返回契约（与 KnowledgeBot 一致的 result dict 结构）
"""

import urllib.parse

import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

from .base_runtime import BaseRuntime
from core.llm_factory import get_llm, estimate_tokens, truncate
from memory.prompts import SEARCH_SYSTEM_PROMPT
from toolkit.cache import cache_get, cache_set
from toolkit.registry import register

# ── 基础设施 ──
from infrastructure.logging import setup_logger as _setup_logger
from infrastructure.circuit_breaker import CircuitBreaker
from infrastructure.cost_tracker import CostTracker
from core.trace import TraceRecorder
from orchestration.assessors import CLEARScorer

console = Console()

ENGINE_NAMES = {"baidu": "百度 AI 搜索", "duckduckgo": "DuckDuckGo"}


# ── 搜索引擎（内部函数） ──

def _search_ddg(query: str, max_results: int = 5) -> list[dict]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
    resp = httpx.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for i, div in enumerate(soup.select(".result"), 1):
        if len(results) >= max_results: break
        tag = div.select_one(".result__title a")
        if not tag: continue
        href = tag.get("href", "")
        url = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)["uddg"][0] if "uddg=" in href else href
        snip = div.select_one(".result__snippet")
        results.append({"id": i, "title": tag.get_text(strip=True), "url": url,
                        "snippet": snip.get_text(strip=True) if snip else "(无摘要)"})
    return results


def _search_baidu(query: str, max_results: int = 5, api_key: str = "", recency: str = "year") -> list[dict]:
    if not api_key:
        raise ValueError("使用百度搜索需配置 BAIDU_API_KEY 环境变量或 config.yaml 的 baidu_api_key")
    payload = {"messages": [{"content": query, "role": "user"}], "search_source": "baidu_search_v2",
               "resource_type_filter": [{"type": "web", "top_k": max_results}]}
    if recency: payload["search_recency_filter"] = recency
    resp = httpx.post("https://qianfan.baidubce.com/v2/ai_search/web_search",
        json=payload, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, timeout=20)
    resp.raise_for_status()
    refs = resp.json().get("references", [])
    return [{"id": i, "title": r.get("title", "(无标题)"), "url": r.get("url", ""),
             "snippet": r.get("content", "(无内容)")} for i, r in enumerate(refs, 1) if i <= max_results]


# ── 注册为工具 ──
register(
    name="web_search",
    description="在互联网上搜索信息。支持百度（默认）和 DuckDuckGo 两种搜索引擎。",
    fn=lambda query, engine="baidu", max_results=5, api_key="", recency="year":
        _search_baidu(query, max_results, api_key, recency) if engine == "baidu" else _search_ddg(query, max_results),
    parameters={"query": {"type": "string", "description": "搜索关键词"},
                "engine": {"type": "string", "description": "搜索引擎: baidu / duckduckgo"},
                "max_results": {"type": "integer", "description": "返回结果数 (3-20)"}},
)


class Searcher(BaseRuntime):
    """生产级搜索信息整理 Agent

    浅接口：init(config) / execute(query)
    深内部：logging · trace · metrics · circuit breaker · cost tracking · 文件缓存
    """

    def __init__(self):
        self._llm_client = None
        self._llm_config = {}
        self._config: dict = {}
        # 基础设施
        self._log = _setup_logger("search")
        self._cb = CircuitBreaker("search_api", failure_threshold=3, recovery_timeout=30)
        self._trace: TraceRecorder | None = None
        self._metrics = CLEARScorer("search")
        self._costs = CostTracker()
        self._history: list[dict] = []

    @property
    def name(self) -> str: return "search"

    @property
    def description(self) -> str:
        return "🔍 搜索网页并整理信息 —— 百度/DuckDuckGo · 文件缓存 · AI 摘要 · 链路追踪"

    def init(self, config: dict) -> None:
        self._log.info("Searcher 初始化")
        self._config = config
        # 统一 LLM 工厂（Mock 模式离线可用）
        self._llm_client = get_llm()
        self._llm_config = {"model": config.get("llm", {}).get("model", "deepseek-v4-flash")}
        self._trace = TraceRecorder("search")
        self._log.info("LLM 客户端就绪（统一工厂）")

    def execute(self, query: str = "", max_results: int = 5,
                engine: str = "", recency: str = "", **kwargs) -> dict:
        from time import time as _now
        t0 = _now()
        self._log.info(f"Query: {query[:80]}")
        if self._trace:
            self._trace.record("user_input", {"query": query[:100], "engine": engine or "baidu"})

        if not query:
            return {"error": "请提供搜索关键词"}

        used_engine = engine or "baidu"
        label = ENGINE_NAMES.get(used_engine, used_engine)

        try:
            # ── 1. 缓存查询 ──
            cached = cache_get(used_engine, query)
            from_cache = cached is not None

            if cached is not None:
                results = cached
                self._log.debug(f"缓存命中: {query}")
            else:
                self._log.debug(f"搜索: {query} via {label}")
                if used_engine == "baidu":
                    api_key = kwargs.get("baidu_api_key") or self._config.get("baidu_api_key", "")
                    results = _search_baidu(query, max_results, api_key, recency)
                else:
                    results = _search_ddg(query, max_results)
                cache_set(used_engine, query, results)

            output = {"query": query, "results": results, "total": len(results),
                      "engine": used_engine, "cached": from_cache}

            # ── 2. 展示 ──
            table = Table(title=f"[bold]搜索结果 ({label}) — {query}[/]", box=box.ROUNDED, title_justify="left")
            table.add_column("#", style="dim", width=3)
            table.add_column("标题", style="cyan")
            table.add_column("摘要", style="white")
            table.add_column("链接", style="blue")
            for r in results:
                table.add_row(str(r["id"]), truncate(r["title"], 50),
                              truncate(r["snippet"], 80),
                              truncate(r["url"], 40))
            console.print(table)
            if from_cache: console.print("[dim]⚡ 以上结果来自文件缓存[/]")

            # ── 3. AI 摘要 ──
            if self._llm_client and results:
                console.print("\n[bold green]🤖 正在生成 AI 摘要...[/]")
                summary = self._summarize(query, results)
                if summary:
                    console.print(Panel(Markdown(summary), title="📝 AI 整理摘要", border_style="green", padding=(1, 2)))
                    output["summary"] = summary

            # ── 4. 记录 ──
            elapsed = _now() - t0
            if self._metrics:
                self._metrics.record(success=True, latency_s=elapsed, query=query)
            if self._trace:
                self._trace.record("completed", {"latency_s": round(elapsed, 2), "total": len(results)})
                self._trace.save()
            self._log.info(f"完成: {len(results)} 条, {elapsed:.1f}s")
            return output

        except Exception as e:
            self._log.error(f"搜索失败: {e}")
            if self._metrics:
                self._metrics.record(success=False, latency_s=_now() - t0, query=query, error=str(e))
            return {"error": f"搜索失败: {e}"}

    def _summarize(self, query: str, results: list) -> str:
        try:
            context = "\n\n".join(f"来源 {r['id']}: {r['title']}\n{r['snippet']}" for r in results)
            answer = self._llm_client.chat(
                [{"role": "system", "content": SEARCH_SYSTEM_PROMPT},
                 {"role": "user", "content": f"搜索关键词：{query}\n\n搜索结果：\n{context}"}],
                temperature=0.3, max_tokens=1000,
            )
            if self._costs:
                self._costs.record(self._llm_config.get("model", "deepseek-v4-flash"),
                                   estimate_tokens(context), estimate_tokens(answer))
            return answer
        except Exception as e:
            return f"⚠️ AI 摘要生成失败：{e}"
