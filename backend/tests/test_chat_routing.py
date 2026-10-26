"""聊天仅传真实历史与当前问题，资料由身份绑定的工具按需读取。"""
import asyncio

from agno.agent import Agent
from agno.run.agent import RunContentEvent
from pydantic import SecretStr

from backend.tests.test_api import client, account


def test_chat_passes_only_real_history_and_question_without_prefetch(client, monkeypatch):
    from agent import runtime as agent
    from agent.tools.cx_knowledge import get_knowledge_scope

    headers = account(client)
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    observed = []

    async def forbidden(*args):
        raise AssertionError('聊天不应自动检索或生成 embedding')

    class ChatAgent(Agent):
        async def arun(self, messages, **kwargs):
            scope = get_knowledge_scope()
            assert scope is not None and scope.user_id > 0
            observed.append([(message.role, message.content) for message in messages])
            yield RunContentEvent(content='仅回答当前问题')

    client.app.state.settings.llm_api_key = SecretStr('test')
    client.app.state.embed = forbidden
    monkeypatch.setattr(agent, 'create_agent', lambda _: ChatAgent())
    for question in ('hi', '我刚刚问了什么'):
        reply = client.post(f'/api/sessions/{session}/messages', headers=headers, json={'content': question})
        assert 'event: done' in reply.text, reply.text
    assert observed == [
        [('user', 'hi')],
        [('user', 'hi'), ('assistant', '仅回答当前问题'), ('user', '我刚刚问了什么')],
    ]


def test_full_text_tool_receives_authenticated_scope_without_prefetch(client, monkeypatch):
    from agent.tools.qwjs_knowledge import make_full_document_tool
    from agent import runtime as agent
    from backend.models import Knowledge, Upload, User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    headers = account(client)
    mapped = client.app.state.engine.execution_options(schema_translate_map={'public': None})
    client.app.state.db = async_sessionmaker(mapped, expire_on_commit=False)

    async def seed():
        async with client.app.state.db() as db:
            user = await db.scalar(select(User).where(User.username == 'alice'))
            db.add(Upload(file_id='source', user_id=user.id, file_name='手册.docx', storage_name='unused', size=1))
            await db.flush()
            for index, text in [(1, '第二章'), (0, '第一章')]:
                db.add(Knowledge(file_id='source', user_id=user.id, file_name='手册.docx',
                                 chunk_index=index, chunk_text=text, embedding=[1.0]))
            await db.commit()
    asyncio.run(seed())

    async def forbidden(*args):
        raise AssertionError('全文工具读取不应触发聊天预检索或 embedding')

    class FullTextAgent(Agent):
        async def arun(self, messages, **kwargs):
            result = await make_full_document_tool().entrypoint(document_name='手册.docx')
            yield RunContentEvent(content=result)

    client.app.state.settings.llm_api_key = SecretStr('test')
    client.app.state.embed = forbidden
    monkeypatch.setattr(agent, 'create_agent', lambda _: FullTextAgent())
    session = client.post('/api/sessions', headers=headers, json={}).json()['sessionId']
    reply = client.post(f'/api/sessions/{session}/messages', headers=headers,
                        json={'content': '请输出手册.docx全文'})
    assert 'event: done' in reply.text, reply.text
    messages = client.get(f'/api/sessions/{session}/messages', headers=headers).json()
    assert messages[-1]['content'] == '第一章\n\n第二章'
