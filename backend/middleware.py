"""在 multipart 解析前限制上传请求体，包含分块传输的累计字节。"""
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException


class UploadBodyLimit:
    def __init__(self, app, settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') not in {'/api/upload', '/api/ingest'} or scope.get('method') != 'POST':
            return await self.app(scope, receive, send)
        # multipart 字段头和 boundary 留出 256 KiB，文件本身仍由路由严格限制。
        limit = (self.settings.max_ingest_bytes if scope.get('path') == '/api/ingest'
                 else self.settings.max_upload_bytes) + 256 * 1024
        headers = dict(scope.get('headers', []))
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            return await JSONResponse({'detail': 'Content-Length 无效'}, status_code=400)(scope, receive, send)
        if length > limit:
            return await JSONResponse({'detail': '上传请求体过大'}, status_code=413)(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > limit:
                    raise HTTPException(413, '上传请求体过大')
            return message
        await self.app(scope, limited_receive, send)
