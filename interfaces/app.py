"""AgentForge — Web UI (FastAPI)

v2 变更：
1. 新增 GET /health（docker-compose 健康检查依赖）
2. lifespan 中完成：异步建表 + Supervisor 事件 → SSE 接线（修复总控台零事件）
3. get_current_user 全异步（修复同步 DB 阻塞事件循环 + 会话解析 bug）
4. 移除与 auth.py 重复的 /login /register /dashboard 路由（单一职责归 auth）
5. sse_push 改用 get_running_loop（get_event_loop 在 3.12+ 已弃用）
"""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core.config import load_config
from interfaces.auth import router as auth_router, SESSION_COOKIE, get_user_by_session
from interfaces.routes.agent import router as agent_router
from interfaces.routes.workflows import router as workflows_router
from interfaces.feedback import router as feedback_router
from interfaces.templates import render

ROOT = Path(__file__).parent.parent

# ── SSE 事件队列 ──
_sse_queues: list[asyncio.Queue] = []
_sse_lock = asyncio.Lock()


async def _sse_broadcast(event: str, data: dict):
    payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    async with _sse_lock:
        for q in _sse_queues[:]:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                _sse_queues.remove(q)


def sse_push(event: str, data: dict):
    """供同步/异步上下文调用的事件推送入口。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_sse_broadcast(event, data))
    except RuntimeError:
        pass  # 无运行中事件循环（如 CLI 上下文），静默丢弃


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 异步建表
    from infrastructure.persistence.database import ainit_db
    await ainit_db()

    # 2. Supervisor 事件 → SSE 接线（总控台实时数据总线）
    from orchestration.supervisor import register_event_handler
    register_event_handler(lambda p: sse_push(p.get("type", "event"), p.get("data", {})))

    yield


app = FastAPI(title="AgentForge", lifespan=lifespan)


class SPAStaticFiles(StaticFiles):
    """SPA 托管：目录路径自动服务 index.html，未知子路径回退到 SPA 入口。

    解决两个 404 场景：
    1. /static/spa（无尾斜杠）→ 重定向后服务 index.html（html=True）
    2. /static/spa/history 等前端路由刷新 → 回退 index.html，由 React Router 接管
    """

    async def get_response(self, path: str, scope):
        from starlette.exceptions import HTTPException as StarletteHTTPException
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # mount 传入的 path 带前导斜杠，且 Windows 下为反斜杠分隔（如 \spa\history）
            clean = path.replace("\\", "/").lstrip("/")
            if exc.status_code == 404 and clean.startswith("spa/"):
                return await super().get_response("spa/index.html", scope)
            raise


app.mount("/static", SPAStaticFiles(
    directory=str(ROOT / "interfaces" / "static"), html=True
), name="static")
app.include_router(auth_router)
app.include_router(agent_router)
app.include_router(workflows_router)
app.include_router(feedback_router)


from interfaces.routes.complaints import router as complaints_router
app.include_router(complaints_router)

async def get_current_user(request: Request) -> dict | None:
    """从会话 Cookie 解析当前用户（全异步）。"""
    try:
        return await get_user_by_session(request.cookies.get(SESSION_COOKIE))
    except Exception:
        return None


# ── 健康检查（docker-compose healthcheck 依赖）──
@app.get("/health")
async def health():
    return {"status": "ok", "service": "supervisor"}


# ── SSE 流式端点 ──
@app.get("/stream")
async def sse_stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    async with _sse_lock:
        _sse_queues.append(q)

    async def event_generator():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20)
                    yield payload
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            async with _sse_lock:
                if q in _sse_queues:
                    _sse_queues.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Orchestrator Dashboard ──
@app.get("/orchestrator", response_class=HTMLResponse)
async def orchestrator_page(request: Request):
    user = await get_current_user(request)
    # orchestrator.html 内嵌 workflow/chat/result 三个子模板（include 只容忍模板缺失，
    # 不容忍变量缺失），这里补齐安全默认值
    return render("orchestrator.html", request=request, user=user,
                  title="Orchestrator 总控台",
                  agent=None, result=None, query="", agent_name="search",
                  history_json="[]")


# ── 新版总控台（React SPA，构建产物在 interfaces/static/spa/）──
@app.get("/console", response_class=HTMLResponse, include_in_schema=False)
async def console_redirect():
    """一键直达新版总控台：重定向到 SPA 入口（静态托管，无需模板渲染）。"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/spa/index.html", status_code=302)


# ── 首页 ──
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    config = load_config()
    user = await get_current_user(request)
    from runtimes import discover_agents
    agents = discover_agents()
    return render("index.html", request=request, config=config, user=user,
                  agents=agents, title="🤖 AgentForge")
