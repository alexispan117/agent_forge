"""AgentForge — Agent 执行路由（chat + search + workflow）"""

import json
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from interfaces.templates import render
from core.trace import TraceRecorder

router = APIRouter()


@router.post("/agent/{name}/run", response_class=HTMLResponse)
async def agent_run(request: Request, name: str, query: str = Form(""), engine: str = Form(""),
                    max_results: int = Form(5), recency: str = Form(""), reset: str = Form(""),
                    session_id: str = Form("default")):
    from runtimes import discover_agents
    from interfaces.app import load_config, get_current_user
    agents = discover_agents()
    config = load_config()
    user = await get_current_user(request)
    agent = agents.get(name)
    if not agent:
        return HTMLResponse(render("error.html", request=request, message=f"Agent '{name}' 不存在"), status_code=404)

    trace = TraceRecorder(agent_name=name)
    trace.record("user_input", {"query": query, "session_id": session_id})
    await run_in_threadpool(agent.init, config)

    user_id = user["id"] if user else ""
    user_role = user.get("role", "user") if user else "user"

    try:
        if name == "workflow":
            from runtimes.orchestrator_runtime import OrchestratorRuntime
            wa = OrchestratorRuntime() if not isinstance(agent, OrchestratorRuntime) else agent
            await run_in_threadpool(wa.init, config)
            result = await run_in_threadpool(
                wa.execute,
                query="" if query in ("list", "recover", "status") else query,
                user_id=user_id,
                user_role=user_role,
                action=query if query in ("list", "recover", "status", "cancel", "approve", "delete")
                       or query.startswith(("delete:", "status:", "approve:")) else "",
                task_id=query.split(":", 1)[1] if query.startswith(("status:", "delete:")) else "",
                granted=query.split(":")[2] if query.startswith("approve:") else "",
                timeout=recency if recency else "5",
            )
            data = {"status": result.get("status", ""), "steps": len(result.get("steps_detail", []))} \
                if "steps_detail" in result else result
            trace.record("workflow_result", data)
            trace.save()
            return HTMLResponse(f'<div id="workflow-result" style="display:none;">{json.dumps(result, ensure_ascii=False)}</div>')

        if name == "chat":
            result = await run_in_threadpool(agent.execute, query=query, reset=reset, session_id=session_id)
            trace.record("final_answer", {"answer_len": len(str(result.get("answer", "")))})
            trace.save()
            # 保存对话（异步持久化；失败不阻断回答）
            if result.get("answer") and user:
                try:
                    from infrastructure.persistence import crud
                    from infrastructure.persistence.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as db:
                        convs = await crud.get_user_conversations(db, user["id"], limit=1)
                        conv = convs[0] if convs else await crud.create_conversation(
                            db, user["id"], title=query[:50], agent="chat")
                        await crud.add_message(db, conv.id, "user", query[:1000])
                        await crud.add_message(db, conv.id, "assistant", (result.get("answer") or ""),
                                               sources=json.dumps(result.get("sources", []), ensure_ascii=False))
                except Exception:
                    pass
            if result.get("answer"):
                import uuid
                result["message_id"] = uuid.uuid4().hex[:12]
            return HTMLResponse(f'<div id="chat-result" style="display:none;">{json.dumps(result, ensure_ascii=False)}</div>')

        result = await run_in_threadpool(agent.execute, query=query, max_results=max_results,
                                         engine=engine, recency=recency,
                                         baidu_api_key=config.get("baidu_api_key", ""))
        trace.record("tool_result", {"total": result.get("total", 0)})
        trace.save()
        return HTMLResponse(render("result.html", request=request, agent_name=name, query=query, result=result,
                                   title=f"搜索结果 — {query}"))
    except Exception as e:
        trace.record("error", {"error": str(e)})
        trace.save()
        return HTMLResponse(f'<div id="chat-result" style="display:none;">{json.dumps({"error": str(e)}, ensure_ascii=False)}</div>')


@router.get("/agent/{name}", response_class=HTMLResponse)
async def agent_info(request: Request, name: str):
    from runtimes import discover_agents
    from interfaces.app import load_config, get_current_user
    agents = discover_agents()
    config = load_config()
    user = await get_current_user(request)
    agent = agents.get(name)
    if not agent:
        return HTMLResponse(render("error.html", request=request, message=f"Agent '{name}' 不存在"), status_code=404)
    if name == "chat":
        rag_dir = Path(__file__).parent.parent.parent / "docs"
        docs_found = any(rag_dir.rglob("*.[mM][dD]")) or any(rag_dir.rglob("*.[tT][xX][tT]"))
        emb_cfg = config.get("embedding", {})
        vector_ready = bool(emb_cfg.get("api_key"))
        history: list[dict] = []
        if user:
            try:
                from infrastructure.persistence import crud
                from infrastructure.persistence.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    convs = await crud.get_user_conversations(db, user["id"], limit=1)
                    if convs:
                        msgs = await crud.get_recent_messages(db, convs[0].id, limit=20)
                        history = [{"role": m.role, "content": (m.content or "")} for m in msgs]
            except Exception:
                history = []
        history_json = json.dumps(history, ensure_ascii=False)
        return HTMLResponse(render("chat.html", request=request, agent=agent, config=config, user=user,
                                   docs_found=docs_found, vector_ready=vector_ready,
                                   history_json=history_json, title="💬 智能问答"))
    if name == "workflow":
        return HTMLResponse(render("workflow.html", request=request, agent=agent, config=config, user=user, title="⚙️ 工作流"))
    return HTMLResponse(render("agent_info.html", request=request, agent=agent, config=config, user=user, title=f"Agent: {name}"))
