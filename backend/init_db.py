"""显式初始化表和管理员；python -m backend.init_db --admin admin。"""
import argparse
import asyncio
import getpass
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from backend.config import Settings
from backend.database import Base, connect_database
from backend.models import User
from backend.schemas import Credentials
from backend.services.auth import passwords


async def initialize(settings, admin_name=None, password=None):
    engine, factory = connect_database(settings.database_url)
    try:
        if engine.dialect.name != 'postgresql':
            raise ValueError('正式初始化仅支持 PostgreSQL/pgvector')
        async with engine.begin() as connection:
            if not await connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'")):
                try:
                    await connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
                except DBAPIError as exc:
                    raise ValueError('无法启用 vector；请用 PostgreSQL 超级用户连接目标库，执行 CREATE EXTENSION IF NOT EXISTS vector;') from exc
            await connection.run_sync(Base.metadata.create_all)
        if admin_name:
            credentials = Credentials(username=admin_name, password=password)
            async with factory() as db:
                existing = await db.scalar(select(User).where(User.username == credentials.username.lower()))
                if existing:
                    raise ValueError('账号已存在；不会自动提权或重置密码')
                db.add(User(username=credentials.username.lower(), password_hash=passwords.hash(credentials.password), role='admin'))
                await db.commit()
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description='创建数据库表和可选管理员（数据库需预先存在）')
    parser.add_argument('--admin', help='新建管理员账号，密码交互输入')
    args = parser.parse_args()
    password = None
    if args.admin:
        password = getpass.getpass('管理员密码：')
        if password != getpass.getpass('再次输入：'):
            raise SystemExit('两次密码不一致')
    try:
        asyncio.run(initialize(Settings(), args.admin, password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print('数据库初始化完成')


if __name__ == '__main__':
    main()
