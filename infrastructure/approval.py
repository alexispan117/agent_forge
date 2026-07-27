"""AgentForge — 人工审批系统

关键操作需要人类确认后才能执行。
支持 CLI 和 Web 两种审批模式。
"""

import json
from pathlib import Path
from typing import Callable

APPROVAL_DIR = Path.home() / ".cache" / "agentforge" / "approvals"


class ApprovalRequired(Exception):
    """需要人工审批"""
    def __init__(self, action: str, reason: str, action_id: str):
        self.action = action
        self.reason = reason
        self.action_id = action_id
        super().__init__(f"[审批] {action} — {reason} (ID: {action_id})")


class ApprovalHandler:
    """审批管理器

    支持三种模式:
    - inline: 终端交互审批
    - web: Web 界面审批（缓存待审批操作）
    - auto: 自动批准（开发和演示用）
    """

    def __init__(self, mode: str = "inline"):
        self.mode = mode
        self._pending: dict[str, dict] = {}

    def request(self, action: str, reason: str,
                execute_fn: Callable | None = None) -> bool:
        """请求审批

        Args:
            action: 操作描述（如 "运行命令: rm -rf /"）
            reason: 风险原因
            execute_fn: 批准后执行的回调

        Returns:
            是否批准
        """
        action_id = str(hash(f"{action}{reason}"))[:8]
        entry = {
            "action_id": action_id,
            "action": action,
            "reason": reason,
            "approved": None,
        }
        APPROVAL_DIR.mkdir(parents=True, exist_ok=True)

        if self.mode == "auto":
            self._approve(action_id, entry, execute_fn)
            return True

        if self.mode == "inline":
            print(f"\n⚠️  需要审批 [{action_id}]")
            print(f"  操作: {action}")
            print(f"  原因: {reason}")
            resp = input("  批准? (y/N): ").strip().lower()
            if resp in ("y", "yes"):
                self._approve(action_id, entry, execute_fn)
                return True
            print(f"  ❌ 已拒绝\n")
            return False

        # web 模式：缓存等待 Web 界面审批
        entry["status"] = "pending"
        self._pending[action_id] = {"entry": entry, "execute_fn": execute_fn}
        (APPROVAL_DIR / f"{action_id}.json").write_text(
            json.dumps(entry, ensure_ascii=False)
        )
        raise ApprovalRequired(action, reason, action_id)

    def approve(self, action_id: str) -> bool:
        """Web 界面批准操作"""
        info = self._pending.get(action_id)
        if not info:
            fp = APPROVAL_DIR / f"{action_id}.json"
            if fp.exists():
                info = {"entry": json.loads(fp.read_text()), "execute_fn": None}
            else:
                return False
        self._approve(action_id, info["entry"], info["execute_fn"])
        return True

    def reject(self, action_id: str) -> bool:
        """Web 界面拒绝操作"""
        info = self._pending.get(action_id)
        if info:
            info["entry"]["status"] = "rejected"
        self._pending.pop(action_id, None)
        (APPROVAL_DIR / f"{action_id}.json").unlink(missing_ok=True)
        return True

    def list_pending(self) -> list[dict]:
        """列出待审批操作"""
        return [v["entry"] for v in self._pending.values()]

    def _approve(self, action_id: str, entry: dict, execute_fn: Callable | None):
        entry["approved"] = True
        entry["status"] = "approved"
        self._pending.pop(action_id, None)
        (APPROVAL_DIR / f"{action_id}.json").unlink(missing_ok=True)
        if execute_fn:
            try:
                execute_fn()
            except Exception as e:
                print(f"  执行失败: {e}")
