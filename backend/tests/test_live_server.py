"""可选真实 HTTP/重启验收；只清理本测试创建的随机账号。"""
import asyncio
from contextlib import contextmanager
import os
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import delete
from backend.config import ROOT, Settings
from backend.database import connect_database
from backend.models import User


@pytest.mark.skipif(os.getenv('RUN_LIVE_SMOKE') != '1', reason='设置 RUN_LIVE_SMOKE=1 运行真实服务验收')
def test_live_http_and_restart_persistence(tmp_path):
    username = 'smoke_' + uuid4().hex[:16]
    password = secrets.token_urlsafe(20)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    environment = dict(os.environ, LLM_API_KEY='', EMBEDDING_API_KEY='', LLM_CONFIG_SOURCE='env')

    @contextmanager
    def running():
        with (tmp_path / 'uvicorn.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.server:app', '--factory',
                '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=environment,
                stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                with httpx.Client(base_url=origin, timeout=10, trust_env=False) as http:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            pytest.fail('uvicorn 启动失败，见测试目录 uvicorn.log')
                        try:
                            if http.get('/api/health').status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.1)
                    else:
                        pytest.fail('真实数据库健康检查未通过')
                    yield http
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)

    async def cleanup():
        engine, factory = connect_database(Settings().database_url)
        try:
            async with factory() as db:
                await db.execute(delete(User).where(User.username == username))
                await db.commit()
        finally:
            await engine.dispose()

    try:
        with running() as http:
            assert http.get('/').status_code == 200
            assert http.get('/api.js').status_code == 200
            assert http.get('/docs').status_code == 200
            assert http.post('/api/users', json={'username': username, 'password': password}).status_code == 201
            login = http.post('/api/login', json={'username': username, 'password': password})
            headers = {'Authorization': 'Bearer ' + login.json()['token']}
            session = http.post('/api/sessions', headers=headers, json={}).json()['sessionId']
            stream = http.post(f'/api/sessions/{session}/messages', headers=headers, json={'content': 'test'})
            assert 'event: error' in stream.text and 'LLM_API_KEY' in stream.text
        with running() as http:
            rows = http.get('/api/sessions', headers=headers).json()
            assert rows[0]['sessionId'] == session
            assert http.get(f'/api/sessions/{session}/messages', headers=headers).json() == []
    finally:
        asyncio.run(cleanup())
