"""注册所有 ORM 表，供初始化和迁移使用。"""
from .user import User
from .chat import Session, Message
from .knowledge import Upload, Knowledge, IngestJob

__all__ = ['User', 'Session', 'Message', 'Upload', 'Knowledge', 'IngestJob']
