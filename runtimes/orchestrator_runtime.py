"""OrchestratorRuntime v2 — 企业工作流自动化 Agent"""
from runtimes.base_runtime import BaseRuntime
from orchestration import ReActEngine, M
from orchestration.assessors import CLEARScorer


class OrchestratorRuntime(BaseRuntime):
    def __init__(self):
        self._engine: ReActEngine | None = None
        self._llm = None
        self._metrics: CLEARScorer | None = None

    @property
    def name(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return "⚙️ 企业工作流 —— LLM 规划 · 文件操作 · 代码执行 · 审批节点"

    def init(self, config: dict) -> None:
        from core.llm_factory import get_llm
        self._llm = get_llm()
        self._metrics = CLEARScorer("workflow")
        self._engine = ReActEngine()

    def execute(self, query: str = "", **kwargs) -> dict:
        user_id = kwargs.get("user_id", "")
        action = kwargs.get("action", "")
        task_id = kwargs.get("task_id", "")

        if not self._engine:
            return {"error": "未初始化"}

        # RBAC: admin-only 操作
        user_role = kwargs.get("user_role", "user")
        admin_actions = {"cancel", "approve", "delete"}
        if action in admin_actions or action.startswith("delete:") or action.startswith("approve:"):
            if user_role != "admin":
                return {"error": "权限不足，仅管理员可执行此操作"}

        # 列出任务
        if action == "list":
            return {"tasks": M.list_tasks(user_id=user_id, limit=20)}

        # 查看任务详情
        if action.startswith("status:"):
            tid = action.split(":", 1)[1]
            t = M.load_task(tid)
            return {"error": "任务不存在"} if not t else {"task": t}

        # 取消
        if action == "cancel" and task_id:
            t = M.load_task(task_id)
            if t:
                t["status"] = "CANCELLED"
                M.save_task(t)
            return {"status": "cancelled"}

        # 删除
        if action.startswith("delete:"):
            tid = action.split(":", 1)[1]
            return {"deleted": M.delete_task(tid)}

        # 恢复未完成任务
        if action == "recover":
            return {"recovered": len(M.recover_pending_tasks())}

        # 审批
        if action.startswith("approve:"):
            parts = action.split(":")
            tid = parts[1] if len(parts) > 1 else ""
            granted = parts[2] == "1" if len(parts) > 2 else False
            return {"approved": True if granted else False, "task_id": tid}

        # 创建 + 后台执行（立即返回 task_id，前端轮询）
        if not query:
            return {"error": "请输入任务描述"}

        task_dict = self._engine.create_task(user_id, query)

        def _run_bg():
            self._engine.run(task_dict["id"], self._llm, None)

        import threading
        threading.Thread(target=_run_bg, daemon=True).start()

        return {
            "task_id": task_dict["id"],
            "status": "RUNNING",
            "prompt": query,
        }
