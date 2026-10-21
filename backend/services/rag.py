"""文本提取、embedding 和 pgvector 私有知识库检索。"""
from pathlib import Path
from fastapi import HTTPException
from pgvector.sqlalchemy import Vector
from sqlalchemy import select, bindparam, Float
from sqlalchemy.orm import aliased
from backend.models import Knowledge
from backend.services.embedder import embed, validate_vectors


def chunk_text(text: str) -> list[str]:
    text = text.replace('\x00', '').strip()
    return [text[i:i + 500] for i in range(0, len(text), 500)]


def extract_text(path: Path, suffix: str) -> str:
    if suffix in {'.txt', '.md'}:
        return path.read_text(encoding='utf-8-sig')
    if suffix == '.docx':
        # 限制解压后的 XML 总量，避免小体积压缩炸弹。
        import zipfile
        with zipfile.ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError('Word 文档解压后过大')
        from agent.tools.convert_to_md import convert_docx
        return convert_docx(path)[0]
    from agent.tools.convert_to_md import convert_pdf
    return convert_pdf(path)[0]


async def retrieve(db, user_id: int, question: str, file_ids: list[str], embedder) -> list[dict]:
    # 空知识库无需调用 embedding；普通聊天仍可独立使用。
    filters = [Knowledge.user_id == user_id]
    if file_ids:
        filters.append(Knowledge.file_id.in_(file_ids))
    if await db.scalar(select(Knowledge.id).where(*filters).limit(1)) is None:
        return []
    vector = validate_vectors(await embedder([question]), 1)[0]
    if db.bind.dialect.name != 'postgresql':
        raise HTTPException(503, '向量检索需要 PostgreSQL/pgvector')
    # 全局 HNSW 的 ANN 后过滤可能漏掉当前用户的全部资料。先物化私有候选，
    # 再精确排序，确保用户/文件过滤后的 top 5 可靠；索引留供未来分区优化。
    candidates = select(Knowledge).where(*filters).cte('private_chunks').prefix_with('MATERIALIZED')
    private_chunk = aliased(Knowledge, candidates)
    distance = private_chunk.embedding.op('<=>', return_type=Float)(
        bindparam('query_embedding', vector, type_=Vector(1536)))
    rows = (await db.scalars(select(private_chunk).order_by(distance).limit(5))).all()
    return [{'fileId': row.file_id, 'fileName': row.file_name, 'text': row.chunk_text} for row in rows]
