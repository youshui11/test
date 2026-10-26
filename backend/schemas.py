# 文件作用：定义注册、登录和聊天请求的 Pydantic 校验规则。
# 关联关系：由认证及聊天接口使用；维护命令创建管理员时复用 Credentials 校验。
"""请求校验；客户端不能通过注册设置角色。"""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_]+$')
    password: str = Field(min_length=6, max_length=64)

    @field_validator('password')
    @classmethod
    def valid_password(cls, value):
        if not value.strip() or len(value.encode('utf-8')) > 72:
            raise ValueError('密码不能为空，UTF-8 编码不能超过 72 字节')
        return value


class ChatInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(default='', max_length=10000)
    fileIds: list[str] = Field(default_factory=list, max_length=20)

    @field_validator('fileIds')
    @classmethod
    def valid_ids(cls, values):
        if any(len(v) > 64 for v in values):
            raise ValueError('附件 ID 无效')
        return list(dict.fromkeys(values))
