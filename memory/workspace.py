"""AgentForge — 上下文工程：工作记忆（Notepad / Todo）

参考教程第9章上下文工程 + MokioClaw 的 Notepad/TODO 模式。
"""

import json
from pathlib import Path
from datetime import datetime

WORK_DIR = Path.home() / ".cache" / "agentforge" / "workspace"


class Notepad:
    """工作笔记（Notepad）：记录发现、决策和重要信息

    类似于 MokioClaw 的 NOTEPAD.md。
    长期保留，不会被压缩清除。
    """

    def __init__(self, session_id: str = "default"):
        self._fp = WORK_DIR / session_id / "notepad.json"
        self._fp.parent.mkdir(parents=True, exist_ok=True)
        self._notes: list[dict] = self._load()

    def write(self, category: str, content: str):
        """写入一条笔记

        Args:
            category: 分类（decision / finding / risk / next_step）
            content: 笔记内容
        """
        self._notes.append({
            "category": category,
            "content": content,
            "ts": datetime.now().isoformat(),
        })
        self._save()

    def read(self, category: str | None = None, last_n: int = 20) -> list[dict]:
        """读取笔记"""
        notes = self._notes if category is None else \
                [n for n in self._notes if n["category"] == category]
        return notes[-last_n:]

    def summary(self) -> str:
        """生成笔记摘要"""
        if not self._notes:
            return "(无笔记)"
        categories = {}
        for n in self._notes:
            categories.setdefault(n["category"], []).append(n["content"])
        parts = []
        for cat, items in categories.items():
            parts.append(f"[{cat}] {'; '.join(items[-3:])}")
        return "\n".join(parts)

    def clear(self):
        self._notes = []
        self._save()

    def _load(self) -> list:
        if self._fp.exists():
            try:
                return json.loads(self._fp.read_text())
            except Exception:
                pass
        return []

    def _save(self):
        self._fp.write_text(json.dumps(self._notes, ensure_ascii=False))


class TodoList:
    """任务清单（Todo）：记录当前目标和进度

    类似于 MokioClaw 的 TODO.md。
    """

    def __init__(self, session_id: str = "default"):
        self._fp = WORK_DIR / session_id / "todo.json"
        self._fp.parent.mkdir(parents=True, exist_ok=True)
        self._items: list[dict] = self._load()

    def add(self, description: str, status: str = "pending"):
        """添加任务"""
        self._items.append({
            "id": len(self._items) + 1,
            "description": description,
            "status": status,
            "ts": datetime.now().isoformat(),
        })
        self._save()

    def update(self, todo_id: int, status: str):
        """更新任务状态"""
        for item in self._items:
            if item["id"] == todo_id:
                item["status"] = status
                break
        self._save()

    def list(self, status: str | None = None) -> list[dict]:
        """列出任务"""
        if status:
            return [t for t in self._items if t["status"] == status]
        return list(self._items)

    def progress(self) -> str:
        """生成进度摘要"""
        if not self._items:
            return "(无任务)"
        total = len(self._items)
        done = sum(1 for t in self._items if t["status"] == "completed")
        pending = total - done
        return f"进度: {done}/{total} 完成 ({pending} 待处理)"

    def clear(self):
        self._items = []
        self._save()

    def _load(self) -> list:
        if self._fp.exists():
            try:
                return json.loads(self._fp.read_text())
            except Exception:
                pass
        return []

    def _save(self):
        self._fp.write_text(json.dumps(self._items, ensure_ascii=False))
