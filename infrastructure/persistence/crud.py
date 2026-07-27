"""AgentForge — 数据库 CRUD 操作（全异步 v2）

变更：
- 全部函数 async 化（配合 AsyncSession，阻塞 I/O 在线程池执行）
- 密码哈希 SHA256+salt → bcrypt（旧格式哈希仍可校验，平滑迁移）
- datetime.utcnow（已弃用）→ _utcnow()
- 新增 get_recent_messages / add_feedback / get_feedback_stats
"""

from datetime import datetime, timezone
from typing import Optional

import bcrypt
from sqlalchemy import select, func, desc

from infrastructure.persistence.orm_models import User, Conversation, Message, Feedback


def _utcnow() -> datetime:
    """Naive UTC 时间（SQLite DateTime 兼容）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── 密码（bcrypt，兼容旧 SHA256 格式校验）──

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        if hashed.startswith("$2"):  # bcrypt 格式
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        # 兼容旧格式 "salt:sha256_hex"
        import hashlib
        salt, h = hashed.split(":")
        return h == hashlib.sha256((salt + plain).encode()).hexdigest()
    except Exception:
        return False


# ── 用户 ──

async def create_user(db, username: str, email: str, password: str, display_name: str = "") -> User:
    user = User(username=username, email=email, hashed_password=_hash_password(password),
                display_name=display_name or username)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_username(db, username: str) -> Optional[User]:
    r = await db.execute(select(User).where(User.username == username))
    return r.scalar_one_or_none()


async def get_user_by_email(db, email: str) -> Optional[User]:
    r = await db.execute(select(User).where(User.email == email))
    return r.scalar_one_or_none()


async def get_user_by_id(db, user_id: str) -> Optional[User]:
    r = await db.execute(select(User).where(User.id == user_id))
    return r.scalar_one_or_none()


async def get_user_stats(db, user_id: str) -> dict:
    r1 = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
    )
    conv_count = r1.scalar() or 0
    r2 = await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id)
    )
    msg_count = r2.scalar() or 0
    return {"total_conversations": conv_count, "total_messages": msg_count, "total_token_cost": 0.0}


# ── 对话 ──

async def create_conversation(db, user_id: str, title: str = "新对话", agent: str = "chat") -> Conversation:
    conv = Conversation(user_id=user_id, title=title, agent=agent)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_user_conversations(db, user_id: str, limit: int = 20) -> list[Conversation]:
    r = await db.execute(
        select(Conversation).where(Conversation.user_id == user_id, Conversation.is_active == True)
        .order_by(desc(Conversation.updated_at)).limit(limit)
    )
    return list(r.scalars().all())


async def get_conversation(db, conv_id: str) -> Optional[Conversation]:
    r = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    return r.scalar_one_or_none()


async def add_message(db, conversation_id: str, role: str, content: str, sources: str = "",
                      latency_ms: int = 0, tokens: int = 0) -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content,
                  sources=sources, latency_ms=latency_ms, tokens=tokens)
    db.add(msg)
    await db.commit()
    c = await get_conversation(db, conversation_id)
    if c:
        c.updated_at = _utcnow()
        await db.commit()
    return msg


async def get_recent_messages(db, conversation_id: str, limit: int = 20) -> list[Message]:
    """显式查询最近消息（避免在模板层触发懒加载 IO）。"""
    r = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at)).limit(limit)
    )
    msgs = list(r.scalars().all())
    msgs.reverse()  # 恢复时间正序
    return msgs


# ── 反馈 ──

async def add_feedback(db, user_id: str, message_id: str, rating: int = 0, comment: str = "") -> Feedback:
    fb = Feedback(user_id=user_id or "anonymous", message_id=message_id or "unknown",
                  rating=rating, comment=comment)
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return fb


async def get_feedback_stats(db) -> dict:
    r_total = await db.execute(select(func.count(Feedback.id)))
    total = r_total.scalar() or 0
    r_likes = await db.execute(select(func.count(Feedback.id)).where(Feedback.rating == 1))
    likes = r_likes.scalar() or 0
    r_dislikes = await db.execute(select(func.count(Feedback.id)).where(Feedback.rating == -1))
    dislikes = r_dislikes.scalar() or 0
    return {"total": total, "likes": likes, "dislikes": dislikes, "score": likes - dislikes}
