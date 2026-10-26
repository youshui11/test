# 文件作用：统一注册和导出所有 ORM 模型，确保完整元数据可用于建表和升级。
# 关联关系：集中导出 User、Session、Message、Upload、Knowledge、IngestJob。
"""注册所有 ORM 表，供初始化和迁移使用。"""
from .user import User
from .chat import Session, Message
from .knowledge import Upload, Knowledge, IngestJob

__all__ = ['User', 'Session', 'Message', 'Upload', 'Knowledge', 'IngestJob']
