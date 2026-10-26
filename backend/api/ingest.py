# 文件作用：接收知识库资料、登记后台导入任务，并提供当前用户任务状态查询。
# 关联关系：将资料交给 agent/dr.py 的 DRAgent，通过 Upload/IngestJob 记录状态。
"""POST 资料导入与用户隔离的持久化状态查询。"""
from pathlib import Path
from uuid import uuid4
import anyio
from fastapi import APIRouter, Request, Depends, File, UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from backend.database import get_db
from backend.models import User, Upload, IngestJob
from backend.services.auth import get_current_user
from agent.documents.converter import CONVERTERS
from agent.dr import job_directory, clean_job_directory

router = APIRouter(prefix='/api/ingest', tags=['导入资料'])


@router.post('', status_code=202)
async def ingest(request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    file_name = (file.filename or '').replace('\\', '/').split('/')[-1]
    suffix = Path(file_name).suffix.lower()
    if suffix not in CONVERTERS:
        raise HTTPException(415, '不支持的文件格式')
    if not file_name or len(file_name) > 200 or any(ord(char) < 32 for char in file_name):
        raise HTTPException(422, '文件名无效或过长')
    if request.app.state.dr.closing:
        raise HTTPException(503, '服务正在关闭，请稍后重试')
    user_id = user.id
    await db.commit()
    file_id = str(uuid4())
    root = request.app.state.settings.ingest_temp_dir
    folder = job_directory(root, file_id)
    await run_in_threadpool(folder.mkdir, parents=True, exist_ok=False)
    storage_name = 'source' + suffix
    accepted = False
    try:
        # 先写所有权标记再保存原件，供崩溃后安全回收尚未登记数据库的目录。
        await run_in_threadpool((folder / '.ingest-owner').write_text,
                                'ingest-v1:' + file_id, encoding='utf-8')
        size = 0
        async with await anyio.open_file(folder / storage_name, 'wb') as output:
            while data := await file.read(64 * 1024):
                size += len(data)
                if size > request.app.state.settings.max_ingest_bytes:
                    raise HTTPException(413, '导入资料不能超过 50 MB')
                await output.write(data)
        if size == 0:
            raise HTTPException(422, '不能导入空文件')
        db.add(Upload(file_id=file_id, user_id=user_id, file_name=file_name, storage_name=storage_name,
                      size=size, status='processing'))
        await db.flush()
        db.add(IngestJob(file_id=file_id))
        with anyio.CancelScope(shield=True):
            await db.commit()
            request.app.state.dr.start(file_id)
            accepted = True
        return {'fileId': file_id, 'fileName': file_name, 'chunkCount': 0, 'status': 'processing'}
    finally:
        with anyio.CancelScope(shield=True):
            try:
                await file.close()
            finally:
                if not accepted:
                    try:
                        await db.rollback()
                    finally:
                        await run_in_threadpool(clean_job_directory, root, file_id)


@router.get('/status/{file_id}')
async def status(file_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await db.scalar(select(IngestJob).join(Upload, Upload.file_id == IngestJob.file_id)
                          .where(IngestJob.file_id == file_id, Upload.user_id == user.id))
    if job is None:
        raise HTTPException(404, '导入任务不存在或无权访问')
    return {'fileId': job.file_id, 'status': job.status, 'chunkCount': job.chunk_count, 'error': job.error}
