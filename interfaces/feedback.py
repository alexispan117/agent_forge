"""AgentForge — Web 用户反馈路由（v2：落库持久化）"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import JSONResponse

from infrastructure.persistence.database import AsyncSessionLocal
from infrastructure.persistence import crud
from interfaces.auth import SESSION_COOKIE, get_user_by_session

router = APIRouter()


@router.post("/feedback")
async def submit_feedback(
    request: Request,
    message_id: str = Form(""),
    rating: int = Form(0),  # 1=赞, -1=踩
    comment: str = Form(""),
):
    user = await get_user_by_session(request.cookies.get(SESSION_COOKIE))
    try:
        async with AsyncSessionLocal() as db:
            await crud.add_feedback(
                db,
                user_id=user["id"] if user else "anonymous",
                message_id=message_id,
                rating=rating,
                comment=comment,
            )
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    return JSONResponse({"status": "ok"})


@router.get("/feedback/stats")
async def feedback_stats():
    async with AsyncSessionLocal() as db:
        stats = await crud.get_feedback_stats(db)
    return JSONResponse(stats)
