"""AgentForge — 搜索结果缓存（文件级持久化）

缓存策略：
- 使用磁盘 JSON 文件，服务重启不丢失
- 默认 TTL 5 分钟
- 缓存键 = md5(engine + query.lower())
- 自动清理过期条目
"""

import json
import time
import hashlib
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "agentforge"
CACHE_TTL = 300  # 5 分钟


def _key(engine: str, query: str) -> str:
    raw = f"{engine}|{query.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.json"


def cache_get(engine: str, query: str) -> list | None:
    """查询缓存

    Returns:
        如果命中且未过期，返回数据列表；否则返回 None
    """
    fp = _path(_key(engine, query))
    if not fp.exists():
        return None
    try:
        entry = json.loads(fp.read_text(encoding="utf-8"))
        if time.time() - entry["ts"] < CACHE_TTL:
            return entry["data"]
    except (json.JSONDecodeError, KeyError):
        pass
    # 过期或损坏，删除
    fp.unlink(missing_ok=True)
    return None


def cache_set(engine: str, query: str, data: list):
    """写入缓存"""
    fp = _path(_key(engine, query))
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps({"data": data, "ts": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )


def cache_clear(engine: str | None = None, older_than: int | None = None):
    """清理缓存

    Args:
        engine: 指定引擎（如 "baidu"），仅清理该引擎缓存
        older_than: 清理超过 N 秒的缓存
    """
    if not CACHE_DIR.is_dir():
        return
    now = time.time()
    for fp in CACHE_DIR.glob("*.json"):
        if older_than:
            try:
                entry = json.loads(fp.read_text(encoding="utf-8"))
                if now - entry["ts"] < older_than:
                    continue
            except Exception:
                pass
        if engine and engine not in fp.stem:
            continue
        fp.unlink(missing_ok=True)
