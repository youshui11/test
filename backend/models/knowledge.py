# 文件作用：定义附件元数据、知识片段及导入任务表，并声明向量检索索引。
# 关联关系：连接普通附件、DR 导入、CX 检索和 QWJS 全文读取，统一保存入库资料。
"""上传元数据和共享的 1536 维知识片段；所有者记录来源及原件权限。"""
from datetime import datetime
from sqlalchemy import ForeignKey, String, DateTime, JSON, Text, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from backend.database import Base
from .user import utcnow


class Upload(Base):
    __tablename__ = 'uploads'
    file_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    file_name: Mapped[str] = mapped_column(String(200))
    storage_name: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default='ready')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Knowledge(Base):
    __tablename__ = 'knowledge_base'
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey('uploads.file_id', ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    file_name: Mapped[str] = mapped_column(String(200))
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int | None] = mapped_column(nullable=True)
    embedding: Mapped[list] = mapped_column(JSON().with_variant(Vector(1536), 'postgresql'))
    meta: Mapped[dict] = mapped_column('metadata', JSON().with_variant(JSONB(), 'postgresql'), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# HNSW 可在空表建立；相比 IVFFlat，不需要预先训练聚类中心。
Index('ix_knowledge_embedding_cosine', Knowledge.embedding,
      postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'}).ddl_if(dialect='postgresql')


class IngestJob(Base):
    __tablename__ = 'ingest_jobs'
    __table_args__ = (CheckConstraint("status IN ('processing','completed','failed')"),)
    file_id: Mapped[str] = mapped_column(ForeignKey('uploads.file_id', ondelete='CASCADE'), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default='processing', index=True)
    chunk_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
