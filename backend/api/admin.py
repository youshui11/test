"""管理员会话汇总及数据库级联删除。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import User, Session, Message
from backend.services.auth import require_admin

router = APIRouter(prefix='/api/admin', tags=['管理'], dependencies=[Depends(require_admin)])


@router.get('/sessions')
async def all_sessions(db: AsyncSession = Depends(get_db)):
    count = select(func.count(Message.id)).where(Message.session_id == Session.session_id).correlate(Session).scalar_subquery()
    last = select(Message.content).where(Message.session_id == Session.session_id).order_by(Message.id.desc()).limit(1).correlate(Session).scalar_subquery()
    rows = (await db.execute(select(Session, User.username, count, last).join(User, Session.user_id == User.id)
                              .order_by(Session.updated_at.desc()))).all()
    return [{'username': username, 'sessionId': session.session_id, 'title': session.title,
             'lastMessage': latest or '暂无消息', 'msgCount': total,
             'createTime': session.created_at.isoformat(), 'updateTime': session.updated_at.isoformat()}
            for session, username, total, latest in rows]


@router.delete('/sessions/{session_id}')
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(Session).where(Session.session_id == session_id))
    if result.rowcount != 1:
        raise HTTPException(404, '会话不存在或已删除')
    await db.commit()
    return {'success': True}
