"""显式启用旧预检索时，全文读取仍保持顺序、文件范围和来源消歧。"""
import asyncio

from backend.tests.test_api import client, account


def seed(client, username='alice', *, large=False, quote=''):
    from sqlalchemy import select
    from backend.models import User, Upload, Knowledge

    # 此文件验证可回滚的旧预检索全文路径；新聊天流程由 test_chat_routing 验证。
    client.app.state.settings.chat_preretrieval_enabled = True

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
                    text = '长' * 12000 if large else f'第{index + 1}章：{username}正文'
                    if quote and index == 2 and file_id.startswith('target-'):
                        text += '\n' + quote
                    db.add(Knowledge(file_id=file_id, user_id=user.id, file_name=name,
                                     chunk_index=index, chunk_text=text,
                                     embedding=[1.] + [0.] * 1535, meta={}))
            await db.commit()
    asyncio.run(insert())


def test_full_document_reads_other_accounts_document_in_order_without_model(client):
    account(client)
    seed(client)
    headers = account(client, 'bobby')
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


def test_quote_locates_source_and_returns_whole_document(client):
    headers = account(client)
    seed(client, quote='空压站仅有总管指针表，\n支路异常时无法区分设备耗气变化和压力波动。')
    account(client, 'bobby')
    seed(client, 'bobby')
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    response = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '查询「空压站仅有总管指针表，支路异常时无法区分设备耗气变化和压力波动。」出自哪篇文档，并输出该文档全文'})
    assert 'event: done' in response.text, response.text
    answer = client.get(f'/api/sessions/{session}/messages', headers=headers).json()[-1]['content']
    assert '09_外观检测相机与追溯接入.pdf' in answer
    assert all(f'第{i}章：alice正文' in answer for i in range(1, 9))
    assert 'bobby正文' not in answer


def test_quote_with_multiple_sources_requires_selection(client):
    headers = account(client)
    seed(client)
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    response = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '查询「第3章：alice正文」出自哪篇文档，并输出该文档全文'})
    assert 'event: error' in response.text and '多份' in response.text
    assert 'event: delta' not in response.text
    selected = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '查询「第3章：alice正文」出自哪篇文档，并输出该文档全文',
                                 'fileIds': ['target-alice']})
    assert 'event: done' in selected.text, selected.text


def test_quote_can_find_another_accounts_source_and_read_full_document(client):
    headers = account(client)
    seed(client)
    account(client, 'bobby')
    seed(client, 'bobby', quote='只有其他账号资料中出现的独有原句。')
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    response = client.post(f'/api/sessions/{session}/messages', headers=headers,
                           json={'content': '查询「只有其他账号资料中出现的独有原句。」出自哪篇文档，并输出该文档全文'})
    assert 'event: done' in response.text, response.text
    answer = client.get(f'/api/sessions/{session}/messages', headers=headers).json()[-1]['content']
    assert '只有其他账号资料中出现的独有原句。' in answer
    assert all(f'第{i}章：bobby正文' in answer for i in range(1, 9))
    assert 'alice正文' not in answer
