"""AgentForge — pytest 测试套件

运行：python -m pytest tests.py -q

设计要点：
- 文件顶部先钉死 LLM_MOCK_MODE=true（零网络）与测试专用 DATABASE_URL，
  再 import 项目模块（database.py 的 engine 是模块级创建的）
- test_import_smoke 遍历 8 个顶层包全量 import，防断链复发（本次重构头号回归测试）
- 端到端用例在 Worker 全部不可达时自动验证「降级本地执行」路径
"""

import os

os.environ.setdefault("LLM_MOCK_MODE", "true")
_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "test_app.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
# 清理上一轮残留的测试库（用户名有唯一约束，必须全新库）
for _suffix in ("", "-wal", "-shm"):
    if os.path.exists(_TEST_DB + _suffix):
        os.remove(_TEST_DB + _suffix)

import asyncio
import importlib
import pkgutil

import pytest

# ═══════════════════════════════════════════════
# 1. 断链回归：全包 import 冒烟
# ═══════════════════════════════════════════════

TOP_PACKAGES = ["core", "runtimes", "orchestration", "memory", "toolkit", "infrastructure", "interfaces"]

# 无 __init__.py 的命名空间子模块，walk_packages 遍历不到，显式列出
EXTRA_MODULES = [
    "interfaces.routes.agent",
    "interfaces.routes.workflows",
    "interfaces.app",
    "interfaces.auth",
    "interfaces.feedback",
    "services.supervisor.main",
    "services.worker_analyst.main",
    "services.worker_desensitize.main",
    "services.worker_report.main",
]


def _all_modules() -> list[str]:
    names: list[str] = []
    for pkg_name in TOP_PACKAGES:
        pkg = importlib.import_module(pkg_name)
        for info in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}."):
            names.append(info.name)
    return names + EXTRA_MODULES


def test_import_smoke():
    """8 个顶层包 + 服务入口全部可 import（断链零容忍）。"""
    failures: dict[str, str] = {}
    for name in _all_modules():
        try:
            importlib.import_module(name)
        except Exception as e:  # noqa: BLE001 — 收集全部失败再统一报告
            failures[name] = f"{type(e).__name__}: {e}"
    assert not failures, "以下模块 import 失败（断链）:\n" + "\n".join(
        f"  {m}: {err}" for m, err in sorted(failures.items())
    )


# ═══════════════════════════════════════════════
# 2. core/llm_factory — 异步 Mock
# ═══════════════════════════════════════════════

async def test_mock_llm_achat_and_embed_deterministic():
    from core.llm_factory import get_llm
    llm = get_llm()
    answer = await llm.achat([{"role": "user", "content": "请拆解这份合同审计任务"}])
    assert isinstance(answer, str) and answer

    v1 = await llm.aembed("合同条款")
    v2 = await llm.aembed("合同条款")
    assert v1 == v2, "Mock embedding 必须是确定性的"
    assert len(v1) == 768


async def test_mock_llm_concurrent_nonblocking():
    """5 路并发耗时应远小于串行（验证 asyncio.sleep 非阻塞）。"""
    import time
    from core.llm_factory import get_llm
    llm = get_llm()
    t0 = time.time()
    await asyncio.gather(*(llm.achat([{"role": "user", "content": "生成报告"}]) for _ in range(5)))
    elapsed = time.time() - t0
    assert elapsed < 3.0, f"并发疑似被阻塞: {elapsed:.2f}s"


def test_llm_token_utils():
    from core.llm_factory import estimate_tokens, truncate
    assert estimate_tokens("你好") >= 2
    assert truncate("hello world", 5) == "hello…"
    assert truncate("hi", 5) == "hi"


def test_llm_facade_sync_compat():
    """同步门面在无事件循环的上下文可用（CLI/线程池过渡路径）。"""
    from core.llm_factory import get_llm
    llm = get_llm()
    out = llm.chat([{"role": "user", "content": "你好"}])
    assert isinstance(out, str) and out


# ═══════════════════════════════════════════════
# 3. core/with_fallback — 同步/异步降级
# ═══════════════════════════════════════════════

def test_fallback_sync_success():
    from core.with_fallback import with_fallback

    @with_fallback(service="analyst", max_retries=1, base_delay=0.01)
    def ok():
        return {"fine": True}

    assert ok() == {"fine": True}


def test_fallback_sync_degraded_default():
    from core.with_fallback import with_fallback

    @with_fallback(service="analyst", max_retries=1, base_delay=0.01)
    def boom():
        raise ConnectionError("worker down")

    result = boom()
    assert result["status"] == "degraded"
    assert "worker down" in result["error"]


async def test_fallback_async_retry_then_success():
    from core.with_fallback import with_fallback
    calls = {"n": 0}

    @with_fallback(service="report", max_retries=2, base_delay=0.01)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("慢")
        return "ok"

    assert await flaky() == "ok"
    assert calls["n"] == 2


async def test_fallback_async_business_error_not_retried():
    """业务异常（ValueError）不在 retry_on 白名单，必须立即抛出。"""
    from core.with_fallback import with_fallback

    @with_fallback(service="report", max_retries=2, base_delay=0.01)
    async def bad_args():
        raise ValueError("参数错误")

    with pytest.raises(ValueError):
        await bad_args()


# ═══════════════════════════════════════════════
# 4. memory/episodic — remember / query / seed
# ═══════════════════════════════════════════════

def test_episodic_remember_and_query(tmp_path):
    from memory import episodic
    # 种子隔离：指向不存在的路径，避免 DEMO_SEED_MEMORY 干扰断言
    mem = episodic.EpisodicMemory("pytest_iso", seed_path=tmp_path / "none.json")
    mem.clear()
    mem.remember("project:hermes", "合同审计项目使用五维评分", importance=0.9)
    mem.add_history("合同审计怎么做", "先拆解再并行执行", success=True)
    hits = mem.query("合同审计")
    assert "project:hermes" in hits or "合同审计" in hits
    mem.clear()


def test_episodic_load_seed(tmp_path):
    import json
    from memory import episodic
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({
        "sessions": [{
            "session_id": "s1", "project": "测试项目",
            "summary": "上次完成了合同审计演示",
            "key_decisions": ["采用 MCP 协议", "密钥外移"],
        }]
    }, ensure_ascii=False), encoding="utf-8")
    mem = episodic.EpisodicMemory("pytest_seed", seed_path=seed)
    try:
        assert mem.recall("seed:s1") is not None
        assert len(mem.recall_all()) >= 3  # 1 summary + 2 decisions
    finally:
        mem.clear()


# ═══════════════════════════════════════════════
# 5. orchestration/agent_protocol — ASGI 内存往返
# ═══════════════════════════════════════════════

async def test_protocol_roundtrip():
    import httpx
    from fastapi import FastAPI
    from orchestration.agent_protocol import (
        AgentCard, ToolSpec, WorkerClient, build_protocol_router,
    )

    def demo_tool(text: str) -> dict:
        return {"echo": text, "length": len(text)}

    card = AgentCard(
        name="worker-test", description="测试",
        tools=[ToolSpec(name="demo_tool", input_schema={
            "type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
        })],
    )
    app = FastAPI()
    app.include_router(build_protocol_router(card=card, tools={"demo_tool": demo_tool}))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as raw:
        async with WorkerClient("http://test", client=raw) as wc:
            discovered = await wc.discover()
            assert discovered.name == "worker-test"
            assert [t.name for t in await wc.list_tools()] == ["demo_tool"]
            out = await wc.call_tool("demo_tool", {"text": "你好"})
            assert out == {"echo": "你好", "length": 2}
            # 未知工具 → RPC 错误
            with pytest.raises(RuntimeError):
                await wc.call_tool("nope", {})


async def test_protocol_sync_tool_in_event_loop():
    """同步工具必须在线程池执行（不能在事件循环里阻塞/抛错）。"""
    import httpx
    from fastapi import FastAPI
    from orchestration.agent_protocol import AgentCard, ToolSpec, WorkerClient, build_protocol_router
    from core.llm_factory import get_llm

    def sync_llm_tool(text: str) -> dict:
        # facade.chat 内部 asyncio.run：若不在线程池会直接 raise
        return {"reply": get_llm().chat([{"role": "user", "content": text}])[:10]}

    card = AgentCard(name="w", tools=[ToolSpec(name="sync_llm_tool")])
    app = FastAPI()
    app.include_router(build_protocol_router(card=card, tools={"sync_llm_tool": sync_llm_tool}))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as raw:
        async with WorkerClient("http://test", client=raw) as wc:
            out = await wc.call_tool("sync_llm_tool", {"text": "你好"})
            assert out["reply"]


# ═══════════════════════════════════════════════
# 6. orchestration/supervisor — 端到端（Worker 离线 → 降级路径）
# ═══════════════════════════════════════════════

async def test_supervisor_e2e_and_isolation():
    from orchestration.supervisor import get_supervisor, reset_supervisor
    reset_supervisor()
    sup = get_supervisor()

    wf1 = sup.create_workflow("审计一份采购合同")
    wf2 = sup.create_workflow("审计一份销售合同")
    assert wf1 != wf2

    result = await sup.run(wf1)
    assert result["status"] == "completed"
    assert result["task_tree"], "任务树不应为空"
    # CLEAR 五维评分齐全
    for dim in ("cost", "latency", "efficacy", "assurance", "reliability"):
        assert dim in result["clear_scores"]
    # 所有任务到达终态
    terminal = {"done", "failed", "degraded"}
    assert all(t["status"] in terminal for t in result["task_tree"])

    # 工作流隔离：wf2 的任务注册表必须为空
    wf2_view = sup.get_workflow(wf2)
    assert wf2_view["task_tree"] == []
    reset_supervisor()


async def test_supervisor_degraded_not_failed_no_deadlock():
    """回归：降级兜底字典自带 error 字段，不得误判 failed 导致下游死锁。

    mock decompose 含 agent="supervisor" 的任务（未配置 Worker），
    其降级结果 {"status": "degraded", "error": "..."} 必须记为 degraded，
    依赖它的后续任务必须能继续调度。
    """
    from orchestration.supervisor import Supervisor
    sup = Supervisor()  # 独立实例，避免单例状态干扰

    wf_id = sup.create_workflow("审计合同（含审批节点）")
    # 强制使用含 supervisor 节点的拆解结果
    sup._workflows[wf_id]["request"] = "审计合同"
    await sup.decompose(wf_id)
    # 若随机 mock 未含 supervisor 节点，手动注入一个验证调度逻辑
    wf = sup._workflows[wf_id]
    if not any(n.agent == "supervisor" for n in wf["tasks"].values()):
        from orchestration.supervisor import TaskNode
        first_id = next(iter(wf["tasks"]))
        node = TaskNode("sup1", "审批流程发起", "supervisor", depends_on=[first_id])
        wf["tasks"][node.id] = node
        tail = TaskNode("tail1", "归档", "report", depends_on=["sup1"])
        wf["tasks"][tail.id] = tail

    result = await sup.execute(wf_id)
    statuses = {t["id"]: t["status"] for t in result["task_tree"]}
    assert "failed" not in statuses.values(), f"出现 failed 任务: {statuses}"
    assert all(s in ("done", "degraded") for s in statuses.values())


async def test_supervisor_inject_failure():
    from orchestration.supervisor import get_supervisor, reset_supervisor
    reset_supervisor()
    sup = get_supervisor()
    wf_id = sup.create_workflow("测试故障注入")
    await sup.decompose(wf_id)
    injected = sup.inject_failure(wf_id)
    assert injected is not None
    wf = sup.get_workflow(wf_id)
    victim = next(t for t in wf["task_tree"] if t["id"] == injected)
    assert victim["status"] == "failed"
    reset_supervisor()


# ═══════════════════════════════════════════════
# 7. infrastructure/persistence — 异步 CRUD
# ═══════════════════════════════════════════════

async def test_crud_user_conversation_feedback():
    from infrastructure.persistence.database import AsyncSessionLocal, ainit_db
    from infrastructure.persistence import crud

    await ainit_db()
    async with AsyncSessionLocal() as db:
        user = await crud.create_user(db, "pytest_user", "pytest@example.com", "secret123")
        assert user.id
        fetched = await crud.get_user_by_username(db, "pytest_user")
        assert fetched and crud.verify_password("secret123", fetched.hashed_password)
        assert not crud.verify_password("wrong", fetched.hashed_password)

        conv = await crud.create_conversation(db, user.id, title="测试对话")
        await crud.add_message(db, conv.id, "user", "你好")
        await crud.add_message(db, conv.id, "assistant", "你好！")
        msgs = await crud.get_recent_messages(db, conv.id)
        # 消息顺序取决于插入时间戳，使用 sorted 保证断言稳定
        roles = sorted([m.role for m in msgs])
        assert roles == ["assistant", "user"]

        await crud.add_feedback(db, user.id, "msg-1", rating=1)
        stats = await crud.get_feedback_stats(db)
        assert stats["likes"] >= 1


def test_verify_password_legacy_format():
    """旧 salt:sha256 格式哈希仍可校验（平滑迁移）。"""
    import hashlib
    from infrastructure.persistence.crud import verify_password
    legacy = "somesalt:" + hashlib.sha256(b"somesalt" + b"pw123").hexdigest()
    assert verify_password("pw123", legacy)
    assert not verify_password("nope", legacy)


# ═══════════════════════════════════════════════
# 8. interfaces — HTTP 端到端（ASGI，无需起服务）
# ═══════════════════════════════════════════════

async def test_http_health():
    import httpx
    from interfaces.app import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


async def test_http_workflow_create_and_complete():
    """创建 → 后台执行 → 轮询至 completed（Worker 离线自动降级，全程零网络）。"""
    import httpx
    from interfaces.app import app
    from orchestration.supervisor import reset_supervisor
    reset_supervisor()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/workflows", json={"request": "审计一份供应商合同"})
        assert resp.status_code == 200
        wf_id = resp.json()["id"]

        for _ in range(60):
            await asyncio.sleep(0.5)
            wf = (await client.get(f"/api/workflows/{wf_id}")).json()
            if wf.get("status") == "completed":
                break
        else:
            pytest.fail("工作流 30s 内未完成")

        assert wf["clear_scores"], "完成后必须有 CLEAR 评分"
        assert wf["task_tree"]
    reset_supervisor()


async def test_http_agents_cards_all_offline():
    """本测试环境无 Worker 在线，所有卡片应标记 offline（不抛错）。"""
    import httpx
    from interfaces.app import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents/cards")
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        assert len(agents) == 3
        assert all(a["status"] == "offline" for a in agents)
