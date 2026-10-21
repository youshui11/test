"""验证真实 SDK 的分批、限流退避、向量校验和密钥回退。"""
import json
import httpx
from openai import AsyncOpenAI
import pytest
from backend.config import Settings


@pytest.mark.asyncio
async def test_embedding_batches_and_rate_limit_retries(monkeypatch):
    from backend.services import embedder
    batches, waits = [], []
    calls = 0
    def handle(request):
        nonlocal calls
        calls += 1
        if calls <= 2:
            return httpx.Response(429, json={'error': {'message': 'rate limited', 'type': 'rate_limit_error'}})
        payload = json.loads(request.content)
        assert payload['dimensions'] == 1536
        batches.append(len(payload['input']))
        return httpx.Response(200, json={'object': 'list', 'model': 'text-embedding-3-small',
            'data': [{'object': 'embedding', 'index': i, 'embedding': [1.] + [0.] * 1535}
                     for i in range(len(payload['input']))], 'usage': {'prompt_tokens': 1, 'total_tokens': 1}})
    async def no_wait(seconds):
        waits.append(seconds)
    monkeypatch.setattr(embedder, 'sleep', no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        def factory(**kwargs):
            assert kwargs['max_retries'] == 0
            return AsyncOpenAI(**kwargs, http_client=http)
        monkeypatch.setattr(embedder, 'AsyncOpenAI', factory)
        settings = Settings(_env_file=None, jwt_secret='x' * 32, embedding_api_key='test')
        result = await embedder.embed(['资料'] * 41, settings)
        assert len(result) == 41 and batches == [20, 20, 1]
        assert waits == [1, 2]


@pytest.mark.asyncio
async def test_rate_limit_stops_after_three_retries(monkeypatch):
    from backend.services import embedder
    calls = []
    def handle(request):
        calls.append(True)
        return httpx.Response(429, json={'error': {'message': 'limit', 'type': 'rate_limit_error'}})
    async def no_wait(seconds):
        pass
    monkeypatch.setattr(embedder, 'sleep', no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        monkeypatch.setattr(embedder, 'AsyncOpenAI', lambda **kw: AsyncOpenAI(**kw, http_client=http))
        with pytest.raises(embedder.EmbeddingError, match='限流'):
            await embedder.embed(['text'], Settings(_env_file=None, jwt_secret='x' * 32, embedding_api_key='test'))
    assert len(calls) == 4


def test_vectors_reject_invalid_values_and_key_fallback():
    from backend.services.embedder import validate_vectors
    for vectors in [[], [[1., 2.]], [[0.] * 1536], [[float('nan')] * 1536], [[float('inf')] * 1536]]:
        with pytest.raises(ValueError):
            validate_vectors(vectors, 1)
    settings = Settings(_env_file=None, jwt_secret='x' * 32, openai_api_key='openai-test')
    assert settings.embedding_api_key.get_secret_value() == 'openai-test'
    preferred = Settings(_env_file=None, jwt_secret='x' * 32, openai_api_key='other', embedding_api_key='preferred')
    assert preferred.embedding_api_key.get_secret_value() == 'preferred'


@pytest.mark.asyncio
async def test_invalid_embedding_key_has_actionable_error_without_retry(monkeypatch):
    from backend.services import embedder
    calls = []
    def handle(request):
        calls.append(True)
        return httpx.Response(401, json={'error': {'message': 'private credential', 'code': 'invalid_api_key'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        monkeypatch.setattr(embedder, 'AsyncOpenAI', lambda **kw: AsyncOpenAI(**kw, http_client=http))
        with pytest.raises(embedder.EmbeddingError, match='401') as error:
            await embedder.embed(['text'], Settings(_env_file=None, jwt_secret='x' * 32, embedding_api_key='test'))
    assert len(calls) == 1 and 'private credential' not in str(error.value)
