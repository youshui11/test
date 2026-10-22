"""CX 必须检索网站资料表，并受当前请求身份与文件范围约束。"""
import os
import json
import sys
from types import ModuleType

import pytest
from agno.agent import Agent
from agno.models.deepseek import DeepSeek
from agno.team import Team
from backend.agent.adapter import create_agent
from backend.config import Settings
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from backend.database import Base, connect_database
from backend.models import User, Upload, Knowledge


@pytest.mark.asyncio
async def test_cx_tool_reads_private_public_table_and_replaces_only_search(monkeypatch):
    from backend.services.cx_knowledge import knowledge_scope
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('需要 TEST_DATABASE_URL 运行真实 pgvector 查询')
    if url == 'configured':
        url = Settings().database_url
    engine, _ = connect_database(url)
    schema = 'test_cx_' + uuid4().hex
    module = ModuleType('agent.server')
    def search_cx_knowledge(query: str):
        raise AssertionError('不得再调用旧 Agno ai 表工具')
    member = Agent(id='cx-subagent', model=DeepSeek(id='test', api_key='test'), tools=[search_cx_knowledge])
    module.pd_team = Team(model=DeepSeek(id='test', api_key='test'), members=[member])
    monkeypatch.setitem(sys.modules, 'agent.server', module)
    settings = Settings(_env_file=None, jwt_secret='x' * 32)
    settings.llm_config_source = 'server'

    created = False
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        # public 显式映射到测试专用 schema，绝不更改网站的真实表。
        isolated = engine.execution_options(schema_translate_map={None: schema, 'public': schema})
        factory = async_sessionmaker(isolated, expire_on_commit=False)
        async with isolated.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            alice = User(username='alice', password_hash='unused')
            bobby = User(username='bobby', password_hash='unused')
            db.add_all([alice, bobby])
            await db.flush()
            user_id = alice.id
            for file_id, user in [('target-alice', alice), ('other-alice', alice), ('target-bobby', bobby)]:
                db.add(Upload(file_id=file_id, user_id=user.id, file_name='09_外观检测相机与追溯接入.pdf',
                              storage_name=file_id, size=1))
                await db.flush()
                for index in range(8):
                    db.add(Knowledge(file_id=file_id, user_id=user.id, file_name='09_外观检测相机与追溯接入.pdf',
                                     chunk_text=f'{user.username}正文{index}',
                                     embedding=[1.] + [0.] * 1535, chunk_index=index))
            await db.commit()
        async def embedding(texts):
            assert texts == ['相机方案']
            return [[1.] + [0.] * 1535]
        with knowledge_scope(factory, user_id, ['target-alice'], embedding):
            runner = create_agent(settings)
            tool = runner.members[0].tools[0]
            result = json.loads(await tool.entrypoint('相机方案'))
        assert result['count'] == 3
        assert all('alice正文' in row['content'] and row['fileId'] == 'target-alice' for row in result['results'])
        assert all(row['fileName'] == '09_外观检测相机与追溯接入.pdf' for row in result['results'])
        assert member.tools[0] is search_cx_knowledge
        with knowledge_scope(factory, user_id, ['target-bobby'], embedding):
            empty = json.loads(await create_agent(settings).members[0].tools[0].entrypoint('相机方案'))
        assert empty['count'] == 0
    finally:
        if created:
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


@pytest.mark.asyncio
async def test_cx_tool_fails_closed_without_authenticated_scope():
    from backend.services.cx_knowledge import make_public_knowledge_tool
    tool = make_public_knowledge_tool()
    with pytest.raises(ValueError, match='身份'):
        await tool.entrypoint('资料')
