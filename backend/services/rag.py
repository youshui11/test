"""文本提取、embedding 和 pgvector 私有知识库检索。"""
from pathlib import Path
import re
from fastapi import HTTPException
from pgvector.sqlalchemy import Vector
from sqlalchemy import select, bindparam, Float, func
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
    # 只有明确索取原文时读取全文；“根据全文总结/分析”等仍走普通问答。
    full_request = re.fullmatch(
        r'\s*(?:请)?(?:帮我)?(?:输出|列出|显示|提供|查看|读取)?\s*'
        r'(?:[《「“\"\']?(?P<name>.+\.(?:pdf|docx|xlsx|xls|pptx|txt|md))[》」”\"\']?\s*(?:中|的)?)?'
        r'(?:全部内容|完整内容|全文)[。！!？?\s]*', question, re.IGNORECASE)
    if full_request:
        name = full_request['name']
        if name:
            filters.append(Knowledge.file_name == name)
        elif not file_ids:
            raise HTTPException(422, '请指定资料文件名，例如：文件.pdf中全部内容')
        count, total, files = (await db.execute(select(
            func.count(Knowledge.id), func.sum(func.length(Knowledge.chunk_text)),
            func.count(func.distinct(Knowledge.file_id))).where(*filters))).one()
        if not count:
            raise HTTPException(404, '未找到该资料的已入库内容，请检查文件名及当前账号')
        if name and files > 1:
            raise HTTPException(409, '存在多份同名资料，请通过附件指定其中一份')
        # 在读取/输出之前拒绝过大请求，避免先输出半篇才触及 SSE 回复上限。
        if total + count * 400 > 90000:
            raise HTTPException(422, '资料过长，无法一次输出全部内容，请按章节分段查询')
        rows = (await db.scalars(select(Knowledge).where(*filters).order_by(
            Knowledge.file_id, Knowledge.chunk_index.asc().nulls_last(), Knowledge.id))).all()
        return [{'fileId': row.file_id, 'fileName': row.file_name, 'text': row.chunk_text,
                 'retrievalMode': 'full'} for row in rows]
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
