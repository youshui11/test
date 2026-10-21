"""环境配置；正式启动必须提供独立 JWT 密钥。"""
from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / 'backend/.env', extra='ignore')
    database_url: str = 'postgresql+asyncpg://wd_admin:wd_123@localhost:5432/wendang'
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_expire_minutes: int = Field(default=480, ge=1, le=10080)
    upload_dir: Path = ROOT / 'backend/data/uploads'
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    cors_origins: list[str] = ['http://localhost:7777', 'http://127.0.0.1:7777', 'http://localhost:5173']
    llm_api_key: SecretStr = SecretStr('')
    llm_base_url: str = 'https://api.openai.com/v1'
    llm_model: str = 'gpt-4o'
    llm_config_source: Literal['env', 'server'] = 'env'
    llm_server_config_path: Path = ROOT / 'agent' / 'server.py'
    llm_provider: Literal['openai', 'deepseek'] = 'openai'
    llm_use_thinking: bool | None = None
    embedding_api_key: SecretStr = SecretStr('')
    embedding_base_url: str = 'https://api.openai.com/v1'
    embedding_model: str = 'text-embedding-3-small'
    model_timeout_seconds: float = Field(default=120, gt=0, le=600)
    max_chunks_per_file: int = Field(default=2000, ge=1)

    @model_validator(mode='after')
    def resolve_model_config(self):
        if self.llm_config_source == 'server':
            from backend.server_config import read_server_model_config
            config = read_server_model_config(self.llm_server_config_path)
            self.llm_api_key = SecretStr(config.pop('llm_api_key'))
            for name, value in config.items():
                setattr(self, name, value)
        return self
