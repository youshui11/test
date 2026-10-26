# 文件作用：验证附件上传被取消时关闭上传缓冲文件并删除未完成的本地副本。
# 关联关系：测试 upload.py 的取消和清理流程，复用 API 测试客户端。
"""模拟 multipart 落盘文件在上游取消时仍完成关闭及磁盘清理。"""
import tempfile
import anyio
import pytest
from fastapi import Request, UploadFile
from sqlalchemy import select
from backend.models import User, Upload
from backend.api.upload import upload
from tests.helpers import account


@pytest.mark.asyncio
async def test_cancelled_upload_closes_spool_and_removes_local_copy(client, monkeypatch):
    account(client)
    spool = tempfile.SpooledTemporaryFile(max_size=1)
    spool.write(b'test text')
    spool.seek(0)
    file = UploadFile(file=spool, filename='cancel.txt')
    original_close = file.close
    closed = []
    async def close():
        await anyio.sleep(0)
        await original_close()
        closed.append(True)
    monkeypatch.setattr(file, 'close', close)
    async with client.app.state.db() as db:
        user = await db.scalar(select(User).where(User.username == 'alice'))
        with anyio.CancelScope() as scope:
            async def cancel_embedding(chunks):
                assert not db.in_transaction(), '向量化期间不得占用鉴权事务'
                scope.cancel()
                await anyio.sleep(0)
            client.app.state.embed = cancel_embedding
            await upload(Request({'type': 'http', 'app': client.app}), file, user, db)
        assert closed == [True]
        assert list(client.app.state.settings.upload_dir.iterdir()) == []
        assert await db.scalar(select(Upload.file_id)) is None
