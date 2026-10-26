# 文件作用：验证后台导入接口、状态变化、失败回滚、用户隔离和中断恢复清理。
# 关联关系：联通 ingest.py、DRAgent 和临时数据库，复用 API 测试客户端。
"""导入 API 的异步状态、所有者隔离、原子入库和任务恢复。"""
import asyncio
import threading
import time
from sqlalchemy import select, func
from tests.helpers import account


def wait_job(client, file_id, headers):
    for _ in range(300):
        response = client.get('/api/ingest/status/' + file_id, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        if data['status'] != 'processing':
            return data
        time.sleep(0.01)
    raise AssertionError('导入任务未结束')


def test_ingest_returns_processing_then_completes_and_isolates(client):
    headers = account(client)
    release = threading.Event()
    async def convert(path):
        while not release.is_set():
            await asyncio.sleep(0.005)
        return '# 资料\n\n公司的成立时间是2020年。'
    async def embed(texts):
        return [[1.] + [0.] * 1535 for _ in texts]
    client.app.state.convert = convert
    client.app.state.embed = embed
    try:
        response = client.post('/api/ingest', headers=headers, files={'file': ('说明.md', b'content')})
        assert response.status_code == 202, response.text
        data = response.json()
        assert data['status'] == 'processing' and data['chunkCount'] == 0
        file_id = data['fileId']
        assert client.get('/api/ingest/status/' + file_id, headers=headers).json()['status'] == 'processing'
        other = account(client, 'bobby')
        assert client.get('/api/ingest/status/' + file_id, headers=other).status_code == 404
        assert client.get('/api/ingest/status/' + file_id).status_code == 401
    finally:
        release.set()
    completed = wait_job(client, file_id, headers)
    assert completed['status'] == 'completed' and completed['chunkCount'] == 1
    from backend.models import Knowledge
    async def read():
        async with client.app.state.db() as db:
            return (await db.scalars(select(Knowledge).where(Knowledge.file_id == file_id))).one()
    row = asyncio.run(read())
    assert row.chunk_index == 0 and row.meta['heading_path'] == '资料'
    assert row.meta['source_file'] == '说明.md'
    assert list(client.app.state.settings.ingest_temp_dir.iterdir()) == []


def test_ingest_failed_embedding_rolls_back_and_cleans(client):
    headers = account(client)
    async def broken(texts):
        raise RuntimeError('private upstream key and error')
    client.app.state.embed = broken
    response = client.post('/api/ingest', headers=headers, files={'file': ('bad.txt', b'hello')})
    assert response.status_code == 202, response.text
    data = wait_job(client, response.json()['fileId'], headers)
    assert data['status'] == 'failed' and data['chunkCount'] == 0
    assert data['error'] and 'private upstream' not in data['error']
    from backend.models import Knowledge
    async def count():
        async with client.app.state.db() as db:
            return await db.scalar(select(func.count(Knowledge.id)))
    assert asyncio.run(count()) == 0
    assert list(client.app.state.settings.ingest_temp_dir.iterdir()) == []


def test_ingest_file_validation_and_body_limit(client):
    headers = account(client)
    assert client.post('/api/ingest', headers=headers, files={'file': ('bad.exe', b'x')}).status_code == 415
    assert client.post('/api/ingest', headers=headers, files={'file': ('empty.txt', b'')}).status_code == 422
    client.app.state.settings.max_ingest_bytes = 5
    assert client.post('/api/ingest', headers=headers, files={'file': ('big.txt', b'123456')}).status_code == 413
    headers['Content-Length'] = str(100 * 1024 * 1024)
    assert client.post('/api/ingest', headers=headers, content=b'body').status_code == 413


def test_recover_interrupted_task(client):
    from uuid import uuid4
    from backend.models import User, Upload, IngestJob
    headers = account(client)
    file_id = str(uuid4())
    folder = client.app.state.settings.ingest_temp_dir / file_id
    folder.mkdir()
    (folder / 'source.txt').write_text('interrupted', encoding='utf-8')
    async def prepare_and_recover():
        async with client.app.state.db() as db:
            user = await db.scalar(select(User).where(User.username == 'alice'))
            db.add(Upload(file_id=file_id, user_id=user.id, file_name='source.txt', storage_name='source.txt', size=11, status='processing'))
            await db.flush()
            db.add(IngestJob(file_id=file_id))
            await db.commit()
        await client.app.state.dr.recover()
    asyncio.run(prepare_and_recover())
    data = client.get('/api/ingest/status/' + file_id, headers=headers).json()
    assert data['status'] == 'failed' and '中断' in data['error']
    assert not folder.exists()


def test_shutdown_cleans_task_cancelled_before_first_execution(client):
    from uuid import uuid4
    from backend.models import User, Upload, IngestJob
    headers = account(client)
    file_id = str(uuid4())
    folder = client.app.state.settings.ingest_temp_dir / file_id
    folder.mkdir()
    (folder / 'source.txt').write_text('queued', encoding='utf-8')
    async def prepare_and_close():
        async with client.app.state.db() as db:
            user = await db.scalar(select(User).where(User.username == 'alice'))
            db.add(Upload(file_id=file_id, user_id=user.id, file_name='source.txt', storage_name='source.txt', size=6, status='processing'))
            await db.flush()
            db.add(IngestJob(file_id=file_id))
            await db.commit()
        client.app.state.dr.start(file_id)
        await client.app.state.dr.close()
    asyncio.run(prepare_and_close())
    data = client.get('/api/ingest/status/' + file_id, headers=headers).json()
    assert data['status'] == 'failed' and not folder.exists()


def test_recovery_only_cleans_marked_orphan_directories(client):
    from uuid import uuid4
    root = client.app.state.settings.ingest_temp_dir
    orphan = root / str(uuid4())
    orphan.mkdir()
    (orphan / '.ingest-owner').write_text('ingest-v1:' + orphan.name, encoding='utf-8')
    (orphan / 'source.txt').write_text('private source', encoding='utf-8')
    user_folder = root / str(uuid4())
    user_folder.mkdir()
    (user_folder / 'keep.txt').write_text('user file', encoding='utf-8')
    asyncio.run(client.app.state.dr.recover())
    assert not orphan.exists()
    assert (user_folder / 'keep.txt').read_text(encoding='utf-8') == 'user file'
