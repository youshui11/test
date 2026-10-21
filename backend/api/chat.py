"""会话与 SSE 流；回答成功后才原子写入整轮消息。"""
import asyncio
import logging
from functools import partial
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import User, Session, Message, Upload
from backend.models.user import utcnow
from backend.schemas import ChatInput
from backend.services.auth import get_current_user
from backend.services.chat import owned_session, owned_files, public_file, public_message, sse, generation_lock

router = APIRouter(prefix='/api/sessions', tags=['会话'])
logger = logging.getLogger(__name__)


@router.get('')
async def list_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Session).where(Session.user_id == user.id).order_by(Session.updated_at.desc()))).all()
    return [{'sessionId': s.session_id, 'title': s.title, 'updateTime': s.updated_at.isoformat()} for s in rows]


@router.post('', status_code=201)
async def create_session(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = Session(session_id='s_' + uuid4().hex, user_id=user.id, title='新对话')
    db.add(session)
    await db.commit()
    return {'sessionId': session.session_id, 'title': session.title}


@router.get('/{session_id}/messages')
async def get_messages(session_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_session(db, session_id, user, admin_read=True)
    rows = (await db.scalars(select(Message).where(Message.session_id == session_id).order_by(Message.id))).all()
    ids = {file_id for row in rows for file_id in row.file_ids}
    files = {f.file_id: public_file(f) for f in (await db.scalars(select(Upload).where(Upload.file_id.in_(ids)))).all()} if ids else {}
    return [public_message(row, [files[id] for id in row.file_ids if id in files]) for row in rows]


@router.post('/{session_id}/messages')
async def send_message(session_id: str, body: ChatInput, request: Request,
                       user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_session(db, session_id, user)
    await owned_files(db, body.fileIds, user.id)
    question = body.content.strip()
    if not question and not body.fileIds:
        raise HTTPException(422, '请输入消息或添加附件')
    if not question:
        question = '请总结附件的主要内容。'
    # 结束鉴权查询事务；流内使用独立会话，不依赖 FastAPI yield 依赖释放时机。
    user_id = user.id
    await db.commit()

    async def events():
        try:
            async with asyncio.timeout(request.app.state.settings.model_timeout_seconds):
                async with generation_lock(request.app.state.engine, session_id) as connection:
                    # 复用持锁连接，避免每轮占一条锁连接后再等待第二条池连接。
                    factory = partial(request.app.state.db, bind=connection) if connection is not None else request.app.state.db
                    async with factory() as read_db:
                        target = await owned_session(read_db, session_id, user)
                        version, title = target.version, target.title
                        await owned_files(read_db, body.fileIds, user_id)
                        history_rows = (await read_db.scalars(select(Message).where(Message.session_id == session_id)
                                                              .order_by(Message.id.desc()).limit(12))).all()
                        history = [{'role': m.role, 'content': m.content} for m in reversed(history_rows)]
                        context = await request.app.state.retrieve(read_db, user_id, question, body.fileIds)
                    parts = []
                    length = 0
                    async for delta in request.app.state.answer(history, question, context):
                        if await request.is_disconnected():
                            return
                        length += len(delta)
                        if length > 100000:
                            raise HTTPException(502, '模型回复过长，请缩小问题范围')
                        parts.append(delta)
                        yield sse('delta', {'content': delta})
                    if not parts:
                        raise HTTPException(502, '模型未返回文字，请重试')
                    if await request.is_disconnected():
                        return
                    now = utcnow()
                    async with factory() as write_db:
                        # UPDATE 获取行锁并验证版本；与管理员 DELETE 串行，避免孤立消息。
                        result = await write_db.execute(update(Session).where(Session.session_id == session_id,
                            Session.user_id == user_id, Session.version == version).values(version=version + 1,
                            updated_at=now, title=(body.content.strip() or '附件分析')[:24] if version == 0 else title))
                        if result.rowcount != 1:
                            raise HTTPException(409, '会话已更改或删除，请刷新后重试')
                        answer = Message(msg_id='m_' + uuid4().hex, session_id=session_id, role='ai',
                                         content=''.join(parts), file_ids=[], created_at=now)
                        write_db.add_all([Message(msg_id='m_' + uuid4().hex, session_id=session_id, role='user',
                            content=body.content.strip(), file_ids=body.fileIds, created_at=now), answer])
                        await write_db.commit()
            # 释放生成锁后再通知成功，前端不会因接收 done 后关闭流而打断正常释放。
            yield sse('done', public_message(answer))
        except asyncio.CancelledError:
            raise
        except HTTPException as exc:
            yield sse('error', {'message': str(exc.detail), 'status': exc.status_code})
        except Exception as exc:
            logger.warning('Chat failed: %s', type(exc).__name__)
            yield sse('error', {'message': '生成回复失败，请稍后重试', 'status': 502})

    return StreamingResponse(events(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
