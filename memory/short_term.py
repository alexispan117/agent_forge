"""AgentForge — ShortTermMemory 类

替代 rag_agent.py 中原始的 list[dict] 模式，
消除 Primitive Obsession 气味。
"""

from typing import Optional


class ShortTermMemory:
    """对话历史管理

    封装 append、压缩、窗口切片等操作，统一接口。
    """

    def __init__(self, max_window: int = 20):
        self._messages: list[dict] = []
        self._max_window = max_window

    @property
    def messages(self) -> list[dict]:
        return self._messages

    @property
    def count(self) -> int:
        return len(self._messages)

    def add_user(self, content: str):
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        self._messages.append({"role": "assistant", "content": content})

    def last_n(self, n: int = 10) -> list[dict]:
        return self._messages[-n:]

    def summary(self, max_len: int = 200) -> str:
        """生成对话摘要（用于注入 Prompt）"""
        lines = []
        for m in self._messages[-self._max_window:]:
            role = "用户" if m["role"] == "user" else "助手"
            text = (m.get("content", "") or "")[:max_len]
            lines.append(f"{role}: {text}")
        return "\n".join(lines)

    def compress(self, compressor) -> bool:
        """调用上下文压缩器，返回是否触发了压缩"""
        if not compressor:
            return False
        if compressor.should_compress(self._messages):
            self._messages = compressor.compress(self._messages)
            return True
        return False

    def clear(self):
        self._messages.clear()

    def restore(self, messages: list[dict]):
        self._messages = list(messages)

    def __len__(self):
        return len(self._messages)

    def __getitem__(self, idx):
        return self._messages[idx]
