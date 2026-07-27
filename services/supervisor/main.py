"""services/supervisor/main.py — Supervisor 总控节点（端口 8000）

职责：
1. 承载 interfaces.app 全部 Web 路由（总控台 / SSE / 工作流 API）
2. 通过 MCP/A2A 协议对外暴露自身能力（开放互联演示）
"""
import asyncio
import os
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SERVICE_TYPE", "supervisor")
os.environ.setdefault("LLM_MOCK_MODE", "true")

from orchestration.agent_protocol import AgentCard, ToolSpec, build_protocol_router
from orchestration.supervisor import get_supervisor
from interfaces.app import app as fastapi_app
import uvicorn

# ── Supervisor 的 A2A AgentCard ──
_CARD = AgentCard(
    name="supervisor",
    description="Supervisor 总控节点：任务拆解、DAG 调度、故障自愈",
    endpoint=os.environ.get("SUPERVISOR_URL", "http://localhost:8000"),
    capabilities=["orchestration", "decompose", "fault_injection", "memory"],
    tools=[
        ToolSpec(
            name="create_workflow",
            description="创建并后台执行一个多 Agent 工作流",
            input_schema={"type": "object",
                          "properties": {"request": {"type": "string", "description": "任务描述"}},
                          "required": ["request"]},
        ),
        ToolSpec(
            name="get_workflow",
            description="查询工作流执行状态与任务树",
            input_schema={"type": "object",
                          "properties": {"wf_id": {"type": "string"}},
                          "required": ["wf_id"]},
        ),
    ],
)


async def _create_workflow(request: str) -> dict:
    sup = get_supervisor()
    wf_id = sup.create_workflow(request)
    asyncio.create_task(sup.run(wf_id))
    return {"id": wf_id, "status": "created"}


def _get_workflow(wf_id: str) -> dict:
    return get_supervisor().get_workflow(wf_id) or {"error": "工作流不存在"}


# 挂载 MCP/A2A 协议路由（/.well-known/agent.json + /mcp + /health）
fastapi_app.include_router(
    build_protocol_router(card=_CARD, tools={
        "create_workflow": _create_workflow,
        "get_workflow": _get_workflow,
    })
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"[Supervisor] 启动在端口 {port}")
    print(f"[Supervisor] LLM模式: {'MOCK' if os.environ.get('LLM_MOCK_MODE', 'true') == 'true' else 'REAL'}")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port, log_level="info")
