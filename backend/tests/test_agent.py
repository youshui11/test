"""Agno 事件转换，尤其是上游部分响应后错误不能当作成功。"""
import pytest
from fastapi import HTTPException
from agno.run.agent import RunContentEvent, RunErrorEvent
from backend.config import Settings
from backend.services import agent


@pytest.mark.asyncio
async def test_agno_error_event_rejects_partial_response(monkeypatch):
    class EventSource:
        async def arun(self, *args, **kwargs):
            yield RunContentEvent(content='partial')
            yield RunErrorEvent(content='private upstream error')
    monkeypatch.setattr(agent, 'create_agent', lambda _: EventSource())
    settings = Settings(jwt_secret='x' * 32, llm_api_key='test-key', llm_config_source='env')
    with pytest.raises(HTTPException, match='模型服务'):
        async for _ in agent.stream_answer([], 'hello', [], settings):
            pass
