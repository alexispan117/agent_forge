"""services/worker_analyst/main.py — 分析型 Worker（端口 8001）

通过 MCP/A2A 协议暴露分析能力：
- analyze_contract：合同合规异常分析（带情景记忆唤醒）
- cross_validate：跨文档一致性交叉验证
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SERVICE_TYPE", "analyst")
os.environ.setdefault("LLM_MOCK_MODE", "true")

from core.llm_factory import get_llm
from core.with_fallback import with_fallback
from memory.episodic import EpisodicMemory
from orchestration.agent_protocol import AgentCard, ToolSpec, build_protocol_router

llm = get_llm()
memory = EpisodicMemory("analyst")


@with_fallback(service="analyst", max_retries=2)
def analyze_contract(contract_text: str, **kwargs) -> dict:
    """分析合同，识别异常（先唤醒情景记忆，再 LLM 分析）。"""
    mem = memory.query(contract_text[:50])
    context_hint = f"历史参考：\n{mem}\n" if mem else ""

    prompt = f"{context_hint}\n分析以下合同内容，找出合规异常：\n{contract_text[:2000]}"
    result = llm.chat([{"role": "user", "content": prompt}])

    return {
        "findings": result,
        "memory_hit": bool(mem),
        "timestamp": time.time(),
    }


@with_fallback(service="analyst")
def cross_validate(docs: list, **kwargs) -> dict:
    """跨文档交叉验证。"""
    texts = "\n---\n".join(str(d)[:500] for d in docs)
    result = llm.chat([{"role": "user", "content": f"交叉验证以下文档的一致性：\n{texts}"}])
    return {"validation": result}


# ── A2A AgentCard ──
CARD = AgentCard(
    name="worker-analyst",
    description="分析型 Worker：合同合规分析、跨文档交叉验证、情景记忆唤醒",
    endpoint=os.environ.get("WORKER_ANALYST_URL", "http://localhost:8001"),
    capabilities=["contract_analysis", "cross_validation", "memory_recall"],
    tools=[
        ToolSpec(
            name="analyze_contract",
            description="分析合同文本，识别合规异常",
            input_schema={"type": "object",
                          "properties": {"contract_text": {"type": "string"}},
                          "required": ["contract_text"]},
        ),
        ToolSpec(
            name="cross_validate",
            description="跨文档交叉验证一致性",
            input_schema={"type": "object",
                          "properties": {"docs": {"type": "array", "items": {"type": "string"}}},
                          "required": ["docs"]},
        ),
    ],
)

TOOLS = {"analyze_contract": analyze_contract, "cross_validate": cross_validate}


def create_app():
    from fastapi import FastAPI
    app = FastAPI(title="Worker-Analyst")
    app.include_router(build_protocol_router(card=CARD, tools=TOOLS))

    @app.post("/analyze")
    def api_analyze(data: dict):
        return analyze_contract(data.get("text", ""))

    @app.post("/cross-validate")
    def api_validate(data: dict):
        return cross_validate(data.get("docs", []))

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
