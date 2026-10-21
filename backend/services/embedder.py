"""统一 embedding：20 条分批、1536 维校验、429 最多三次指数退避重试。"""
from asyncio import sleep
import math
from openai import AsyncOpenAI, RateLimitError, APIError
from fastapi import HTTPException


class EmbeddingError(Exception):
    """可以展示给用户的向量服务错误。"""


def validate_vectors(vectors, expected):
    if len(vectors) != expected or any(len(vector) != 1536 or
            not all(math.isfinite(value) for value in vector) or not any(vector) for vector in vectors):
        raise ValueError('embedding 必须返回有效、非零的 1536 维向量')
    return vectors


async def embed(texts: list[str], settings) -> list[list[float]]:
    key = settings.embedding_api_key.get_secret_value()
    if not key:
        raise HTTPException(503, '未配置 EMBEDDING_API_KEY 或 OPENAI_API_KEY')
    vectors = []
    async with AsyncOpenAI(api_key=key, base_url=settings.embedding_base_url,
                           timeout=settings.model_timeout_seconds, max_retries=0) as client:
        for start in range(0, len(texts), 20):
            batch = texts[start:start + 20]
            for attempt in range(4):
                try:
                    response = await client.embeddings.create(model=settings.embedding_model, input=batch,
                                                                dimensions=1536, encoding_format='float')
                    break
                except RateLimitError:
                    if attempt == 3:
                        raise EmbeddingError('向量服务限流，重试三次后仍失败，请稍后重新导入') from None
                    await sleep(2 ** attempt)
                except APIError as exc:
                    if getattr(exc, 'status_code', None) == 401:
                        raise EmbeddingError('向量服务密钥无效（401），请更新 EMBEDDING_API_KEY，或清空后填写 OPENAI_API_KEY') from None
                    if getattr(exc, 'status_code', None) == 403:
                        raise EmbeddingError('向量服务拒绝访问（403），请检查密钥权限和服务配置') from None
                    raise EmbeddingError('向量服务调用失败，请检查 embedding 密钥、模型和服务地址') from None
            data = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in data] != list(range(len(batch))):
                raise EmbeddingError('向量服务返回的片段数量或顺序无效')
            try:
                vectors.extend(validate_vectors([item.embedding for item in data], len(batch)))
            except (ValueError, TypeError):
                raise EmbeddingError('向量服务未返回有效的 1536 维向量') from None
    return vectors
