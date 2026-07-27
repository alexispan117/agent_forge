"""AgentForge — Agent 评估指标追踪器

记录每次 Agent 执行的成功率、准确率、延迟、Token 成本。
"""

import json
import time
from pathlib import Path

METRICS_DIR = Path.home() / ".cache" / "agentforge" / "metrics"


class CLEARScorer:
    """Agent 执行指标追踪"""

    def __init__(self, agent_name: str = "default"):
        self.agent = agent_name
        self._fp = METRICS_DIR / f"{agent_name}.jsonl"
        self._fp.parent.mkdir(parents=True, exist_ok=True)

    def record(self, success: bool, latency_s: float, token_cost: float = 0,
               tool_accuracy: float = 1.0, hallucination: bool = False,
               query: str = "", error: str = ""):
        """记录一次执行

        Args:
            success: 是否成功完成
            latency_s: 延迟（秒）
            token_cost: Token 成本（美元）
            tool_accuracy: 工具调用准确率 (0-1)
            hallucination: 是否产生幻觉
            query: 用户问题
            error: 错误信息
        """
        entry = {
            "ts": time.time(),
            "agent": self.agent,
            "success": success,
            "latency_s": round(latency_s, 2),
            "token_cost": round(token_cost, 6),
            "tool_accuracy": round(tool_accuracy, 2),
            "hallucination": hallucination,
            "query": query[:100],
            "error": error[:200] if error else "",
        }
        with open(self._fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def summary(self, last_n: int = 100) -> dict:
        """获取最近 N 次执行的统计摘要"""
        if not self._fp.exists():
            return {"total": 0}
        records = []
        with open(self._fp, "r") as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        recent = records[-last_n:]
        if not recent:
            return {"total": 0}

        total = len(recent)
        successes = sum(1 for r in recent if r["success"])
        avg_latency = sum(r["latency_s"] for r in recent) / total
        avg_cost = sum(r["token_cost"] for r in recent) / total
        avg_tool_acc = sum(r.get("tool_accuracy", 1.0) for r in recent) / total
        hallucinations = sum(1 for r in recent if r.get("hallucination", False))

        return {
            "total": total,
            "success_rate": round(successes / total * 100, 1),
            "avg_latency_s": round(avg_latency, 2),
            "avg_token_cost": round(avg_cost, 6),
            "tool_accuracy": round(avg_tool_acc * 100, 1),
            "hallucination_rate": round(hallucinations / total * 100, 1),
            "failures": total - successes,
        }
