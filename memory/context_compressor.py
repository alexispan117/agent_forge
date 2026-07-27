"""AgentForge — 上下文压缩

当 Token 接近窗口上限时，压缩历史对话。
参考 MokioClaw 的 context_compressor 机制。
"""

import json
from pathlib import Path

COMPRESS_DIR = Path.home() / ".cache" / "agentforge" / "compressed"


class ContextCompressor:
    """上下文压缩器

    策略：
    1. 对话历史 → 摘要
    2. 工具调用 → 结果摘要
    3. Notepad 和 Todo 保留
    """

    def __init__(self, session_id: str = "default"):
        self._fp = COMPRESS_DIR / f"{session_id}.json"
        self._fp.parent.mkdir(parents=True, exist_ok=True)
        self._history: list[dict] = []
        self._compression_count = 0

    def estimate_tokens(self, messages: list[dict]) -> int:
        """粗略估算 Token 数（按 1 汉字 ≈ 2 token，1 英文词 ≈ 1.3 token）"""
        total = 0
        for msg in messages:
            text = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            for char in text:
                if "\u4e00" <= char <= "\u9fff":
                    total += 2
                elif char.isalpha():
                    continue
            # 英文词
            for word in text.split():
                if word.isascii() and word.isalpha():
                    total += 1.3
            total += len(text) // 4  # 标点/空格
        return int(total)

    def should_compress(self, messages: list[dict], limit: int = 40000) -> bool:
        """判断是否需要压缩"""
        return self.estimate_tokens(messages) > limit

    def compress(self, messages: list[dict], llm_client=None) -> list[dict]:
        """压缩对话历史

        保留最近 4 条完整消息，之前的压缩为摘要。

        Args:
            messages: 原始消息列表
            llm_client: LLM 客户端（用于生成摘要）

        Returns:
            压缩后的消息列表
        """
        if len(messages) <= 8:
            return messages

        # 保留最近 4 条
        keep = messages[-4:]
        compress = messages[:-4]

        # 生成摘要
        summary = self._summarize(compress, llm_client)
        self._compression_count += 1

        compressed = [
            {"role": "system", "content": f"[上下文压缩 #{self._compression_count}]\n{summary}"},
        ] + keep

        # 保存
        self._history.append({
            "compression": self._compression_count,
            "original_count": len(messages),
            "compressed_count": len(compressed),
            "summary": summary,
        })
        self._save()

        return compressed

    def _summarize(self, messages: list[dict], llm_client=None) -> str:
        """生成对话摘要"""
        if not messages:
            return "(空对话)"

        if not llm_client:
            # 无 LLM 时简单截取
            text = "\n".join(
                f"{'用户' if m['role'] == 'user' else '助手'}: {m.get('content', '')[:100]}"
                for m in messages
            )
            return f"对话摘要（共 {len(messages)} 条消息）:\n{text[:500]}"

        try:
            text = "\n".join(m.get("content", "")[:200] for m in messages if m.get("content"))
            # llm_client 为 core.llm_factory 的 LLMFacade（Mock/Real 统一接口）
            return llm_client.chat(
                [
                    {"role": "system", "content": "将以下对话压缩为摘要，保留关键信息和决策。"},
                    {"role": "user", "content": text},
                ],
                temperature=0.2,
                max_tokens=300,
            )
        except Exception:
            return f"(对话摘要: {len(messages)} 条消息)"

    def summary(self) -> dict:
        return {
            "compression_count": self._compression_count,
            "history": self._history[-5:],
        }

    def _save(self):
        self._fp.write_text(json.dumps({
            "compression_count": self._compression_count,
            "history": self._history[-10:],
        }, ensure_ascii=False))
