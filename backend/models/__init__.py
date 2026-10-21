"""注册所有 ORM 表，供初始化和迁移使用。"""
from .user import User
from .session import Session
from .message import Message
from .knowledge import Upload, Knowledge
from .ingest import IngestJob

__all__ = ['User', 'Session', 'Message', 'Upload', 'Knowledge', 'IngestJob']
