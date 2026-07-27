"""OrchestratorRuntime — 数据模型 + SQLite 持久化"""

import sqlite3, json, time, uuid, threading
from pathlib import Path
from typing import Optional

DB_DIR = Path(__file__).parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "workflow.db"

_local = threading.local()


def _get_db():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _init_db(_local.conn)
    return _local.conn


def _init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT '',
            prompt TEXT DEFAULT '',
            status TEXT DEFAULT 'PENDING',
            plan TEXT DEFAULT '[]',
            current_step INTEGER DEFAULT 0,
            history TEXT DEFAULT '[]',
            result TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            timeout_minutes REAL DEFAULT 5.0,
            retry_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            idx INTEGER DEFAULT 0,
            action TEXT DEFAULT '',
            params TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            result TEXT DEFAULT '',
            started_at REAL,
            finished_at REAL,
            retries INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            step_idx INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at REAL,
            timeout_at REAL
        );
    """)
    conn.commit()


# ── Task ──

def create_task(user_id: str, prompt: str, timeout_minutes: float = 5.0) -> dict:
    tid = uuid.uuid4().hex[:12]
    now = time.time()
    conn = _get_db()
    conn.execute(
        "INSERT INTO tasks (id, user_id, prompt, status, created_at, updated_at, timeout_minutes) VALUES (?,?,?,?,?,?,?)",
        (tid, user_id, prompt, "PENDING", now, now, timeout_minutes),
    )
    conn.commit()
    return load_task(tid)


def load_task(task_id: str) -> Optional[dict]:
    conn = _get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return None
    t = dict(row)
    t["plan"] = json.loads(t.get("plan", "[]"))
    t["history"] = json.loads(t.get("history", "[]"))
    t["result"] = json.loads(t.get("result", "{}"))
    # 加载 steps
    steps = conn.execute("SELECT * FROM steps WHERE task_id=? ORDER BY idx", (task_id,)).fetchall()
    t["steps"] = [dict(s) for s in steps]
    for st in t["steps"]:
        if isinstance(st.get("params"), str):
            st["params"] = json.loads(st["params"])
        for k in ("started_at", "finished_at"):
            if k in st and isinstance(st[k], str):
                st[k] = float(st[k]) if st[k] else None
    # 加载 approvals
    apps = conn.execute("SELECT * FROM approvals WHERE task_id=? ORDER BY step_idx", (task_id,)).fetchall()
    t["approvals"] = [dict(a) for a in apps]
    return t


def save_task(task: dict):
    conn = _get_db()
    now = time.time()
    conn.execute(
        """UPDATE tasks SET status=?, plan=?, current_step=?, history=?, result=?, error=?, updated_at=?, retry_count=?
           WHERE id=?""",
        (task["status"], json.dumps(task.get("plan", [])), task.get("current_step", 0),
         json.dumps(task.get("history", [])), json.dumps(task.get("result", {})),
         task.get("error", ""), now, task.get("retry_count", 0), task["id"]),
    )
    # 保存 steps
    conn.execute("DELETE FROM steps WHERE task_id=?", (task["id"],))
    for s in task.get("steps", []):
        conn.execute(
            "INSERT INTO steps (task_id, idx, action, params, status, result, started_at, finished_at, retries) VALUES (?,?,?,?,?,?,?,?,?)",
            (task["id"], s.get("idx", 0), s.get("action", ""), json.dumps(s.get("params", {})),
             s.get("status", "pending"), s.get("result", ""), s.get("started_at"), s.get("finished_at"), s.get("retries", 0)),
        )
    conn.commit()


def list_tasks(user_id: str = "", limit: int = 20) -> list[dict]:
    conn = _get_db()
    if user_id:
        rows = conn.execute("SELECT * FROM tasks WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            plan = json.loads(d.get("plan", "[]"))
            d["steps"] = len(plan) if isinstance(plan, list) else 0
        except Exception:
            d["steps"] = 0
        d["steps_completed"] = d.get("current_step", 0)
        result.append(d)
    return result


def delete_task(task_id: str) -> bool:
    conn = _get_db()
    conn.execute("DELETE FROM steps WHERE task_id=?", (task_id,))
    conn.execute("DELETE FROM approvals WHERE task_id=?", (task_id,))
    c = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    return c.rowcount > 0


def recover_pending_tasks() -> list[dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status NOT IN ('DONE','FAILED','CANCELLED','TIMEOUT')"
    ).fetchall()
    recovered = []
    for r in rows:
        t = dict(r)
        if time.time() > t["created_at"] + t["timeout_minutes"] * 60:
            conn.execute("UPDATE tasks SET status='TIMEOUT' WHERE id=?", (t["id"],))
        else:
            recovered.append(t)
    conn.commit()
    return recovered


# ── Approval ──

def create_approval(task_id: str, step_idx: int, reason: str, timeout_minutes: float = 60) -> dict:
    conn = _get_db()
    now = time.time()
    conn.execute(
        "INSERT INTO approvals (task_id, step_idx, reason, status, created_at, timeout_at) VALUES (?,?,?,?,?,?)",
        (task_id, step_idx, reason, "pending", now, now + timeout_minutes * 60),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM approvals WHERE task_id=? AND step_idx=? ORDER BY id DESC LIMIT 1",
                        (task_id, step_idx)).fetchone()
    return dict(row) if row else {}


def approve_task(task_id: str, step_idx: int, granted: bool) -> Optional[dict]:
    conn = _get_db()
    conn.execute("UPDATE approvals SET status=? WHERE task_id=? AND step_idx=? AND status='pending'",
                 ("approved" if granted else "rejected", task_id, step_idx))
    conn.commit()
    return load_task(task_id)
