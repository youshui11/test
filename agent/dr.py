# 文件作用：管理知识库后台导入，协调转换、语义切分、向量入库、任务恢复和临时目录清理。
# 关联关系：由 backend/server.py 创建 DRAgent，供导入接口启动任务并由应用生命周期统一收尾。
"""dr 导入处理：受管理的后台任务、原子入库、状态恢复与限定目录清理。"""
import asyncio
import logging
from pathlib import Path
import shutil
from uuid import UUID
import anyio
from fastapi import HTTPException
from sqlalchemy import select, update
from starlette.concurrency import run_in_threadpool
from backend.models import Upload, Knowledge, IngestJob
from backend.models.user import utcnow
from agent.documents.chunker import chunk_markdown
from agent.documents.converter import ConvertError
from agent.embedding import EmbeddingError, validate_vectors

logger = logging.getLogger(__name__)


def job_directory(root: Path, file_id: str) -> Path:
    # 只接受本功能生成的标准 UUID；递归清理前验证最终绝对路径归属。
    if str(UUID(file_id)) != file_id:
        raise ValueError('任务 ID 格式无效')
    absolute_root = root.resolve()
    target = (absolute_root / file_id).resolve()
    if target.parent != absolute_root or target != absolute_root / file_id:
        raise ValueError('任务目录越界')
    return target


def clean_job_directory(root: Path, file_id: str):
    target = job_directory(root, file_id)
    if target.exists():
        shutil.rmtree(target)


def orphan_directories(root: Path, registered: set[str]):
    result = []
    for entry in root.iterdir():
        if entry.name in registered or not entry.is_dir() or entry.is_symlink() or getattr(entry, 'is_junction', lambda: False)():
            continue
        try:
            target = job_directory(root, entry.name)
            with (target / '.ingest-owner').open(encoding='utf-8') as marker:
                owned = marker.read(64) == 'ingest-v1:' + entry.name
            if owned:
                result.append(entry.name)
        except (ValueError, OSError, UnicodeError):
            continue
    return result


class DRAgent:
    name = 'dr'

    def __init__(self, app):
        self.app = app
        self.tasks = set()
        self.semaphore = asyncio.Semaphore(app.state.settings.ingest_concurrency)
        self.closing = False

    def start(self, file_id):
        if self.closing:
            raise HTTPException(503, '服务正在关闭，请稍后重新导入')
        task = asyncio.create_task(self.run(file_id), name='ingest:' + file_id)
        self.tasks.add(task)
        task.add_done_callback(self.finished)

    def finished(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning('Ingest state persistence failed: %s', type(task.exception()).__name__)

    async def recover(self):
        async with self.app.state.db() as db:
            jobs = (await db.execute(select(IngestJob.file_id, IngestJob.status))).all()
        for file_id, status in jobs:
            if status == 'processing':
                await self.fail(file_id, '服务中断，导入未完成，请重新导入')
        orphans = await run_in_threadpool(orphan_directories, self.app.state.settings.ingest_temp_dir,
                                        {file_id for file_id, _ in jobs})
        for file_id in orphans:
            await self.cleanup(file_id)

    async def close(self):
        self.closing = True
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # 尚未获得首次执行机会的协程不会进入 run/finally，也需要显式收尾。
        for task in tasks:
            if task.cancelled():
                await self.fail(task.get_name().split(':', 1)[1], '服务关闭，导入已中断，请重新导入')

    async def cleanup(self, file_id):
        await run_in_threadpool(clean_job_directory, self.app.state.settings.ingest_temp_dir, file_id)

    async def fail(self, file_id, message):
        with anyio.CancelScope(shield=True):
            await self.cleanup(file_id)
            async with self.app.state.db() as db:
                await db.execute(update(IngestJob).where(IngestJob.file_id == file_id,
                    IngestJob.status == 'processing').values(status='failed', chunk_count=0,
                                                             error=message[:500], updated_at=utcnow()))
                await db.execute(update(Upload).where(Upload.file_id == file_id,
                                                      Upload.status == 'processing').values(status='failed'))
                await db.commit()

    async def run(self, file_id):
        try:
            async with self.semaphore:
                async with asyncio.timeout(self.app.state.settings.ingest_timeout_seconds):
                    await self.process(file_id)
        except asyncio.CancelledError:
            await self.fail(file_id, '服务关闭，导入已中断，请重新导入')
            raise
        except (ConvertError, EmbeddingError) as exc:
            await self.fail(file_id, str(exc))
        except HTTPException as exc:
            await self.fail(file_id, str(exc.detail))
        except TimeoutError:
            await self.fail(file_id, '导入任务超时，请拆分资料后重试')
        except Exception as exc:
            logger.warning('Ingest failed: %s', type(exc).__name__)
            await self.fail(file_id, '导入失败，请检查资料或向量服务配置后重试')

    async def process(self, file_id):
        async with self.app.state.db() as db:
            upload = await db.get(Upload, file_id)
            if upload is None:
                await self.cleanup(file_id)
                return
            user_id, file_name, storage_name = upload.user_id, upload.file_name, upload.storage_name
        path = job_directory(self.app.state.settings.ingest_temp_dir, file_id) / storage_name
        markdown = await self.app.state.convert(path)
        chunks = await run_in_threadpool(chunk_markdown, markdown, file_name)
        if not chunks:
            raise ConvertError('资料没有可提取的正文，扫描件请先 OCR')
        if len(chunks) > self.app.state.settings.max_chunks_per_file:
            raise ConvertError('资料片段过多，请拆分文件后重新导入')
        vectors = validate_vectors(await self.app.state.embed([chunk.text for chunk in chunks]), len(chunks))
        # 临时文件在状态变为 completed/failed 前清理，轮询结果与清理状态一致。
        await self.cleanup(file_id)
        async with self.app.state.db() as db:
            job = await db.get(IngestJob, file_id, with_for_update=True)
            if job is None or job.status != 'processing':
                return
            db.add_all([Knowledge(file_id=file_id, user_id=user_id, file_name=file_name,
                chunk_text=chunk.text, embedding=vector, chunk_index=index, meta=chunk.metadata)
                for index, (chunk, vector) in enumerate(zip(chunks, vectors))])
            job.status, job.chunk_count, job.error, job.updated_at = 'completed', len(chunks), None, utcnow()
            await db.execute(update(Upload).where(Upload.file_id == file_id).values(status='completed'))
            await db.commit()
