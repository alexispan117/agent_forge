"""AgentForge — 数据模型

用户系统 + 对话记录 + 反馈。
本地开发: SQLite
生产部署: MySQL（仅需改 DATABASE_URL 环境变量）
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex[:16]


def _utcnow() -> datetime:
    """Naive UTC 时间（datetime.utcnow 已于 Python 3.12 弃用）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ═══════════════════════════════════════════════
# 用户
# ═══════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    avatar_url: Mapped[str] = mapped_column(String(512), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


# ═══════════════════════════════════════════════
# 对话记录
# ═══════════════════════════════════════════════

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(16), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    agent: Mapped[str] = mapped_column(String(32), default="chat")  # chat / search
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    token_cost: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan",
                            order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(16), ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[str] = mapped_column(Text, default="")  # JSON
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    conversation = relationship("Conversation", back_populates="messages")


# ═══════════════════════════════════════════════
# 反馈
# ═══════════════════════════════════════════════

class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(16), ForeignKey("users.id"), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(16), ForeignKey("messages.id"), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, default=0)  # -1: 踩, 0: 无, 1: 赞
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
