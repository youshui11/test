"""真实 pgvector 集成；仅在指定 TEST_DATABASE_URL 时创建并清理随机测试 schema。"""
import os
from uuid import uuid4
import pytest
from sqlalchemy import text, select, delete
from backend.config import Settings
from backend.database import Base, connect_database
from backend.models import User, Session, Message, Upload, Knowledge
from backend.services.rag import retrieve
from backend.services.chat import generation_lock


@pytest.mark.asyncio
async def test_anyio_cancelled_generation_releases_lock_and_pool_connection(monkeypatch):
    """断流的 AnyIO level cancellation 不能中断解锁或连接归还。"""
    import anyio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('需要 TEST_DATABASE_URL')
    if url == 'configured':
        url = Settings().database_url
    engine = create_async_engine(url, pool_size=1, max_overflow=0, pool_timeout=0.2)
    observer = create_async_engine(url)
    original_execute = AsyncConnection.execute
    async def checkpoint_before_unlock(connection, statement, *args, **kwargs):
        if 'pg_advisory_unlock(' in str(statement):
            # 放大真实网络 I/O 本来就有的取消窗口，保证回归稳定。
            await anyio.sleep(0.02)
        return await original_execute(connection, statement, *args, **kwargs)
    monkeypatch.setattr(AsyncConnection, 'execute', checkpoint_before_unlock)
    try:
        with anyio.CancelScope() as scope:
            async with generation_lock(engine, 'cancel-test-' + uuid4().hex) as connection:
                pid = await connection.scalar(text('SELECT pg_backend_pid()'))
                await connection.commit()
                scope.cancel()
                await anyio.sleep(0)
        # 若后台释放任务脱离取消作用域继续运行，也须在检查前给它完成机会。
        await anyio.sleep(0.05)
        async with observer.connect() as connection:
            remaining = await connection.scalar(text(
                "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND pid=:pid AND granted"
            ), {'pid': pid})
        assert remaining == 0, '取消后的 PostgreSQL 会话残留 advisory lock'
        assert engine.pool.checkedout() == 0, '取消后锁连接未归还连接池'
        async with engine.connect() as connection:
            assert await connection.scalar(text('SELECT 1')) == 1
    finally:
        await engine.dispose()
        await observer.dispose()


@pytest.mark.asyncio
async def test_lock_connection_can_be_reused_with_single_connection_pool():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('需要 TEST_DATABASE_URL')
    if url == 'configured':
        url = Settings().database_url
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    engine = create_async_engine(url, pool_size=1, max_overflow=0, pool_timeout=0.2)
    try:
        async with generation_lock(engine, 'pool-test-' + uuid4().hex) as connection:
            async with AsyncSession(bind=connection) as db:
                assert await db.scalar(text('SELECT 42')) == 42
        async with engine.connect() as connection:
            assert await connection.scalar(text('SELECT 43')) == 43
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pgvector_ranking_isolation_cascade_and_lock():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('设置 TEST_DATABASE_URL 才运行真实 PostgreSQL 集成测试')
    if url == 'configured':
        url = Settings().database_url
    engine, _ = connect_database(url)
    schema = 'test_backend_' + uuid4().hex
    created = False
    try:
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'")), \
                '请先由超级用户在目标数据库启用 vector 扩展'
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        isolated = engine.execution_options(schema_translate_map={None: schema})
        from sqlalchemy.ext.asyncio import async_sessionmaker
        factory = async_sessionmaker(isolated, expire_on_commit=False)
        async with isolated.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            a = User(username='alice', password_hash='unused')
            b = User(username='bobby', password_hash='unused')
            db.add_all([a, b])
            await db.flush()
            db.add_all([Upload(file_id='a', user_id=a.id, file_name='a.txt', storage_name='a', size=1),
                        Upload(file_id='b', user_id=b.id, file_name='b.txt', storage_name='b', size=1)])
            await db.flush()
            db.add_all([Knowledge(file_id='a', user_id=a.id, file_name='a.txt', chunk_text='related', embedding=[1., 0.] + [0.] * 1534),
                        Knowledge(file_id='a', user_id=a.id, file_name='a.txt', chunk_text='unrelated', embedding=[0., 1.] + [0.] * 1534),
                        Knowledge(file_id='b', user_id=b.id, file_name='b.txt', chunk_text='private', embedding=[1., 0.] + [0.] * 1534)])
            db.add(Session(session_id='session-test', user_id=a.id))
            await db.flush()
            db.add(Message(msg_id='msg-test', session_id='session-test', role='user', content='test'))
            await db.commit()
            async def embedding(texts):
                return [[1., 0.] + [0.] * 1534]
            result = await retrieve(db, a.id, 'question', [], embedding)
            assert {item['text'] for item in result[:2]} == {'related', 'private'}
            assert result[-1]['text'] == 'unrelated'
            selected = await retrieve(db, a.id, 'question', ['b'], embedding)
            assert [item['text'] for item in selected] == ['private']
            await db.execute(delete(Session).where(Session.session_id == 'session-test'))
            await db.commit()
            assert await db.scalar(select(Message.id)) is None
        async with generation_lock(engine, schema):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as error:
                async with generation_lock(engine, schema):
                    pytest.fail('同一会话不应同时持有两把锁')
            assert error.value.status_code == 409
        async with generation_lock(engine, schema):
            pass  # 已释放，可再次获取。
    finally:
        if created:
            # 目标由本测试生成，不接受用户输入；仅删除自己的随机测试 schema。
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()
