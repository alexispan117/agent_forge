"""AgentForge — 工作状态 Checkpoint

参考 MokioClaw 的 light checkpoint 模式。
在关键步骤保存工作状态，中断后可恢复。
"""

import json
import time
from pathlib import Path

CHECKPOINT_DIR = Path.home() / ".cache" / "agentforge" / "checkpoints"
CHECKPOINT_VERSION = "1.0"


def save(session_id: str, state: dict) -> str:
    """保存 Checkpoint

    Args:
        session_id: 会话标识
        state: 需要保存的状态数据

    Returns:
        checkpoint 文件路径
    """
    fp = CHECKPOINT_DIR / f"{session_id}.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": CHECKPOINT_VERSION,
        "session_id": session_id,
        "ts": time.time(),
        "state": state,
    }
    fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(fp)


def load(session_id: str) -> dict | None:
    """加载 Checkpoint

    Returns:
        {"version": str, "session_id": str, "ts": float, "state": dict}
        或 None（不存在或已过期）
    """
    fp = CHECKPOINT_DIR / f"{session_id}.json"
    if not fp.exists():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        # 24 小时后过期
        if time.time() - data.get("ts", 0) > 86400:
            fp.unlink(missing_ok=True)
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def remove(session_id: str):
    """删除 Checkpoint"""
    fp = CHECKPOINT_DIR / f"{session_id}.json"
    fp.unlink(missing_ok=True)


def list_sessions() -> list[dict]:
    """列出所有活跃的 Checkpoint 会话"""
    if not CHECKPOINT_DIR.is_dir():
        return []
    sessions = []
    now = time.time()
    for fp in sorted(CHECKPOINT_DIR.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            age = now - data.get("ts", 0)
            if age < 86400:
                sessions.append({
                    "session_id": data.get("session_id", fp.stem),
                    "age_s": round(age),
                    "path": str(fp),
                })
        except Exception:
            pass
    return sessions
