# 文件作用：定义 ORM Base，创建异步数据库引擎、会话工厂和请求级数据库依赖。
# 关联关系：供数据模型、业务接口、应用入口及维护命令复用，不自动修改表结构。
"""异步数据库引擎和请求级会话；不在启动时隐式更改表结构。"""
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from fastapi import Request


class Base(DeclarativeBase):
    pass


def connect_database(url):
    engine = create_async_engine(url, pool_pre_ping=True)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine.sync_engine, 'connect')
        def enable_foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request):
    async with request.app.state.db() as db:
        yield db
