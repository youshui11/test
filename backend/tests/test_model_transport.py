"""通过可控 HTTP 上游验证真实 Agno/OpenAI 流式协议，无外网调用。"""
import json
import httpx
import pytest
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from openai import AsyncOpenAI
from backend.config import Settings
from backend.services import agent


@pytest.mark.asyncio
async def test_real_agno_stream_over_openai_transport(monkeypatch):
    def handle(request):
        payload = json.loads(request.content)
        assert payload['stream'] is True
        assert payload['messages'][-1]['content'] == '问题'
        frames = []
        for delta, finish in [({'role': 'assistant', 'content': ''}, None),
                              ({'content': '你好'}, None), ({'content': '世界'}, None), ({}, 'stop')]:
            frames.append('data: ' + json.dumps({'id': 'test', 'object': 'chat.completion.chunk', 'created': 1,
                'model': 'test-model', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}) + '\n\n')
        return httpx.Response(200, headers={'Content-Type': 'text/event-stream'},
                              text=''.join(frames) + 'data: [DONE]\n\n')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        async with AsyncOpenAI(api_key='test', http_client=http) as upstream:
            real_agent = Agent(model=OpenAIChat(id='test-model', async_client=upstream), telemetry=False)
            monkeypatch.setattr(agent, 'create_agent', lambda settings: real_agent)
            settings = Settings(jwt_secret='x' * 32, llm_api_key='test', llm_config_source='env')
            result = [part async for part in agent.stream_answer([], '问题', [], settings)]
            assert ''.join(result) == '你好世界'


@pytest.mark.asyncio
async def test_server_deepseek_config_sends_supported_roles(tmp_path, monkeypatch):
    from backend.agent.server import create_agent
    source = tmp_path / 'server.py'
    source.write_text('model=DeepSeek(id="deepseek-v4-flash", api_key="test", use_thinking=False)', encoding='utf-8')
    settings = Settings(_env_file=None, jwt_secret='x' * 32, llm_config_source='server', llm_server_config_path=source)
    import sys
    from types import ModuleType
    from agno.models.deepseek import DeepSeek
    module = ModuleType('agent.server')
    module.deepseek_agent = Agent(model=DeepSeek(id='deepseek-v4-flash', api_key='test', use_thinking=False),
                                 instructions='test instruction', telemetry=False)
    monkeypatch.setitem(sys.modules, 'agent.server', module)
    captured = []
    def handle(request):
        body = json.loads(request.content)
        captured.append(body)
        assert all(item['role'] in {'system', 'user', 'assistant', 'tool'} for item in body['messages'])
        assert body['thinking'] == {'type': 'disabled'}
        chunk = {'id': 'test', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'deepseek-v4-flash',
                 'choices': [{'index': 0, 'delta': {'content': '连接成功'}, 'finish_reason': 'stop'}]}
        return httpx.Response(200, headers={'Content-Type': 'text/event-stream'},
                              text='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        async with AsyncOpenAI(api_key='test', http_client=http, max_retries=0) as upstream:
            configured = create_agent(settings)
            configured.model.async_client = upstream
            parts = []
            async for event in configured.arun('test', stream=True):
                if getattr(event, 'event', '') == 'RunContent' and isinstance(event.content, str):
                    parts.append(event.content)
            assert ''.join(parts) == '连接成功'
            assert len(captured) == 1
