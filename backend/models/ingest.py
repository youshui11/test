"""持久化导入任务；通过上传记录关联用户归属。"""
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base
from backend.models.user import utcnow


class IngestJob(Base):
    __tablename__ = 'ingest_jobs'
    __table_args__ = (CheckConstraint("status IN ('processing','completed','failed')"),)
    file_id: Mapped[str] = mapped_column(ForeignKey('uploads.file_id', ondelete='CASCADE'), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default='processing', index=True)
    chunk_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
