"""AgentForge — 情景记忆（跨会话长期记忆）

v2 升级点：
1. 存储路径从 ~/.cache 迁移到项目 data/memory/（容器卷内可持久化）
2. 新增 query(text)：关键词重叠检索，供 Worker「记忆唤醒」调用
3. 新增 load_seed()：支持 data/demo/seed_memory.json 的 sessions 结构，首启自动加载
4. 全文件读写显式 utf-8（修复 Windows 下 GBK 解码崩溃）
"""
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

# 项目内持久化目录（随 ./data 卷挂载，容器重建不丢）
MEMORY_DIR = Path(__file__).parent.parent / "data" / "memory"
DEFAULT_SEED = Path(__file__).parent.parent / "data" / "demo" / "seed_memory.json"


class EpisodicMemory:
    """情景记忆

    存储格式：
    {
        "preferences": { ... },
        "facts": [{"key": "...", "value": "...", "importance": 0.9, "ts": ...}, ...],
        "history": [{"query": "...", "answer": "...", "success": true, "ts": ...}, ...]
    }
    """

    def __init__(self, user_id: str = "default", seed_path: Optional[str | Path] = None):
        self.user_id = user_id
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._fp = MEMORY_DIR / f"{user_id}.json"
        self._data: dict = self._load()
        # 首次使用且记忆为空时，自动加载种子数据（演示「记忆唤醒」）
        if not self._data.get("facts") and not self._data.get("history"):
            seed = seed_path or os.environ.get("DEMO_SEED_MEMORY") or DEFAULT_SEED
            if seed and Path(seed).exists():
                self.load_seed(seed)

    # ── 写入 ──

    def remember(self, key: str, value: Any, importance: float = 0.5) -> None:
        """记住一个事实（key 已存在则按 importance 更新）。"""
        facts = self._data.setdefault("facts", [])
        for f in facts:
            if f["key"] == key:
                f["value"] = value
                f["importance"] = importance
                f["ts"] = time.time()
                self._save()
                return
        facts.append({"key": key, "value": value, "importance": importance, "ts": time.time()})
        self._save()

    def set_preference(self, key: str, value: Any) -> None:
        self._data.setdefault("preferences", {})[key] = value
        self._save()

    def add_history(self, query: str, answer: str, success: bool = True) -> None:
        """追加一条会话历史（保留最近 100 条）。"""
        history = self._data.setdefault("history", [])
        history.append({
            "query": query[:200],
            "answer": answer[:500],
            "success": success,
            "ts": time.time(),
        })
        if len(history) > 100:
            self._data["history"] = history[-100:]
        self._save()

    # ── 读取 ──

    def recall(self, key: str) -> Any | None:
        for f in self._data.get("facts", []):
            if f["key"] == key:
                return f["value"]
        return None

    def recall_all(self, min_importance: float = 0.0) -> dict:
        return {
            f["key"]: f["value"]
            for f in self._data.get("facts", [])
            if f["importance"] >= min_importance
        }

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._data.get("preferences", {}).get(key, default)

    def get_recent_history(self, n: int = 10) -> list[dict]:
        return self._data.get("history", [])[-n:]

    def query(self, text: str, top_k: int = 3) -> str:
        """关键词重叠检索：在 facts 与 history 中找与 text 相关的记忆。

        Returns:
            拼接的记忆文本块；无命中返回空字符串。
        """
        terms = self._terms(text)
        if not terms:
            return ""

        scored: list[tuple[float, str]] = []
        for f in self._data.get("facts", []):
            hay = f"{f['key']} {f['value']}".lower()
            score = self._overlap(terms, hay) * (0.5 + f.get("importance", 0.5))
            if score > 0:
                scored.append((score, f"事实 {f['key']}: {f['value']}"))
        for h in self._data.get("history", []):
            hay = f"{h.get('query', '')} {h.get('answer', '')}".lower()
            score = self._overlap(terms, hay)
            if score > 0:
                scored.append((score, f"历史问: {h.get('query', '')[:80]} → 答: {h.get('answer', '')[:120]}"))

        scored.sort(key=lambda x: -x[0])
        return "\n".join(line for _, line in scored[:top_k])

    def context_blob(self) -> str:
        """生成上下文文本块（供 Prompt 注入）。"""
        parts = []
        prefs = self._data.get("preferences", {})
        if prefs:
            parts.append("## 用户偏好\n" + "\n".join(f"- {k}: {v}" for k, v in prefs.items()))
        facts = self._data.get("facts", [])
        important = [f for f in facts if f["importance"] >= 0.7]
        if important:
            parts.append("## 已知事实\n" + "\n".join(f"- {f['key']}: {f['value']}" for f in important))
        return "\n\n".join(parts) if parts else "(无长期记忆)"

    # ── 种子加载 ──

    def load_seed(self, path: str | Path) -> int:
        """加载种子记忆（支持 data/demo/seed_memory.json 的 sessions 结构）。

        Returns:
            写入的事实条数。
        """
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            return 0

        count = 0
        sessions = data.get("sessions", []) if isinstance(data, dict) else []
        for s in sessions:
            summary = s.get("summary", "")
            if summary:
                project = s.get("project", "历史项目")
                self.remember(f"seed:{s.get('session_id', count)}", f"[{project}] {summary}",
                              importance=0.8)
                count += 1
            for i, decision in enumerate(s.get("key_decisions", [])):
                self.remember(f"seed:decision:{count}:{i}", decision, importance=0.7)
                count += 1
        return count

    # ── 维护 ──

    def clear(self) -> None:
        self._data = {}
        self._save()

    @staticmethod
    def _terms(text: str) -> set[str]:
        """提取检索词：连续中文 2-3 字滑窗 + 英文单词。"""
        terms: set[str] = set()
        for seq in re.findall(r"[\u4e00-\u9fff]+", text.lower()):
            if len(seq) >= 3:
                for wlen in (2, 3):
                    for i in range(len(seq) - wlen + 1):
                        terms.add(seq[i:i + wlen])
            elif len(seq) == 2:
                terms.add(seq)
        terms.update(re.findall(r"[a-z]{3,}", text.lower()))
        return terms

    @staticmethod
    def _overlap(terms: set[str], haystack: str) -> float:
        return sum(1.0 for t in terms if t in haystack)

    def _load(self) -> dict:
        if self._fp.exists():
            try:
                return json.loads(self._fp.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"facts": [], "preferences": {}, "history": []}

    def _save(self) -> None:
        self._fp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
