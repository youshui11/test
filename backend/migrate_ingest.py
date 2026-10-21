"""只追加导入任务表和 chunk_index，保留既有数据；python -m backend.migrate_ingest。"""
import asyncio
from sqlalchemy import inspect, text
from backend.config import Settings
from backend.database import Base, connect_database
import backend.models  # 注册全部表。


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


async def main():
    engine, _ = connect_database(Settings().database_url)
    try:
        async with engine.begin() as connection:
            await upgrade(connection)
        print('导入资料数据库升级完成，已有记录已保留')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
