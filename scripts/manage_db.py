# 文件作用：提供 check、init、upgrade 三种显式数据库维护操作。
# 关联关系：通过 python -m scripts.manage_db 运行，复用 config、database、models 和认证密码哈希服务。
"""显式数据库维护：python -m scripts.manage_db {check,init,upgrade}。"""
import argparse
import asyncio
import getpass
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from backend.config import Settings
from backend.database import Base, connect_database
from backend.models import User
from backend.schemas import Credentials
from backend.services.auth import passwords


async def check_database(settings):
    engine, _ = connect_database(settings.database_url)
    try:
        async with engine.connect() as conn:
            version = await conn.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            tables = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
            print('Database reachable; pgvector:', version or 'not enabled')
            print('Business tables present:', sorted(set(tables) & {'users', 'sessions', 'messages', 'uploads', 'knowledge_base'}))
    finally:
        await engine.dispose()


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


async def upgrade(connection):
    await connection.run_sync(Base.metadata.create_all)
    schema = connection.sync_connection.get_execution_options().get('schema_translate_map', {}).get(None)
    columns = await connection.run_sync(lambda sync: inspect(sync).get_columns('knowledge_base', schema=schema))
    quote = connection.dialect.identifier_preparer.quote
    table = (quote(schema) + '.' if schema else '') + quote('knowledge_base')
    if 'chunk_index' not in {column['name'] for column in columns}:
        await connection.execute(text(f'ALTER TABLE {table} ADD COLUMN chunk_index INTEGER'))
    # 为旧数据回填文件内顺序，仅处理缺少索引的记录，不重写新任务索引。
    if connection.dialect.name == 'postgresql':
        await connection.execute(text(f'''WITH positions AS (
            SELECT id, row_number() OVER (PARTITION BY file_id ORDER BY id) - 1 AS position FROM {table}
        ) UPDATE {table} AS target SET chunk_index=positions.position
          FROM positions WHERE target.id=positions.id AND target.chunk_index IS NULL'''))


async def upgrade_database(settings):
    engine, _ = connect_database(settings.database_url)
    try:
        async with engine.begin() as connection:
            await upgrade(connection)
        print('导入资料数据库升级完成，已有记录已保留')
    finally:
        await engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description='数据库诊断、显式初始化与保留数据的导入升级')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='只读检查数据库连接、vector 扩展和业务表')
    initialization = commands.add_parser('init', help='创建数据库表和可选管理员（数据库需预先存在）')
    initialization.add_argument('--admin', help='新建管理员账号，密码交互输入')
    commands.add_parser('upgrade', help='补充导入任务表和片段索引，保留既有资料')
    args = parser.parse_args(argv)

    password = None
    if args.command == 'init' and args.admin:
        password = getpass.getpass('管理员密码：')
        if password != getpass.getpass('再次输入：'):
            raise SystemExit('两次密码不一致')
    try:
        settings = Settings()
        if args.command == 'init':
            asyncio.run(initialize(settings, args.admin, password))
            print('数据库初始化完成')
        else:
            operation = check_database if args.command == 'check' else upgrade_database
            asyncio.run(operation(settings))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    main()

