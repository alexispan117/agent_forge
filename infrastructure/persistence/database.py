"""AgentForge — 数据库引擎（异步外观 v2）

设计：
- 底层保持单一同步 Engine（SQLite，WAL 模式），杜绝 async/sync 双轨重复
- AsyncSession 用 asyncio.to_thread 把阻塞 I/O 移交线程池，对 FastAPI 暴露全异步接口
- 业务侧统一 `async with AsyncSessionLocal() as db:` 或 `Depends(get_db)` 使用
- 后续迁移 aiosqlite 时仅需替换本文件，crud/路由零改动
"""

import asyncio
import os
from pathlib import Path

import sqlalchemy
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

DB_PATH = Path(__file__).parent.parent.parent / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = sqlalchemy.create_engine(
    DB_URL, echo=False, connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    """WAL 模式：读不阻塞写、写不阻塞读（多线程/多容器并发安全）。"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


# expire_on_commit=False：commit 后对象属性保持可用，避免事件循环线程里的懒加载 IO
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class AsyncSession:
    """同步 Session 的异步外观：阻塞操作移交线程池，纯内存操作直接转发。"""

    def __init__(self, sync_session):
        self._sync = sync_session

    async def __aenter__(self) -> "AsyncSession":
        return self

    async def __aexit__(self, *exc) -> None:
        await asyncio.to_thread(self._sync.close)

    async def execute(self, statement, *args, **kwargs):
        return await asyncio.to_thread(self._sync.execute, statement, *args, **kwargs)

    def add(self, instance) -> None:  # 纯内存操作，无需线程
        self._sync.add(instance)

    async def commit(self) -> None:
        await asyncio.to_thread(self._sync.commit)

    async def refresh(self, instance) -> None:
        await asyncio.to_thread(self._sync.refresh, instance)

    async def close(self) -> None:
        await asyncio.to_thread(self._sync.close)


def AsyncSessionLocal() -> AsyncSession:
    """异步会话工厂：`async with AsyncSessionLocal() as db:`"""
    return AsyncSession(SessionLocal())


async def get_db():
    """FastAPI 依赖注入用异步会话。"""
    db = SessionLocal()
    try:
        yield AsyncSession(db)
    finally:
        await asyncio.to_thread(db.close)


def init_db() -> None:
    """初始化数据库表（同步，供启动钩子/CLI 调用）。"""
    from infrastructure.persistence.orm_models import Base
    Base.metadata.create_all(bind=engine)


async def ainit_db() -> None:
    """初始化数据库表（异步，供 FastAPI lifespan 调用）。"""
    await asyncio.to_thread(init_db)
