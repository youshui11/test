# 文件作用：提供各测试分类共享的临时 SQLite FastAPI 客户端 fixture。
# 关联关系：由 pytest 自动加载，使用临时目录隔离数据库、附件和导入任务。
import pytest


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    from backend.config import Settings
    from backend.server import create_app
    app = create_app(Settings(database_url=f'sqlite+aiosqlite:///{tmp_path / "test.db"}',
                              llm_config_source='env', llm_api_key='',
                              jwt_secret='test-secret-with-at-least-32-characters',
                              upload_dir=tmp_path / 'uploads', ingest_temp_dir=tmp_path / 'ingest'))
    import asyncio
    from backend.database import Base
    async def setup():
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(setup())
    with TestClient(app) as connection:
        yield connection
