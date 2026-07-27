"""
core/llm_factory.py — 统一 LLM 工厂（异步优先）

设计要点：
1. 全面 async：MockLLM 用 asyncio.sleep（不阻塞事件循环），RealLLM 用 AsyncOpenAI
2. 指数退避 + 抖动 + 真超时（asyncio.wait_for），仅对可重试异常重试
3. Mock embedding 确定性输出（同一文本恒得同一向量，检索演示可复现）
4. LLMFacade 提供 chat() 同步兼容包装，供未迁移的旧调用方平滑过渡
5. 通用工具 estimate_tokens / truncate 自根目录 llm.py 迁入（单一数据源）
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Protocol, TypeVar, runtime_checkable

logger = logging.getLogger("llm_factory")

MOCK_DIR = Path(__file__).parent / "mock_responses"
DEFAULT_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "30"))
MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "2"))

T = TypeVar("T")


# ═══════════════════════════════════════════════
# 统一异步接口
# ═══════════════════════════════════════════════

@runtime_checkable
class AsyncLLMClient(Protocol):
    """所有上层（Supervisor / Worker / Runtime）只依赖此协议。"""

    async def achat(self, messages: list[dict], **kwargs: Any) -> str: ...
    async def achat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs: Any) -> dict: ...
    async def aembed(self, text: str) -> list[float]: ...


# ═══════════════════════════════════════════════
# 通用重试：指数退避 + 抖动 + 超时
# ═══════════════════════════════════════════════

_BASE_RETRYABLE: tuple[type[Exception], ...] = (asyncio.TimeoutError, ConnectionError, OSError)


async def _with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    retries: int = MAX_RETRIES,
    base_delay: float = 0.5,
    retryable: tuple[type[Exception], ...] = _BASE_RETRYABLE,
) -> T:
    """对可重试异常执行指数退避重试；不可重试异常立即抛出。"""
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=DEFAULT_TIMEOUT_S)
        except retryable as e:
            last_exc = e
            if attempt < retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.3)
                logger.warning(f"LLM 调用失败（第 {attempt + 1}/{retries + 1} 次），{delay:.1f}s 后重试: {e}")
                await asyncio.sleep(delay)
    raise RuntimeError(f"LLM 调用在 {retries + 1} 次尝试后仍失败: {last_exc}") from last_exc


# ═══════════════════════════════════════════════
# MockLLM — 离线演示：零网络、非阻塞、确定性
# ═══════════════════════════════════════════════

class MockLLM:
    """模拟 LLM：零网络请求，毫秒级响应。"""

    async def achat(self, messages: list[dict], **kwargs: Any) -> str:
        content = self._last_user_message(messages)
        intent = self._detect_intent(content)
        responses = self._load_responses(intent)
        chosen = random.choice(responses) if responses else self._load_responses("fallback")[0]

        result: str = chosen["response"]
        if "{input}" in result:
            result = result.replace("{input}", content[:50])
        await asyncio.sleep(chosen.get("delay_s", 0.3))  # 非阻塞模拟延迟
        return result

    async def achat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs: Any) -> dict:
        intent = self._detect_intent(self._last_user_message(messages))
        responses = self._load_responses(intent + "_tools") or self._load_responses("fallback_tools")
        await asyncio.sleep(0.1)
        if responses:
            return random.choice(responses)
        return {
            "tool_calls": [{"name": "list_dir", "args": {"path": "."}}],
            "content": "使用工具 list_dir 列出目录...",
        }

    async def aembed(self, text: str) -> list[float]:
        """确定性 Mock 向量：以文本哈希为随机种子，同文本恒得同向量。"""
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.random() for _ in range(768)]

    # ── 私有方法 ──

    @staticmethod
    def _last_user_message(messages: list[dict]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                return m.get("content", "")
        return ""

    @staticmethod
    def _detect_intent(content: str) -> str:
        keywords = {
            "decompose": ["拆解", "分解", "分析", "评估", "审计", "审", "合规", "目标", "任务"],
            "anomaly": ["异常", "风险", "警告", "违规", "超标", "超过", "大于", "小于"],
            "desensitize": ["脱敏", "隐藏", "加密", "保护", "隐私", "身份证", "银行", "手机号"],
            "report": ["报告", "总结", "汇总", "输出", "生成"],
            "approve": ["审批", "批准", "同意", "拒绝", "驳回"],
            "memory": ["记忆", "历史", "之前", "上次", "以前", "上下文"],
        }
        for intent, kws in keywords.items():
            if any(kw in content for kw in kws):
                return intent
        return "general"

    @staticmethod
    def _load_responses(intent: str) -> list[dict]:
        fp = MOCK_DIR / f"{intent}.json"
        if fp.exists():
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else data.get("responses", [])
        return []


# ═══════════════════════════════════════════════
# RealLLM — OpenAI 兼容异步客户端（DeepSeek 默认）
# ═══════════════════════════════════════════════

class RealLLM:
    """真实 LLM：AsyncOpenAI，内置超时与退避重试。"""

    def __init__(self) -> None:
        from openai import AsyncOpenAI
        import yaml

        cfg_path = Path(__file__).parent.parent / "config.yaml"
        llm_cfg: dict = {}
        if cfg_path.exists():
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            llm_cfg = raw.get("llm", {})

        api_key = os.environ.get("LLM_API_KEY") or llm_cfg.get("api_key")
        if not api_key:
            raise RuntimeError("LLM_API_KEY 未配置（Mock 模式请设 LLM_MOCK_MODE=true）")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=os.environ.get("LLM_BASE_URL") or llm_cfg.get("base_url", "https://api.deepseek.com"),
            timeout=DEFAULT_TIMEOUT_S,
        )
        self.model = os.environ.get("LLM_MODEL") or llm_cfg.get("model", "deepseek-v4-flash")

        # openai 的 APIError 纳入可重试集合（延迟导入，避免 Mock 模式强依赖）
        from openai import APIError
        self._retryable: tuple[type[Exception], ...] = _BASE_RETRYABLE + (APIError,)

    async def achat(self, messages: list[dict], **kwargs: Any) -> str:
        async def _call() -> str:
            resp = await self.client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=messages,
                temperature=kwargs.get("temperature", 0.1),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
            return resp.choices[0].message.content or ""

        try:
            return await _with_retry(_call, retryable=self._retryable)
        except Exception as e:
            logger.error(f"RealLLM.achat 最终失败: {e}")
            raise

    async def achat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs: Any) -> dict:
        async def _call() -> dict:
            resp = await self.client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=messages,
                tools=tools,
                temperature=0.1,
            )
            msg = resp.choices[0].message
            return {
                "tool_calls": [
                    {"name": t.function.name, "args": json.loads(t.function.arguments)}
                    for t in (msg.tool_calls or [])
                ],
                "content": msg.content or "",
            }

        return await _with_retry(_call, retryable=self._retryable)

    async def aembed(self, text: str) -> list[float]:
        async def _call() -> list[float]:
            resp = await self.client.embeddings.create(model="text-embedding-v3", input=text)
            return list(resp.data[0].embedding)

        return await _with_retry(_call, retryable=self._retryable)


# ═══════════════════════════════════════════════
# 门面：异步优先 + 同步兼容（供旧调用方过渡）
# ═══════════════════════════════════════════════

def _run_sync(coro: Awaitable[T]) -> T:
    """仅允许在没有运行中事件循环的上下文（CLI / 工作线程 / 线程池）使用。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("检测到运行中的事件循环：请改用 await achat()/achat_with_tools()/aembed()")


class LLMFacade:
    """统一门面：新代码用 achat*，旧代码可暂时用 chat*（逐步迁移）。"""

    def __init__(self, impl: AsyncLLMClient) -> None:
        self._impl = impl

    async def achat(self, messages: list[dict], **kwargs: Any) -> str:
        return await self._impl.achat(messages, **kwargs)

    async def achat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs: Any) -> dict:
        return await self._impl.achat_with_tools(messages, tools, **kwargs)

    async def aembed(self, text: str) -> list[float]:
        return await self._impl.aembed(text)

    # ── 同步兼容层（旧接口签名不变；仅限无事件循环的上下文）──
    def chat(self, messages: list, **kwargs: Any) -> str:
        return _run_sync(self.achat(messages, **kwargs))

    def chat_with_tools(self, messages: list, tools: list, **kwargs: Any) -> dict:
        return _run_sync(self.achat_with_tools(messages, tools, **kwargs))

    def generate_embedding(self, text: str) -> list[float]:
        return _run_sync(self.aembed(text))


# ═══════════════════════════════════════════════
# 通用工具（自根目录 llm.py 迁入）
# ═══════════════════════════════════════════════

def estimate_tokens(text: str) -> int:
    """估算 Token 数（中文约 2 token/字，英文约 1.3 token/词）。"""
    total = sum(2 for c in text if "\u4e00" <= c <= "\u9fff")
    total += sum(1.3 for w in text.split() if w.isascii() and w.isalpha())
    total += len(text) // 4
    return int(total)


def truncate(text: str, max_len: int = 50, suffix: str = "…") -> str:
    """裁剪文本到指定长度。"""
    return text[:max_len] + suffix if len(text) > max_len else text


# ═══════════════════════════════════════════════
# 工厂
# ═══════════════════════════════════════════════

_instance: Optional[LLMFacade] = None


def get_llm() -> LLMFacade:
    """统一工厂：LLM_MOCK_MODE=true（默认）返回 Mock，否则返回 Real。"""
    global _instance
    if _instance is None:
        mock = os.environ.get("LLM_MOCK_MODE", "true").lower() in ("true", "1", "yes")
        _instance = LLMFacade(MockLLM() if mock else RealLLM())
        logger.info(f"LLM 工厂初始化: {'MockLLM' if mock else 'RealLLM'}")
    return _instance


def reset_llm() -> None:
    """重置工厂单例（测试用）。"""
    global _instance
    _instance = None


if __name__ == "__main__":
    # 离线自测：python core/llm_factory.py
    async def _selftest() -> None:
        llm = get_llm()
        answer = await llm.achat([{"role": "user", "content": "请拆解这份合同审计任务"}])
        print(f"[achat] {answer[:80]}")
        v1 = await llm.aembed("合同条款")
        v2 = await llm.aembed("合同条款")
        assert v1 == v2, "embedding 必须是确定性的"
        print(f"[aembed] 维度={len(v1)}，确定性校验通过")
        t0 = time.time()
        await asyncio.gather(*(llm.achat([{"role": "user", "content": "生成报告"}]) for _ in range(5)))
        print(f"[并发] 5 路并发耗时 {time.time() - t0:.2f}s（非阻塞验证）")

    asyncio.run(_selftest())
