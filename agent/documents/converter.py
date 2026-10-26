# 文件作用：按扩展名调度文档转换子进程，限制输出并处理超时、取消和进程回收。
# 关联关系：由应用装配为 app.state.convert，供 DR 调用 agent.documents 下的格式转换命令。
"""按扩展名在受控子进程中执行 Markdown 转换，取消/超时回收子进程。"""
import asyncio
import os
from pathlib import Path
import sys
import anyio
from backend.config import ROOT

CONVERTERS = {'.pdf': 'pdf_to_md', '.docx': 'docx_to_md', '.xlsx': 'excel_to_md',
              '.xls': 'excel_to_md', '.pptx': 'pptx_to_md', '.txt': 'txt_to_md', '.md': 'txt_to_md'}


class ConvertError(Exception):
    """可向用户展示的转换错误。"""


async def convert_file(path: Path, timeout: float = 120) -> str:
    module = CONVERTERS.get(path.suffix.lower())
    if module is None:
        raise ConvertError('不支持的文件格式')
    environment = dict(os.environ, PYTHONIOENCODING='utf-8')
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'agent.documents.' + module,
        str(path.resolve()), cwd=ROOT, env=environment, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    try:
        async with asyncio.timeout(timeout):
            parts = []
            size = 0
            while data := await process.stdout.read(64 * 1024):
                size += len(data)
                if size > 8 * 1024 * 1024:
                    raise ConvertError('转换文本过长，请拆分资料')
                parts.append(data)
            output = b''.join(parts)
            await process.communicate()
        if process.returncode != 0:
            raise ConvertError('资料转换失败，请检查文件格式、编码，扫描 PDF 请先 OCR')
        text = output.decode('utf-8').strip()
        if not text:
            raise ConvertError('资料没有可提取的文字')
        return text
    except TimeoutError:
        raise ConvertError('资料转换超时，请拆分资料后重试') from None
    finally:
        with anyio.CancelScope(shield=True):
            if process.returncode is None:
                process.kill()
            # 排空剩余管道并关闭传输，避免 Windows 事件循环关闭时遗留句柄。
            await process.communicate()
