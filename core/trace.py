"""AgentForge — Trace 运行链路观测

参考 MokioClaw 的 Trace 系统。
在关键节点记录事件，写入可读的 JSONL 日志。
"""

import json
import time
from pathlib import Path

TRACE_DIR = Path.home() / ".cache" / "agentforge" / "traces"


class TraceRecorder:
    """运行链路观测

    用法:
        trace = TraceRecorder("search")
        trace.record("user_input", {"query": "..."})
        trace.record("tool_call", {"tool": "web_search"})
        trace.record("tool_result", {"count": 5})
        trace.record("final_answer", {"summary": "..."})
        summary = trace.summary()
        trace.save()
    """

    def __init__(self, agent_name: str = "default"):
        self.agent = agent_name
        self._events: list[dict] = []
        self._start = time.time()
        self._session_id = time.strftime(f"trace-%Y%m%d-%H%M%S-{agent_name}")

    @property
    def session_id(self) -> str:
        return self._session_id

    def record(self, event_type: str, data: dict):
        """记录事件

        事件类型约定:
        - user_input: 用户输入
        - plan: 执行计划
        - tool_call: 工具调用
        - tool_result: 工具结果
        - error: 错误
        - final_answer: 最终回答
        """
        self._events.append({
            "type": event_type,
            "ts": round(time.time() - self._start, 3),
            **data,
        })

    def save(self) -> str:
        """保存 Trace 到文件"""
        fp = TRACE_DIR / f"{self._session_id}.json"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(
            json.dumps({
                "session_id": self._session_id,
                "agent": self.agent,
                "duration_s": round(time.time() - self._start, 2),
                "events": self._events,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(fp)

    def summary(self) -> dict:
        """生成 Trace 摘要"""
        return {
            "session_id": self._session_id,
            "agent": self.agent,
            "duration_s": round(time.time() - self._start, 2),
            "event_count": len(self._events),
            "tool_calls": sum(1 for e in self._events if e["type"] == "tool_call"),
            "errors": sum(1 for e in self._events if e["type"] == "error"),
        }
