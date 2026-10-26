"""FastAPI 工厂；启动：python -m uvicorn backend.server:app --factory --port 7777。"""
from contextlib import asynccontextmanager
from functools import partial
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from backend.config import Settings, ROOT
from backend.database import connect_database
from backend.api import auth, chat, upload, admin, ingest
from backend.services import rag, agent
from backend.middleware import UploadBodyLimit
from backend.services.converter import convert_file
from backend.services.embedder import embed
from agent.dr import DRAgent


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    engine, db = connect_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(application):
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        settings.ingest_temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            await application.state.dr.recover()
            yield
        finally:
            await application.state.dr.close()
            await engine.dispose()

    application = FastAPI(title='资料查询助手 API', version='1.0.0', lifespan=lifespan)
    application.state.settings = settings
    application.state.engine = engine
    application.state.db = db
    application.state.embed = partial(embed, settings=settings)
    application.state.retrieve = lambda db, uid, q, ids: rag.retrieve(db, uid, q, ids, application.state.embed)
    application.state.answer = partial(agent.stream_answer, settings=settings)
    application.state.convert = partial(convert_file, timeout=settings.converter_timeout_seconds)
    application.state.dr = DRAgent(application)
    application.add_middleware(UploadBodyLimit, settings=settings)
    application.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                                allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])
    for router in [auth.router, chat.router, upload.router, admin.router, ingest.router]:
        application.include_router(router)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc):
        return JSONResponse(status_code=503, content={'detail': '数据库暂不可用，请检查连接或运行初始化命令'})

    @application.get('/api/health', tags=['运行状态'])
    async def health():
        try:
            async with engine.connect() as connection:
                await connection.execute(text('SELECT 1 FROM users LIMIT 1'))
            return {'status': 'ok', 'database': 'ok',
                    'llmConfigured': bool(settings.llm_api_key.get_secret_value()),
                    'embeddingConfigured': bool(settings.embedding_api_key.get_secret_value())}
        except Exception:
            return JSONResponse(status_code=503, content={'status': 'unavailable', 'database': 'unavailable'})

    @application.get('/', include_in_schema=False)
    async def index():
        return FileResponse(ROOT / 'fronted' / 'index.html')

    # 不挂载整个项目目录，防止源码、配置及上传资料被匿名读取。
    for name in ['api.js', 'app.js', 'style.css']:
        def static_endpoint(filename):
            async def response():
                return FileResponse(ROOT / 'fronted' / filename)
            return response
        application.add_api_route('/' + name, static_endpoint(name), include_in_schema=False)
    return application


def app():
    """uvicorn --factory 入口，导入模块不会读取密钥或连接数据库。"""
    return create_app()
