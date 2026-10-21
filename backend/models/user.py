"""用户表：账号统一小写，密码仅存哈希。"""
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (CheckConstraint("role IN ('user','admin')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default='user')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
