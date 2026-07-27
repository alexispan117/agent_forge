"""AgentForge — Supervisor 工作流 HTTP API（v2 新增）

端点：
- POST /api/workflows                      创建并后台执行工作流
- GET  /api/workflows/{wf_id}              查询工作流状态
- POST /api/workflows/{wf_id}/inject-failure  故障注入（演示自愈降级）
- GET  /api/agents/cards                   A2A 服务发现：聚合各 Worker 的 AgentCard
"""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from orchestration.supervisor import get_supervisor

logger = logging.getLogger("routes.workflows")

router = APIRouter(prefix="/api", tags=["workflows"])


class WorkflowCreate(BaseModel):
    request: str = Field(..., min_length=1, max_length=2000)


@router.post("/workflows")
async def create_workflow(body: WorkflowCreate):
    sup = get_supervisor()
    wf_id = sup.create_workflow(body.request)
    # 后台执行：拆解 → 执行（事件经 SSE 实时推送）
    asyncio.create_task(sup.run(wf_id))
    return {"id": wf_id, "status": "created"}


@router.get("/workflows/{wf_id}")
async def get_workflow(wf_id: str):
    sup = get_supervisor()
    wf = sup.get_workflow(wf_id)
    if wf is None:
        return JSONResponse({"error": "工作流不存在"}, status_code=404)
    return wf


@router.post("/workflows/{wf_id}/inject-failure")
async def inject_failure(wf_id: str, task_id: str | None = None):
    sup = get_supervisor()
    injected = sup.inject_failure(wf_id, task_id)
    if injected is None:
        return JSONResponse({"error": "无可注入的任务（或工作流不存在）"}, status_code=404)
    return {"injected": injected}


@router.get("/agents/cards")
async def agent_cards():
    """A2A 服务发现：并行拉取各 Worker 的 AgentCard（不可达的标记 offline）。"""
    from orchestration.agent_protocol import WorkerClient
    from orchestration.supervisor import WORKER_URLS

    async def _discover(name: str, url: str) -> dict:
        try:
            async with WorkerClient(url, timeout_s=3.0, max_retries=0) as wc:
                card = await wc.discover()
                return {"status": "online", **card.model_dump()}
        except Exception as e:
            return {"name": name, "endpoint": url, "status": "offline", "error": str(e)[:120]}

    cards = await asyncio.gather(*(_discover(n, u) for n, u in WORKER_URLS.items()))
    return {"agents": list(cards)}
