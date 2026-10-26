# 文件作用：在隔离 PostgreSQL schema 中验证旧表升级、向量入库及事务失败回滚。
# 关联关系：调用 manage_db.upgrade 和 DRAgent，需显式设置 TEST_DATABASE_URL。
"""隔离 PostgreSQL schema 验证旧表升级、真实向量入库与中途写入失败原子性。"""
import os
from uuid import uuid4
import pytest
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import async_sessionmaker
from backend.config import Settings
from backend.database import Base, connect_database
from backend.models import User, Upload, Knowledge, IngestJob
from backend.server import create_app
from scripts.manage_db import upgrade


@pytest.mark.asyncio
async def test_postgres_upgrade_and_atomic_ingestion(tmp_path):
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('设置 TEST_DATABASE_URL 运行真实 PostgreSQL 导入集成')
    if url == 'configured':
        url = Settings().database_url
    engine, _ = connect_database(url)
    schema = 'test_ingest_' + uuid4().hex
    created = False
    app = None
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        isolated = engine.execution_options(schema_translate_map={None: schema})
        factory = async_sessionmaker(isolated, expire_on_commit=False)
        async with isolated.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            user = User(username='ingest-user', password_hash='unused')
            db.add(user)
            await db.flush()
            user_id = user.id
            db.add(Upload(file_id='legacy', user_id=user_id, file_name='legacy.txt', storage_name='legacy.txt', size=1))
            await db.flush()
            db.add(Knowledge(file_id='legacy', user_id=user_id, file_name='legacy.txt', chunk_text='原有资料',
                             embedding=[1.] + [0.] * 1535, meta={'chunk': 0}))
            await db.commit()
        # 在本测试自建 schema 内模拟升级前表结构。
        async with isolated.begin() as conn:
            await conn.execute(text(f'ALTER TABLE "{schema}".knowledge_base DROP COLUMN chunk_index'))
            await conn.execute(text(f'DROP TABLE "{schema}".ingest_jobs'))
            await upgrade(conn)
            await upgrade(conn)
        async with factory() as db:
            old = await db.scalar(select(Knowledge).where(Knowledge.file_id == 'legacy'))
            assert old.chunk_text == '原有资料' and old.chunk_index == 0
        settings = Settings(_env_file=None, database_url=url, jwt_secret='x' * 32,
                            ingest_temp_dir=tmp_path / 'ingest', llm_config_source='env')
        app = create_app(settings)
        unused_engine = app.state.engine
        app.state.engine, app.state.db = isolated, factory
        await unused_engine.dispose()
        settings.ingest_temp_dir.mkdir()
        async def embed(texts):
            assert engine.pool.checkedout() == 0, '转换和 embedding 期间不应持有数据库连接'
            return [[1.] + [0.] * 1535 for _ in texts]
        app.state.embed = embed

        async def prepare(content):
            file_id = str(uuid4())
            folder = settings.ingest_temp_dir / file_id
            folder.mkdir()
            (folder / 'source.md').write_text(content, encoding='utf-8')
            async with factory() as db:
                db.add(Upload(file_id=file_id, user_id=user_id, file_name='source.md', storage_name='source.md',
                              size=len(content.encode()), status='processing'))
                await db.flush()
                db.add(IngestJob(file_id=file_id))
                await db.commit()
            return file_id

        good = await prepare('# 标题\n\n这是实际入库的知识资料。')
        await app.state.dr.run(good)
        async with factory() as db:
            job = await db.get(IngestJob, good)
            assert job.status == 'completed' and job.chunk_count == 1
            row = await db.scalar(select(Knowledge).where(Knowledge.file_id == good))
            assert len(row.embedding) == 1536 and row.user_id == user_id
            assert row.meta['heading_path'] == '标题'
        bad = await prepare('# 事务失败\n\n' + ''.join(f'第{i}条描述了不同资料中的业务知识。' for i in range(100)))
        async with isolated.begin() as conn:
            await conn.execute(text(f'''CREATE FUNCTION "{schema}".reject_second_chunk() RETURNS trigger
              LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.file_id = '{bad}' AND NEW.chunk_index = 1 THEN RAISE EXCEPTION 'controlled test failure'; END IF;
                RETURN NEW; END $$'''))
            await conn.execute(text(f'''CREATE TRIGGER fail_second BEFORE INSERT ON "{schema}".knowledge_base
              FOR EACH ROW EXECUTE FUNCTION "{schema}".reject_second_chunk()'''))
        await app.state.dr.run(bad)
        async with factory() as db:
            job = await db.get(IngestJob, bad)
            assert job.status == 'failed' and job.chunk_count == 0
            assert await db.scalar(select(func.count(Knowledge.id)).where(Knowledge.file_id == bad)) == 0
            assert await db.scalar(select(func.count(Knowledge.id)).where(Knowledge.file_id == 'legacy')) == 1
        assert list(settings.ingest_temp_dir.iterdir()) == []
    finally:
        if app is not None:
            await app.state.dr.close()
        if created:
            # 仅删除本测试创建的随机 schema，不接受外部路径或 schema 名称。
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()
