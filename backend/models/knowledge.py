"""上传元数据和 1536 维向量片段；所有者用于检索隔离。"""
from datetime import datetime
from sqlalchemy import ForeignKey, String, DateTime, JSON, Text, Index
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
