"""消息表；外键级联删除，附件引用保存为 JSON。"""
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, JSON, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base
from .user import utcnow


class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (CheckConstraint("role IN ('user','ai')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    msg_id: Mapped[str] = mapped_column(String(64), unique=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.session_id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    file_ids: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), 'postgresql'), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
