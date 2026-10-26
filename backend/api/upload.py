"""受限文件上传、原子向量入库与鉴权下载。"""
import logging
from pathlib import Path
from uuid import uuid4
import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from backend.database import get_db
from backend.models import User, Upload, Knowledge
from backend.services.auth import get_current_user
from backend.services.chat import public_file
from agent.tools.attachments import chunk_text, extract_text
from agent.embedding import validate_vectors

router = APIRouter(prefix='/api', tags=['文件'])
logger = logging.getLogger(__name__)


@router.post('/upload', status_code=201)
async def upload(request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    name = (file.filename or '').replace('\\', '/').split('/')[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in {'.pdf', '.docx', '.txt', '.md'}:
        raise HTTPException(415, '仅支持 PDF、DOCX、TXT、Markdown')
    if not name or len(name) > 200 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, '文件名无效或过长')
    user_id = user.id
    # 解析与 embedding 都在短写事务之前执行，不长期占用鉴权连接。
    await db.commit()
    settings = request.app.state.settings
    file_id = 'f_' + uuid4().hex
    storage_name = file_id + suffix
    path = settings.upload_dir / storage_name
    complete = False
    try:
        size = 0
        async with await anyio.open_file(path, 'wb') as target:
            while data := await file.read(64 * 1024):
                size += len(data)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, '单个附件不能超过 20 MB')
                await target.write(data)
        try:
            content = await run_in_threadpool(extract_text, path, suffix)
            chunks = chunk_text(content)
            if not chunks:
                raise ValueError('没有可提取的文字，扫描件需先 OCR')
            if len(chunks) > settings.max_chunks_per_file:
                raise ValueError('文件文本过长，请拆分后上传')
        except Exception as exc:
            raise HTTPException(422, '无法读取文件，请检查格式、编码或先进行 OCR') from exc
        try:
            vectors = validate_vectors(await request.app.state.embed(chunks), len(chunks))
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning('Embedding failed: %s', type(exc).__name__)
            raise HTTPException(502, '向量服务调用失败，请稍后重试') from exc
        record = Upload(file_id=file_id, user_id=user_id, file_name=name, storage_name=storage_name, size=size)
        db.add(record)
        await db.flush()
        db.add_all([Knowledge(file_id=file_id, user_id=user_id, file_name=name, chunk_text=chunk,
                              embedding=vector, chunk_index=index, meta={'chunk': index})
                    for index, (chunk, vector) in enumerate(zip(chunks, vectors))])
        await db.commit()
        complete = True
        return public_file(record)
    finally:
        # 包含 spool.close 的整个清理过程均需保护；关闭失败也不能跳过文件删除。
        with anyio.CancelScope(shield=True):
            try:
                await file.close()
            finally:
                if not complete:
                    try:
                        await db.rollback()
                    finally:
                        await run_in_threadpool(path.unlink, missing_ok=True)


@router.get('/files/{file_id}')
async def download(file_id: str, request: Request, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    record = await db.get(Upload, file_id)
    if not record or (record.user_id != user.id and user.role != 'admin'):
        raise HTTPException(404, '附件不存在或无权访问')
    path = request.app.state.settings.upload_dir / record.storage_name
    if not await run_in_threadpool(path.is_file):
        raise HTTPException(404, '文件已不存在')
    return FileResponse(path, filename=record.file_name, media_type='application/octet-stream',
                        headers={'X-Content-Type-Options': 'nosniff'})
