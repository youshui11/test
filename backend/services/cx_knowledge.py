"""CX 工具读取网站 public.knowledge_base，绑定当前请求的用户及附件范围。"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json

from agno.tools import tool
from pgvector.sqlalchemy import Vector
from sqlalchemy import MetaData, select, bindparam, Float
from backend.models import Knowledge
from backend.services.embedder import validate_vectors


public_knowledge = Knowledge.__table__.to_metadata(MetaData(), schema='public')
_scope = ContextVar('cx_knowledge_scope', default=None)


@dataclass(frozen=True)
class SearchScope:
    factory: object
    user_id: int
    file_ids: tuple[str, ...]
    embedder: object


@contextmanager
def knowledge_scope(factory, user_id, file_ids, embedder):
    token = _scope.set(SearchScope(factory, user_id, tuple(file_ids), embedder))
    try:
        yield
    finally:
        _scope.reset(token)


def make_public_knowledge_tool():
    scope = _scope.get()

    @tool(name='search_cx_knowledge',
          description='从当前用户的 public.knowledge_base 检索最相近的三条资料。',
          stop_after_tool_call=True)
    async def search_cx_knowledge(query: str) -> str:
        if scope is None:
            raise ValueError('CX 检索未绑定登录身份，拒绝查询资料')
        table = public_knowledge
        filters = [table.c.user_id == scope.user_id]
        if scope.file_ids:
            filters.append(table.c.file_id.in_(scope.file_ids))
        # embedding 网络请求期间不持有数据库事务/连接。
        async with scope.factory() as db:
            exists = await db.scalar(select(table.c.id).where(*filters).limit(1))
        results = []
        if exists is not None:
            vector = validate_vectors(await scope.embedder([query]), 1)[0]
            candidates = select(table).where(*filters).cte('cx_private_chunks').prefix_with('MATERIALIZED')
            distance = candidates.c.embedding.op('<=>', return_type=Float)(
                bindparam('cx_query_embedding', vector, type_=Vector(1536)))
            statement = select(candidates.c.file_id, candidates.c.file_name, candidates.c.chunk_text).order_by(
                distance, candidates.c.id).limit(3)
            async with scope.factory() as db:
                rows = (await db.execute(statement)).all()
            results = [{'rank': rank, 'fileId': row.file_id, 'fileName': row.file_name,
                        'content': row.chunk_text} for rank, row in enumerate(rows, 1)]
        return json.dumps({'query': query, 'count': len(results), 'results': results}, ensure_ascii=False)

    return search_cx_knowledge
