# 文件作用：封装会话与附件归属校验、跨进程生成锁、消息序列化及 SSE 格式。
# 关联关系：供聊天、附件及管理接口使用；生成锁保护同一会话的并发回答。
"""会话校验、跨进程生成锁和消息序列化。"""
import asyncio
import json
import anyio
from contextlib import asynccontextmanager
from fastapi import HTTPException
from sqlalchemy import select, text
from backend.models import Session, Upload, Message


async def owned_session(db, session_id, user, admin_read=False):
    query = select(Session).where(Session.session_id == session_id)
    if not (admin_read and user.role == 'admin'):
        query = query.where(Session.user_id == user.id)
    session = await db.scalar(query)
    if session is None:
        raise HTTPException(404, '会话不存在或无权访问')
    return session


async def owned_files(db, ids, user_id):
    if not ids:
        return []
    files = (await db.scalars(select(Upload).where(Upload.file_id.in_(ids), Upload.user_id == user_id))).all()
    by_id = {f.file_id: f for f in files}
    if len(by_id) != len(ids):
        raise HTTPException(404, '附件不存在或无权访问')
    return [by_id[file_id] for file_id in ids]


def public_file(file):
    return {'fileId': file.file_id, 'fileName': file.file_name, 'size': file.size,
            'url': f'/api/files/{file.file_id}'}


def public_message(message, files=None):
    return {'msgId': message.msg_id, 'role': message.role, 'content': message.content,
            'files': files or [], 'time': message.created_at.isoformat()}


def sse(event, data):
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


@asynccontextmanager
async def generation_lock(engine, session_id):
    if engine.dialect.name == 'postgresql':
        # session-level advisory lock 不需要在模型生成期间保持数据库事务。
        async with engine.connect() as conn:
            acquired = await conn.scalar(text('SELECT pg_try_advisory_lock(hashtextextended(:sid, 0))'), {'sid': session_id})
            await conn.commit()
            if not acquired:
                raise HTTPException(409, '此会话正在生成回复，请稍后再试')
            try:
                yield conn
            finally:
                async def release():
                    try:
                        await conn.execute(text('SELECT pg_advisory_unlock(hashtextextended(:sid, 0))'), {'sid': session_id})
                        await conn.commit()
                    except BaseException:
                        # 释放失败不能让仍带会话锁的物理连接回到连接池。
                        await conn.invalidate()
                        raise
                    finally:
                        await conn.close()
                # AnyIO level cancellation 会反复取消 await；原生 asyncio.shield
                # 本身不足以保护父任务后续等待，也保护外层连接关闭前的归还步骤。
                with anyio.CancelScope(shield=True):
                    task = asyncio.create_task(release())
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        await task
                        raise
    else:
        # 测试引擎以版本条件更新保证不会覆盖并发写入。
        yield None
