"""AgentForge — Web 用户认证（全异步 v2）"""

import hashlib
import time

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from infrastructure.persistence.database import AsyncSessionLocal
from infrastructure.persistence import crud
from interfaces.templates import render

router = APIRouter(tags=["auth"])

SESSION_COOKIE = "agentforge_session"
SESSION_EXPIRE_DAYS = 7


def _make_session_id(user_id: str) -> str:
    raw = f"{user_id}:{int(time.time())}:agentforge_secret"
    return f"{user_id}.{hashlib.md5(raw.encode()).hexdigest()[:12]}"


def _parse_session(session_id: str | None) -> str | None:
    """从会话 Cookie 解析 user_id（无状态会话，演示级）。"""
    if not session_id or "." not in session_id:
        return None
    return session_id.split(".")[0]


async def get_user_by_session(session_id: str | None) -> dict | None:
    """按会话 Cookie 解析当前用户，返回 dict 视图。"""
    user_id = _parse_session(session_id)
    if not user_id:
        return None
    async with AsyncSessionLocal() as db:
        u = await crud.get_user_by_id(db, user_id)
        if u:
            return {"id": u.id, "username": u.username, "role": "admin"}
    return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return HTMLResponse(render("login.html", request=request, error=error, title="登录"))


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = ""):
    return HTMLResponse(render("register.html", request=request, error=error, title="注册"))


@router.post("/login", response_class=HTMLResponse)
async def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_username(db, username)
        if not user or not crud.verify_password(password, user.hashed_password):
            return HTMLResponse(render("login.html", request=request, error="用户名或密码错误", title="登录"))
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(key=SESSION_COOKIE, value=_make_session_id(user.id),
                        max_age=SESSION_EXPIRE_DAYS * 86400, httponly=True)
        return resp


@router.post("/register", response_class=HTMLResponse)
async def register_action(request: Request, username: str = Form(...), email: str = Form(...),
                          password: str = Form(...)):
    async with AsyncSessionLocal() as db:
        if await crud.get_user_by_username(db, username):
            return HTMLResponse(render("register.html", request=request, error="用户名已存在", title="注册"))
        if await crud.get_user_by_email(db, email):
            return HTMLResponse(render("register.html", request=request, error="邮箱已注册", title="注册"))
        if len(password) < 6:
            return HTMLResponse(render("register.html", request=request, error="密码至少6位", title="注册"))
        user = await crud.create_user(db, username, email, password)
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(key=SESSION_COOKIE, value=_make_session_id(user.id),
                        max_age=SESSION_EXPIRE_DAYS * 86400, httponly=True)
        return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await get_user_by_session(request.cookies.get(SESSION_COOKIE))
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    async with AsyncSessionLocal() as db:
        stats = await crud.get_user_stats(db, user["id"])
        convs = await crud.get_user_conversations(db, user["id"], limit=20)
    return HTMLResponse(render("dashboard.html", request=request, user=user,
                               stats=stats, conversations=convs, title="📊 用户中心"))
