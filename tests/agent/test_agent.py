# 文件作用：验证智能体流式正文筛选、团队事件和上游报错的处理行为。
# 关联关系：直接测试 agent/runtime.py，防止部分回答后报错被误判为成功。
"""Agno 事件转换，尤其是上游部分响应后错误不能当作成功。"""
import pytest
from fastapi import HTTPException
from agno.run.agent import RunContentEvent, RunErrorEvent
from agno.agent import Agent
from agno.team import Team
from backend.config import Settings
from agent import runtime as agent


@pytest.mark.asyncio
async def test_agno_error_event_rejects_partial_response(monkeypatch):
    class EventSource:
        async def arun(self, *args, **kwargs):
            yield RunContentEvent(content='partial')
            yield RunErrorEvent(content='private upstream error')
    monkeypatch.setattr(agent, 'create_agent', lambda _: EventSource())
    settings = Settings(jwt_secret='x' * 32, llm_api_key='test-key', llm_config_source='env')
    with pytest.raises(HTTPException, match='模型服务'):
        async for _ in agent.stream_answer([], 'hello', settings):
            pass


@pytest.mark.asyncio
async def test_team_content_is_streamed_and_team_error_is_not_success(monkeypatch):
    from types import SimpleNamespace
    class EventSource(Team):
        async def arun(self, *args, **kwargs):
            yield SimpleNamespace(event='TeamRunContent', content='团队回复')
            yield SimpleNamespace(event='TeamRunError', content='private error')
    monkeypatch.setattr(agent, 'create_agent', lambda _: EventSource(members=[]))
    settings = Settings(_env_file=None, jwt_secret='x' * 32, llm_api_key='test', llm_config_source='env')
    parts = []
    with pytest.raises(HTTPException, match='模型服务'):
        async for part in agent.stream_answer([], 'hello', settings):
            parts.append(part)
    assert parts == ['团队回复']


@pytest.mark.asyncio
@pytest.mark.parametrize('team_mode', [False, True])
async def test_only_main_callers_content_event_is_forwarded(monkeypatch, team_mode):
    from agno.run.team import RunContentEvent as TeamContentEvent
    base = Team if team_mode else Agent

    class EventSource(base):
        async def arun(self, *args, **kwargs):
            yield RunContentEvent(content='单智能体正文')
            yield TeamContentEvent(content='团队正文')

    monkeypatch.setattr(agent, 'create_agent', lambda _: EventSource(**({'members': []} if team_mode else {})))
    settings = Settings(_env_file=None, jwt_secret='x' * 32, llm_api_key='test', llm_config_source='env')
    parts = [part async for part in agent.stream_answer([], 'hello', settings)]
    assert parts == (['团队正文'] if team_mode else ['单智能体正文'])
