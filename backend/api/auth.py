# 文件作用：提供普通用户注册和登录接口，校验输入并签发登录令牌。
# 关联关系：连接 schemas、User 模型及 services/auth.py 的密码哈希和 JWT 功能。
"""用户注册和登录接口。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from backend.database import get_db
from backend.models import User
from backend.schemas import Credentials, LoginInput
from backend.services.auth import passwords, issue_token

router = APIRouter(prefix='/api', tags=['认证'])
# 缺少用户时也执行一次校验，避免快速返回暴露账号是否存在。
DUMMY_HASH = passwords.hash('unusable-random-dummy-password')


@router.post('/users', status_code=201)
async def register(body: Credentials, db: AsyncSession = Depends(get_db)):
    user = User(username=body.username.lower(), password_hash=await run_in_threadpool(passwords.hash, body.password), role='user')
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, '该账号已被注册')
    return {'username': user.username, 'role': user.role}


@router.post('/login')
async def login(body: LoginInput, request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.username == body.username.lower()))
    valid = await run_in_threadpool(passwords.verify, body.password if len(body.password.encode()) <= 72 else '',
                                   user.password_hash if user else DUMMY_HASH)
    if not valid or not user:
        raise HTTPException(401, '账号或密码错误')
    return {'token': issue_token(user, request.app.state.settings), 'role': user.role, 'username': user.username}
