"""全文请求必须返回指定资料的所有片段，保持顺序和用户隔离。"""
import asyncio

from backend.tests.test_api import client, account


def seed(client, username='alice', *, large=False):
    from sqlalchemy import select
    from backend.models import User, Upload, Knowledge

    async def no_embedding(texts):
        raise AssertionError('全文读取不应调用 embedding')
    client.app.state.embed = no_embedding

    async def insert():
        async with client.app.state.db() as db:
            user = await db.scalar(select(User).where(User.username == username))
            for file_id, name in [('target-' + username, '09_外观检测相机与追溯接入.pdf'),
                                  ('other-' + username, '其他.pdf')]:
                db.add(Upload(file_id=file_id, user_id=user.id, file_name=name, storage_name=file_id, size=1))
                await db.flush()
                for index in reversed(range(8)):
                    db.add(Knowledge(file_id=file_id, user_id=user.id, file_name=name,
                                     chunk_index=index, chunk_text=('长' * 12000 if large else f'第{index + 1}章：{username}正文'),
                                     embedding=[1.] + [0.] * 1535, meta={}))
            await db.commit()
    asyncio.run(insert())


def test_full_document_returns_all_chapters_in_order_without_model(client):
    headers = account(client)
    seed(client)
    account(client, 'bobby')
    seed(client, 'bobby')
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    response = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '09_外观检测相机与追溯接入.pdf中全部内容'})
    assert 'event: done' in response.text, response.text
    messages = client.get(f'/api/sessions/{session}/messages', headers=headers).json()
    answer = messages[-1]['content']
    positions = [answer.index(f'第{i}章：alice正文') for i in range(1, 9)]
    assert positions == sorted(positions)
    assert 'bobby正文' not in answer and '其他.pdf' not in answer


def test_full_document_unknown_name_never_falls_back_to_unrelated_chunks(client):
    headers = account(client)
    seed(client)
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    response = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '不存在.pdf中全部内容'})
    assert 'event: error' in response.text and '未找到' in response.text
    assert client.get(f'/api/sessions/{session}/messages', headers=headers).json() == []


def test_full_document_rejects_oversize_without_partial_reply(client):
    headers = account(client)
    seed(client, large=True)
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    response = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '09_外观检测相机与追溯接入.pdf中全部内容'})
    assert 'event: error' in response.text and '分段' in response.text
    assert 'event: delta' not in response.text


def test_full_document_can_use_explicit_attachment_and_requires_a_scope(client):
    headers = account(client)
    seed(client)
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    response = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '请输出全部内容'})
    assert 'event: error' in response.text and '指定' in response.text
    response = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '请输出全部内容', 'fileIds': ['target-alice']})
    assert 'event: done' in response.text, response.text
    answer = client.get(f'/api/sessions/{session}/messages', headers=headers).json()[-1]['content']
    assert '第8章：alice正文' in answer and '其他.pdf' not in answer
