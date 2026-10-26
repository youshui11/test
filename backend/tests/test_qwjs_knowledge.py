"""QWJS 全文工具：真实 SQL 查询、片段顺序、歧义与请求范围。"""
import pytest
import pytest_asyncio
from agno.agent import Agent
from agno.models.deepseek import DeepSeek
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from agent.tools.cx_knowledge import knowledge_scope
from backend.agent_adapter import isolated_copy
from backend.database import Base
from backend.models import Knowledge, Upload, User


@pytest_asyncio.fixture
async def documents():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:',
                                execution_options={'schema_translate_map': {'public': None}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        user = User(username='qwjs-test', password_hash='unused')
        db.add(user)
        await db.flush()
        for file_id, name, parts in [
            ('first', '公司章程.docx', [(2, '第三段'), (0, '第一段'), (1, '第二段')]),
            ('second', '公司章程补充.docx', [(0, '补充全文')]),
            ('dup-a', '同名.pdf', [(0, '甲正文')]),
            ('dup-b', '同名.pdf', [(0, '乙正文')]),
            ('large', '过长.pdf', [(0, '长' * 90001)]),
        ]:
            db.add(Upload(file_id=file_id, user_id=user.id, file_name=name,
                          storage_name=file_id, size=1))
            await db.flush()
            for index, text in parts:
                db.add(Knowledge(file_id=file_id, user_id=user.id, file_name=name,
                                 chunk_index=index, chunk_text=text, embedding=[1.0]))
        await db.commit()
        user_id = user.id
    try:
        yield factory, user_id
    finally:
        await engine.dispose()


async def invoke(documents, name='', file_id='', attachments=()):
    from agent.tools.qwjs_knowledge import make_full_document_tool
    factory, user_id = documents
    async def no_embedding(_):
        raise AssertionError('读取全文不能调用 embedding')
    with knowledge_scope(factory, user_id, attachments, no_embedding):
        tool = make_full_document_tool()
    return await tool.entrypoint(document_name=name, file_id=file_id)


@pytest.mark.asyncio
async def test_exact_name_returns_all_chunks_in_document_order(documents):
    result = await invoke(documents, '公司章程.docx')
    assert result == '第一段\n\n第二段\n\n第三段'


@pytest.mark.asyncio
async def test_title_lookup_and_duplicate_names_require_disambiguation(documents):
    assert await invoke(documents, '章程补充') == '补充全文'
    result = await invoke(documents, '同名.pdf')
    assert '多份' in result
    assert 'dup-a' in result and 'dup-b' in result
    assert '甲正文' not in result and '乙正文' not in result
    assert await invoke(documents, file_id='dup-b') == '乙正文'


@pytest.mark.asyncio
async def test_attachment_scope_missing_identifier_and_no_match(documents):
    assert '未找到' in await invoke(documents, file_id='second', attachments=['first'])
    assert await invoke(documents, attachments=['first']) == '第一段\n\n第二段\n\n第三段'
    assert '请提供' in await invoke(documents)
    assert '未找到' in await invoke(documents, '不存在')
    assert '未找到' in await invoke(documents, '%')


@pytest.mark.asyncio
async def test_large_document_is_not_returned_as_truncated_full_text(documents):
    result = await invoke(documents, file_id='large')
    assert '过长' in result
    assert '长' * 100 not in result


@pytest.mark.asyncio
async def test_missing_login_scope_fails_closed():
    from agent.tools.qwjs_knowledge import make_full_document_tool
    with pytest.raises(ValueError, match='身份'):
        await make_full_document_tool().entrypoint(document_name='公司章程')


@pytest.mark.asyncio
async def test_adapter_binds_a_separate_tool_for_each_request(documents):
    from agent.tools.qwjs_knowledge import make_full_document_tool
    original_tool = make_full_document_tool()
    original = Agent(model=DeepSeek(id='test', api_key='test'), tools=[original_tool])
    factory, user_id = documents
    with knowledge_scope(factory, user_id, ['first'], None):
        first = isolated_copy(original)
    with knowledge_scope(factory, user_id, ['second'], None):
        second = isolated_copy(original)
    assert await first.tools[0].entrypoint() == '第一段\n\n第二段\n\n第三段'
    assert await second.tools[0].entrypoint() == '补充全文'
    assert original.tools[0] is original_tool
    with pytest.raises(ValueError, match='身份'):
        await original_tool.entrypoint(file_id='first')
