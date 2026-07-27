"""客诉工单系统 API 路由"""
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import json

router = APIRouter()


class ComplaintRequest(BaseModel):
    ticket_id: str


class ApprovalRequest(BaseModel):
    ticket_id: str
    thread_id: str
    action: str       # "approve" or "reject"
    comment: str = ""
    reviewer: str = "系统管理员"


@router.get("/complaints")
async def list_complaint_tickets(request: Request):
    """列出所有可用工单"""
    from fastapi.responses import HTMLResponse
    from orchestration.complaint_agent import list_tickets
    from interfaces.app import get_current_user
    tickets = list_tickets()
    user = await get_current_user(request)
    accept = request.headers.get("accept", "")
    if "text/html" in accept or "*/*" in accept:
        from interfaces.templates import render
        html = render("complaints.html", request=request, tickets=tickets, user=user)
        return HTMLResponse(html)
    return {"tickets": tickets}


@router.post("/api/complaints/run")
async def run_complaint(request: Request):
    """启动客诉处理工作流"""
    form = await request.form()
    ticket_id = form.get("ticket_id", "")

    if not ticket_id:
        raise HTTPException(400, "缺少 ticket_id")

    from orchestration.complaint_agent import run_complaint_workflow
    result = await run_complaint_workflow(ticket_id)

    # SSE 推送节点状态
    for msg in result.get("messages", []):
        from interfaces.app import sse_push
        sse_push("complaint_log", {"ticket_id": ticket_id, "message": msg})

    return result


@router.post("/api/complaints/approve")
async def approve_complaint(req: ApprovalRequest):
    """Human-in-the-Loop 审批：批准或拒绝"""
    from orchestration.complaint_agent import complaint_graph
    from datetime import datetime

    config = {"configurable": {"thread_id": req.thread_id}}

    # 获取当前状态快照
    snapshot = complaint_graph.get_state(config)
    if not snapshot.next:
        raise HTTPException(400, "该工单不需要审批或已完成")

    # 更新审批状态并恢复执行
    await complaint_graph.aupdate_state(
        config,
        {
            "approval_status": "approved" if req.action == "approve" else "rejected",
            "approval_comment": req.comment,
            "approval_by": req.reviewer,
            "approval_at": datetime.now().isoformat(),
        },
    )

    # 继续执行（使用 Command.resume 从 interrupt 恢复）
    from langgraph.types import Command
    result = await complaint_graph.ainvoke(
        Command(resume={"action": req.action, "comment": req.comment, "reviewer": req.reviewer}),
        config
    )

    from interfaces.app import sse_push
    sse_push("complaint_approved", {"ticket_id": req.ticket_id, "action": req.action})

    if result:
        return {"status": "completed", "summary": {
            "ticket_id": result.get("ticket_id"),
            "approval_status": result.get("approval_status"),
            "response_draft": result.get("response_draft"),
            "quality_score": result.get("quality_score"),
        }}
    return {"status": "in_progress", "message": "批准处理中"}


@router.get("/api/complaints/{ticket_id}/state")
async def get_complaint_state(ticket_id: str):
    """获取工单处理状态（用于前端轮询）"""
    from orchestration.complaint_agent import complaint_graph
    config = {"configurable": {"thread_id": ticket_id}}
    snapshot = complaint_graph.get_state(config)
    return {
        "ticket_id": ticket_id,
        "current_stage": snapshot.values.get("current_stage", "unknown") if snapshot.values else "unknown",
        "next_nodes": [str(n) for n in snapshot.next] if snapshot.next else [],
        "messages": snapshot.values.get("messages", [])[-20:] if snapshot.values else [],
        "has_interrupt": len(snapshot.next) > 0 if snapshot.next else False,
    }

