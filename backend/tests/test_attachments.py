"""附件处理独立于聊天检索，四种现有格式继续支持上传和下载。"""
import asyncio
from io import BytesIO

import pytest
from backend.tests.test_api import client, account


def test_extract_utf8_text_and_markdown(tmp_path):
    from agent.tools.attachments import extract_text, chunk_text
    for suffix in ('.txt', '.md'):
        source = tmp_path / ('附件' + suffix)
        source.write_text('附件测试正文', encoding='utf-8-sig')
        assert extract_text(source, suffix) == '附件测试正文'
    assert chunk_text(' \x00' + '中' * 1201 + '\n') == ['中' * 500, '中' * 500, '中' * 201]


@pytest.mark.parametrize('suffix', ['.txt', '.md', '.docx', '.pdf'])
def test_upload_formats_after_attachment_migration(client, suffix):
    from sqlalchemy import select
    from backend.models import Knowledge

    expected = 'Attachment test content' if suffix == '.pdf' else '附件测试正文'
    if suffix == '.docx':
        from docx import Document
        document = Document()
        document.add_paragraph(expected)
        buffer = BytesIO()
        document.save(buffer)
        payload = buffer.getvalue()
    elif suffix == '.pdf':
        import pymupdf
        with pymupdf.open() as document:
            document.new_page().insert_text((72, 72), expected)
            payload = document.tobytes()
    else:
        payload = expected.encode('utf-8')

    async def embedding(texts):
        assert expected in '\n'.join(texts)
        return [[1.] + [0.] * 1535 for _ in texts]

    client.app.state.embed = embedding
    headers = account(client)
    response = client.post('/api/upload', headers=headers, files={'file': ('附件' + suffix, payload)})
    assert response.status_code == 201, response.text
    metadata = response.json()
    assert client.get(metadata['url'], headers=headers).content == payload

    async def verify():
        async with client.app.state.db() as db:
            chunks = (await db.scalars(select(Knowledge).where(Knowledge.file_id == metadata['fileId']))).all()
            assert chunks and expected in ''.join(chunk.chunk_text for chunk in chunks)
            assert all(len(chunk.embedding) == 1536 for chunk in chunks)
    asyncio.run(verify())
