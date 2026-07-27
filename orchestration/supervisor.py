"""
orchestration/supervisor.py — Supervisor 编排器 v2

核心职责：
1. 任务拆解（LLM 生成 DAG，解析失败自动兜底）
2. Worker 调度（MCP/A2A 协议客户端真实 HTTP 调用，不可达时降级本地执行）
3. 状态管理（任务树按 workflow_id 隔离，杜绝跨工作流污染）
4. DAG 真并行（asyncio.gather 调度就绪任务）
5. 记忆链路（拆解前查询情景记忆，完成后写回）
6. CLEAR 评估（执行结束自动计算五维评分并随事件推送）

事件通过 register_event_handler 注册回调外发（接口层接到 SSE /stream）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from core.llm_factory import get_llm
from core.with_fallback import with_fallback
from memory.episodic import EpisodicMemory

logger = logging.getLogger("orchestrator")

# ── 事件推送回调（由 SSE 端点注册）──
_event_handlers: list = []


def register_event_handler(handler) -> None:
    """注册事件处理回调（用于 SSE 推送）。"""
    _event_handlers.append(handler)


def _push_event(event_type: str, data: dict) -> None:
    """向所有注册的回调推送事件。"""
    payload = {"type": event_type, "data": data, "timestamp": time.time()}
    for handler in _event_handlers:
        try:
            handler(payload)
        except Exception as e:
            logger.error(f"事件推送失败: {e}")


# ── Worker 拓扑（环境变量可覆盖，默认本机端口；compose 内为服务名）──
WORKER_URLS: dict[str, str] = {
    "analyst": os.environ.get("WORKER_ANALYST_URL", "http://localhost:8001"),
    "desensitize": os.environ.get("WORKER_DESENSITIZE_URL", "http://localhost:8002"),
    "report": os.environ.get("WORKER_REPORT_URL", "http://localhost:8003"),
}

#: agent 类型 → (MCP 工具名, 参数构造函数)
_WORKER_TOOLS: dict[str, str] = {
    "analyst": "analyze_contract",
    "desensitize": "desensitize_text",
    "report": "generate_report",
}

_AGENT_LABELS = {"analyst": "分析", "desensitize": "脱敏", "report": "报告生成"}


class TaskNode:
    """任务树节点。"""

    def __init__(self, task_id: str, name: str, agent: str, depends_on: Optional[list] = None):
        self.id = str(task_id)
        self.name = name
        self.agent = agent  # analyst / desensitize / report
        self.depends_on = [str(d) for d in (depends_on or [])]
        self.status = "pending"  # pending / running / done / failed / degraded
        self.result: Any = None
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.retries = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "agent": self.agent,
            "depends_on": self.depends_on, "status": self.status,
            "result": str(self.result)[:100] if self.result else None,
            "error": self.error, "started_at": self.started_at,
            "completed_at": self.completed_at, "retries": self.retries,
        }


class Supervisor:
    """Supervisor 编排器 — 多 Agent 工作流的核心调度引擎。"""

    def __init__(self, llm=None):
        self.llm = llm or get_llm()
        self._workflows: dict[str, dict] = {}
        # 情景记忆（拆解前参考、完成后写回）
        try:
            self._memory: Optional[EpisodicMemory] = EpisodicMemory("supervisor")
        except Exception as e:
            logger.warning(f"情景记忆不可用: {e}")
            self._memory = None

    # ── 公开 API ──

    def create_workflow(self, user_request: str) -> str:
        """创建新工作流，返回 workflow_id。"""
        wf_id = uuid.uuid4().hex[:12]
        self._workflows[wf_id] = {
            "id": wf_id,
            "request": user_request,
            "created_at": time.time(),
            "status": "pending",
            "tasks": {},          # 本工作流专属任务注册表（隔离）
            "task_tree": [],
            "clear_scores": {},
        }
        _push_event("workflow_created", {"id": wf_id, "request": user_request})
        logger.info(f"[编排] 创建工作流 {wf_id}: {user_request[:50]}")
        return wf_id

    async def decompose(self, wf_id: str) -> list[dict]:
        """任务拆解：LLM 生成 DAG（先查记忆，失败后兜底模板）。"""
        wf = self._workflows.get(wf_id)
        if not wf:
            raise ValueError(f"工作流 {wf_id} 不存在")

        wf["status"] = "decomposing"
        wf["started_at"] = time.time()
        _push_event("workflow_status", {"id": wf_id, "status": "decomposing"})

        # 记忆唤醒：查找历史相似任务
        memory_hint = ""
        if self._memory:
            try:
                hits = self._memory.query(wf["request"])
                if hits:
                    memory_hint = f"\n\n历史经验参考：\n{hits}\n"
                    _push_event("memory_recall", {"workflow_id": wf_id, "hits": hits[:200]})
            except Exception as e:
                logger.warning(f"记忆查询失败: {e}")

        prompt = f"""请将以下任务拆解为原子化的执行步骤。

任务：{wf['request']}{memory_hint}

每个步骤必须包含：
- name: 步骤名称
- agent: 负责的Worker类型（analyst/desensitize/report）
- depends_on: 依赖的步骤ID列表（空列表表示无依赖）

以JSON格式返回：{{"tasks": [...]}}"""

        result = await self.llm.achat([{"role": "user", "content": prompt}])

        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            logger.warning("[编排] LLM 拆解结果非 JSON，使用兜底模板")
            parsed = self._fallback_decompose(wf["request"])

        # 构建本工作流的任务树
        nodes: list[dict] = []
        for t in parsed.get("tasks", []):
            node = TaskNode(
                task_id=t.get("id", uuid.uuid4().hex[:8]),
                name=t.get("name", "未命名任务"),
                agent=t.get("agent", "analyst"),
                depends_on=t.get("depends_on", []),
            )
            wf["tasks"][node.id] = node
            nodes.append(node.to_dict())

        # 依赖 ID 规范化：LLM 可能返回数字/字符串混合
        id_map = {n["id"]: n["id"] for n in nodes}
        for node in wf["tasks"].values():
            node.depends_on = [str(d) for d in node.depends_on if str(d) in id_map]

        wf["task_tree"] = [n.to_dict() for n in wf["tasks"].values()]
        wf["status"] = "ready"
        _push_event("task_tree_updated", {"workflow_id": wf_id, "tasks": wf["task_tree"]})
        logger.info(f"[编排] 拆解完成: {len(nodes)} 个任务")
        return wf["task_tree"]

    async def execute(self, wf_id: str) -> dict:
        """执行工作流：DAG 就绪任务 asyncio.gather 真并行。"""
        wf = self._workflows.get(wf_id)
        if not wf:
            return {"error": "工作流不存在"}

        wf["status"] = "running"
        _push_event("workflow_status", {"id": wf_id, "status": "running"})

        tasks: dict[str, TaskNode] = wf["tasks"]
        max_iterations = 50

        for _ in range(max_iterations):
            pending = [n for n in tasks.values() if n.status == "pending"]
            if not pending:
                break

            # 依赖全部 done 的任务才可调度（degraded 视为可继续）
            ready = [
                n for n in pending
                if all(tasks.get(d) is None or tasks[d].status in ("done", "degraded")
                       for d in n.depends_on)
            ]

            if not ready:
                logger.warning(f"[编排] 死锁检测: {len(pending)} 个任务无法调度")
                for node in pending:
                    node.status = "failed"
                    node.error = "依赖无法满足"
                    _push_event("task_status", node.to_dict())
                break

            for node in ready:
                node.status = "running"
                node.started_at = time.time()
                _push_event("task_status", node.to_dict())

            # 真并行执行就绪批次
            results = await asyncio.gather(
                *(self._call_worker(node.agent, node.name, node.id) for node in ready),
                return_exceptions=True,
            )

            for node, result in zip(ready, results):
                node.completed_at = time.time()
                if isinstance(result, Exception):
                    node.status = "failed"
                    node.error = str(result)
                elif result.get("degraded") or result.get("status") == "degraded":
                    # 降级判定必须先于 error：降级兜底字典自带 error 说明字段
                    node.status = "degraded"
                    node.result = result
                elif result.get("error"):
                    node.status = "failed"
                    node.error = result["error"]
                else:
                    node.status = "done"
                    node.result = result
                _push_event("task_status", node.to_dict())

        # 汇总
        done = sum(1 for n in tasks.values() if n.status == "done")
        failed = sum(1 for n in tasks.values() if n.status == "failed")
        degraded = sum(1 for n in tasks.values() if n.status == "degraded")
        total = len(tasks) or 1

        wf["status"] = "completed"
        wf["completed_at"] = time.time()
        wf["task_tree"] = [n.to_dict() for n in tasks.values()]
        wf["clear_scores"] = self._compute_clear(wf, done, failed, degraded)

        # 记忆写回：记录本次工作流结论
        if self._memory:
            try:
                summary = (f"工作流「{wf['request'][:60]}」完成: {done} 成功 / "
                           f"{degraded} 降级 / {failed} 失败")
                self._memory.remember(f"workflow:{wf_id}", summary, importance=0.7)
                self._memory.add_history(wf["request"][:200], summary, success=(failed == 0))
            except Exception as e:
                logger.warning(f"记忆写回失败: {e}")

        _push_event("workflow_status", {
            "id": wf_id, "status": "completed",
            "final_state": wf["task_tree"],
            "clear_scores": wf["clear_scores"],
        })
        return wf

    async def run(self, wf_id: str) -> dict:
        """拆解 + 执行的一站式入口。"""
        await self.decompose(wf_id)
        return await self.execute(wf_id)

    def get_workflow(self, wf_id: str) -> Optional[dict]:
        wf = self._workflows.get(wf_id)
        if wf is None:
            return None
        # 返回可 JSON 序列化的视图
        return {k: v for k, v in wf.items() if k != "tasks"} | {
            "task_tree": [n.to_dict() for n in wf["tasks"].values()],
        }

    def inject_failure(self, wf_id: str, task_id: Optional[str] = None) -> Optional[str]:
        """故障注入：优先指定任务，否则选第一个 running/pending 任务。返回被注入的任务 id。"""
        wf = self._workflows.get(wf_id)
        if not wf:
            return None
        tasks = wf["tasks"]
        node: Optional[TaskNode] = None
        if task_id and task_id in tasks:
            node = tasks[task_id]
        else:
            node = next((n for n in tasks.values() if n.status == "running"), None) \
                or next((n for n in tasks.values() if n.status == "pending"), None)
        if node is None:
            return None
        node.status = "failed"
        node.error = "[故障注入] 模拟 Worker 宕机"
        _push_event("task_status", node.to_dict())
        logger.warning(f"[故障注入] 任务 {node.id} 已标记为失败")
        return node.id

    # ── 私有方法 ──

    async def _call_worker(self, agent: str, task_name: str, task_id: str) -> dict:
        """通过 MCP/A2A 协议调用 Worker；不可达时降级为本地 LLM 模拟执行。

        agent 无对应远程 Worker（如 supervisor 自身的审批/编排步骤）时，
        视为本地编排任务直接执行——这属于设计内行为，不算降级。
        """
        if agent not in WORKER_URLS or agent not in _WORKER_TOOLS:
            label = _AGENT_LABELS.get(agent, agent)
            response = await self.llm.achat(
                [{"role": "user", "content": f"执行{label}任务：{task_name}"}]
            )
            return {"result": response, "agent": agent, "via": "local"}

        @with_fallback(service=agent, max_retries=1, timeout_s=8.0, base_delay=0.5)
        async def _remote() -> dict:
            from orchestration.agent_protocol import WorkerClient
            base_url = WORKER_URLS[agent]
            tool = _WORKER_TOOLS[agent]
            args = self._build_tool_args(agent, tool, task_name)
            async with WorkerClient(base_url, timeout_s=8.0, max_retries=0) as wc:
                out = await wc.call_tool(tool, args)
            out["via"] = "remote"
            return out

        try:
            return await _remote()
        except Exception as e:
            # 降级策略：本地 LLM 模拟该 Worker（单机演示 / Worker 宕机场景）
            logger.warning(f"[编排] Worker {agent} 远程调用失败，降级本地执行: {e}")
            label = _AGENT_LABELS.get(agent, agent)
            response = await self.llm.achat(
                [{"role": "user", "content": f"执行{label}任务：{task_name}"}]
            )
            return {"result": response, "agent": agent, "via": "local_mock", "degraded": True}

    @staticmethod
    def _build_tool_args(agent: str, tool: str, task_name: str) -> dict:
        """按 MCP 工具的 input_schema 构造参数。"""
        if tool == "analyze_contract":
            return {"contract_text": task_name}
        if tool == "desensitize_text":
            return {"text": task_name}
        if tool == "generate_report":
            return {"findings": [{"task": task_name}]}
        return {"input": task_name}

    @staticmethod
    def _compute_clear(wf: dict, done: int, failed: int, degraded: int) -> dict:
        """从真实执行数据计算 CLEAR 五维评分（替代前端随机数）。"""
        total = max(done + failed + degraded, 1)
        elapsed = max(wf.get("completed_at", 0) - wf.get("started_at", time.time()), 0.01)
        return {
            "cost": max(100 - total * 8, 20),                          # 任务越多调用成本越高
            "latency": max(min(round(100 - elapsed * 5), 100), 20),    # 越快越高
            "efficacy": round((done + degraded) / total * 100),        # 完成率（含降级）
            "assurance": 100 if failed == 0 else max(100 - failed * 25, 30),
            "reliability": round((done / total) * 100),                # 无故障完成率
        }

    def _fallback_decompose(self, request: str) -> dict:
        """LLM 拆解失败的兜底方案。"""
        return {
            "tasks": [
                {"id": "1", "name": f"分析任务：{request[:30]}", "agent": "analyst", "depends_on": []},
                {"id": "2", "name": "数据脱敏处理", "agent": "desensitize", "depends_on": ["1"]},
                {"id": "3", "name": "报告生成", "agent": "report", "depends_on": ["1", "2"]},
            ]
        }


# ═══════════════════════════════════════════════
# 单例工厂（接口层与服务层共享同一编排器实例）
# ═══════════════════════════════════════════════

_supervisor: Optional[Supervisor] = None


def get_supervisor() -> Supervisor:
    """获取全局 Supervisor 单例。"""
    global _supervisor
    if _supervisor is None:
        _supervisor = Supervisor(get_llm())
    return _supervisor


def reset_supervisor() -> None:
    """重置单例（测试用）。"""
    global _supervisor
    _supervisor = None
