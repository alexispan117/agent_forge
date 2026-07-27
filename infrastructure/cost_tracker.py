"""AgentForge — Token 成本追踪

根据模型用量估算成本。
"""

import json
import time
from pathlib import Path

COST_DIR = Path.home() / ".cache" / "agentforge" / "costs"

# 各模型每百万 Token 的价格（美元）
MODEL_PRICES = {
    "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
    "deepseek-v4-pro": {"input": 0.55, "output": 2.19},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "text-embedding-v3": {"input": 0.13, "output": 0.13},
    "text-embedding-3-small": {"input": 0.02, "output": 0.02},
}


class CostTracker:
    """Token 成本追踪

    记录每次 LLM 调用的 Token 消耗并估算成本。
    """

    def __init__(self):
        self._session_costs: list[dict] = []
        self._start = time.time()

    def record(self, model: str, input_tokens: int, output_tokens: int) -> dict:
        """记录一次 LLM 调用

        Args:
            model: 模型名称
            input_tokens: 输入 Token 数
            output_tokens: 输出 Token 数

        Returns:
            {"input_tokens", "output_tokens", "cost", "model"}
        """
        prices = MODEL_PRICES.get(model, {"input": 0.50, "output": 1.50})
        cost = (input_tokens / 1_000_000 * prices["input"] +
                output_tokens / 1_000_000 * prices["output"])

        entry = {
            "ts": time.time(),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": round(cost, 8),
        }
        self._session_costs.append(entry)
        return entry

    def session_summary(self) -> dict:
        """当前会话的成本汇总"""
        total_tokens = sum(e["input_tokens"] + e["output_tokens"] for e in self._session_costs)
        total_cost = sum(e["cost"] for e in self._session_costs)
        return {
            "calls": len(self._session_costs),
            "total_tokens": total_tokens,
            "input_tokens": sum(e["input_tokens"] for e in self._session_costs),
            "output_tokens": sum(e["output_tokens"] for e in self._session_costs),
            "total_cost_usd": round(total_cost, 6),
        }

    def save_session(self, session_id: str):
        """将会话成本保存到文件"""
        fp = COST_DIR / f"{session_id}.json"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps({
            "session_id": session_id,
            "duration_s": round(time.time() - self._start, 2),
            **self.session_summary(),
            "entries": self._session_costs,
        }, ensure_ascii=False))
