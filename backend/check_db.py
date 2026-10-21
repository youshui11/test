"""只读数据库诊断；不打印连接凭据。python -m backend.check_db。"""
import asyncio
from sqlalchemy import text, inspect
from backend.config import Settings
from backend.database import connect_database


async def main():
    engine, _ = connect_database(Settings().database_url)
    try:
        async with engine.connect() as conn:
            version = await conn.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            tables = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
            print('Database reachable; pgvector:', version or 'not enabled')
            print('Business tables present:', sorted(set(tables) & {'users', 'sessions', 'messages', 'uploads', 'knowledge_base'}))
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
