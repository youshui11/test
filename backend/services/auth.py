"""JWT 签发与数据库角色校验，bcrypt 在工作线程执行。"""
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import User

passwords = CryptContext(schemes=['bcrypt'], deprecated='auto')
bearer = HTTPBearer(auto_error=False)


def issue_token(user, settings):
    return jwt.encode({'sub': str(user.id), 'exp': datetime.now(timezone.utc) +
                       timedelta(minutes=settings.jwt_expire_minutes)},
                      settings.jwt_secret.get_secret_value(), algorithm='HS256')


async def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer),
                           db: AsyncSession = Depends(get_db)):
    try:
        if credentials is None:
            raise ValueError()
        payload = jwt.decode(credentials.credentials, request.app.state.settings.jwt_secret.get_secret_value(),
                             algorithms=['HS256'], options={'require_exp': True, 'require_sub': True})
        user = await db.get(User, int(payload['sub']))
        if user is None:
            raise ValueError()
        return user
    except (JWTError, ValueError, TypeError, KeyError):
        raise HTTPException(401, '登录已失效，请重新登录', headers={'WWW-Authenticate': 'Bearer'})


async def require_admin(user: User = Depends(get_current_user)):
    if user.role != 'admin':
        raise HTTPException(403, '需要管理员权限')
    return user
