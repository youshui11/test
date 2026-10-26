"""验证真实路由、事务和用户隔离；外部模型使用确定性替身。"""
import importlib.util
import pytest


def test_backend_exists():
    assert importlib.util.find_spec('backend.server') is not None, '后端入口尚未实现'


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    from backend.config import Settings
    from backend.server import create_app
    app = create_app(Settings(database_url=f'sqlite+aiosqlite:///{tmp_path / "test.db"}',
                              llm_config_source='env', llm_api_key='',
                              jwt_secret='test-secret-with-at-least-32-characters',
                              upload_dir=tmp_path / 'uploads', ingest_temp_dir=tmp_path / 'ingest'))
    import asyncio
    from backend.database import Base
    async def setup():
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(setup())
    with TestClient(app) as connection:
        yield connection


def account(client, name='alice'):
    response = client.post('/api/users', json={'username': name, 'password': 'password123'})
    assert response.status_code == 201, response.text
    response = client.post('/api/login', json={'username': name, 'password': 'password123'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_frontend_files_served_from_fronted(client):
    from backend.config import ROOT
    for name, url in [('index.html', '/'), ('api.js', '/api.js'), ('app.js', '/app.js'), ('style.css', '/style.css')]:
        response = client.get(url + '?v=directory-move')
        assert response.status_code == 200
        assert response.content == (ROOT / 'fronted' / name).read_bytes()
        assert not (ROOT / name).exists()
    # 移动目录后仍只公开明确列出的资源，不把整个项目作为静态目录。
    assert client.get('/backend/.env').status_code == 404


def test_auth_and_isolation(client):
    a = account(client)
    assert client.post('/api/users', json={'username': 'ALICE', 'password': 'password123'}).status_code == 409
    assert client.post('/api/users', json={'username': 'evil', 'password': 'password123', 'role': 'admin'}).status_code == 422
    assert client.post('/api/login', json={'username': 'alice', 'password': 'wrong'}).status_code == 401
    assert client.get('/api/sessions').status_code == 401
    assert client.get('/api/sessions', headers={'Authorization': 'Bearer broken'}).status_code == 401
    session = client.post('/api/sessions', headers=a, json={}).json()['sessionId']
    b = account(client, 'bobby')
    assert client.get(f'/api/sessions/{session}/messages', headers=b).status_code == 404
    assert client.post(f'/api/sessions/{session}/messages', headers=b, json={'content': 'hello'}).status_code == 404
    assert client.get('/api/admin/sessions', headers=a).status_code == 403
    assert client.delete(f'/api/admin/sessions/{session}', headers=a).status_code == 403
    assert len(client.get('/api/sessions', headers=a).json()) == 1
    assert client.get('/api/sessions', headers=b).json() == []


def test_stream_persistence_and_failure(client):
    headers = account(client)
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    async def answer(*args):
        yield '你好'
        yield '世界'
    client.app.state.answer = answer
    result = client.post(f'/api/sessions/{session}/messages', headers=headers, json={'content': '问题'})
    assert result.headers['content-type'].startswith('text/event-stream')
    assert 'event: delta' in result.text and 'event: done' in result.text
    messages = client.get(f'/api/sessions/{session}/messages', headers=headers).json()
    assert [m['content'] for m in messages] == ['问题', '你好世界']
    assert client.get('/api/sessions', headers=headers).json()[0]['title'] == '问题'
    async def broken(*args):
        yield 'partial'
        raise RuntimeError('secret upstream error')
    client.app.state.answer = broken
    result = client.post(f'/api/sessions/{session}/messages', headers=headers, json={'content': '失败'})
    assert 'event: error' in result.text and 'event: done' not in result.text
    assert 'secret upstream error' not in result.text
    assert len(client.get(f'/api/sessions/{session}/messages', headers=headers).json()) == 2


def test_upload_ownership_and_cleanup(client):
    a = account(client)
    async def embed(texts):
        return [[1.0] + [0.0] * 1535 for _ in texts]
    client.app.state.embed = embed
    upload = client.post('/api/upload', headers=a, files={'file': ('notes.txt', '公司资料'.encode())})
    assert upload.status_code == 201, upload.text
    file = upload.json()
    assert client.get(file['url'], headers=a).content == '公司资料'.encode()
    b = account(client, 'bobby')
    assert client.get(file['url'], headers=b).status_code == 404
    session = client.post('/api/sessions', headers=b, json={}).json()['sessionId']
    assert client.post(f'/api/sessions/{session}/messages', headers=b,
                       json={'content': '窃取', 'fileIds': [file['fileId']]}).status_code == 404
    assert client.post('/api/upload', headers=a, files={'file': ('script.exe', b'bad')}).status_code == 415
    assert client.post('/api/upload', headers=a, files={'file': ('empty.txt', b' ')}).status_code == 422
    async def broken(texts):
        raise RuntimeError('embedding failure')
    client.app.state.embed = broken
    before = set(client.app.state.settings.upload_dir.iterdir())
    assert client.post('/api/upload', headers=a, files={'file': ('bad.txt', b'text')}).status_code == 502
    assert set(client.app.state.settings.upload_dir.iterdir()) == before


def test_static_files_are_allowlisted(client):
    assert client.get('/').status_code == 200
    for path in ['/backend/.env', '/.git/config', '/server.py', '/requirements.txt']:
        assert client.get(path).status_code == 404


def test_chunking():
    from agent.tools.attachments import chunk_text
    chunks = chunk_text('中' * 1201)
    assert list(map(len, chunks)) == [500, 500, 201]
    assert ''.join(chunks) == '中' * 1201


def test_admin_can_read_and_delete_with_cascade(client):
    headers = account(client)
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    async def answer(*args):
        yield 'answer'
    client.app.state.answer = answer
    assert 'event: done' in client.post(f'/api/sessions/{session}/messages', headers=headers,
                                       json={'content': 'hello'}).text
    admin = account(client, 'adminuser')
    import asyncio
    from sqlalchemy import update, select, func
    from backend.models import User, Message
    async def promote():
        async with client.app.state.db() as db:
            await db.execute(update(User).where(User.username == 'adminuser').values(role='admin'))
            await db.commit()
    asyncio.run(promote())
    assert client.get(f'/api/sessions/{session}/messages', headers=admin).status_code == 200
    assert client.get('/api/admin/sessions', headers=admin).json()[0]['msgCount'] == 2
    assert client.delete(f'/api/admin/sessions/{session}', headers=admin).status_code == 200
    async def remaining():
        async with client.app.state.db() as db:
            return await db.scalar(select(func.count(Message.id)))
    assert asyncio.run(remaining()) == 0
    assert client.get('/api/sessions', headers=headers).json() == []


def test_upload_limits_bad_vectors_and_missing_model_key(client):
    headers = account(client)
    client.app.state.settings.max_upload_bytes = 5
    assert client.post('/api/upload', headers=headers, files={'file': ('big.txt', b'123456')}).status_code == 413
    client.app.state.settings.max_upload_bytes = 20 * 1024 * 1024
    assert client.post('/api/upload', headers=headers, files={'file': ('bad.docx', b'not-docx')}).status_code == 422
    async def bad_vectors(texts):
        return [[1.0, 2.0]]
    client.app.state.embed = bad_vectors
    assert client.post('/api/upload', headers=headers, files={'file': ('bad.txt', b'text')}).status_code == 502
    assert list(client.app.state.settings.upload_dir.iterdir()) == []
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    result = client.post(f'/api/sessions/{session}/messages', headers=headers, json={'content': 'hello'})
    assert 'event: error' in result.text and 'LLM_API_KEY' in result.text
    assert client.get(f'/api/sessions/{session}/messages', headers=headers).json() == []


def test_upload_rejects_oversize_http_body_before_parsing(client):
    headers = account(client)
    headers['Content-Length'] = str(100 * 1024 * 1024)
    assert client.post('/api/upload', headers=headers, content=b'body').status_code == 413


def test_expired_jwt_rejected(client):
    from jose import jwt
    expired = jwt.encode({'sub': '1', 'exp': 1}, client.app.state.settings.jwt_secret.get_secret_value(), algorithm='HS256')
    assert client.get('/api/sessions', headers={'Authorization': 'Bearer ' + expired}).status_code == 401
