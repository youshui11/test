# 文件作用：为普通附件提取文字并按固定 500 字符切分，保持原上传处理规则。
# 关联关系：由 backend/api/upload.py 调用，DOCX/PDF 复用 convert_to_md.py 提取函数。
"""普通附件的文本提取与固定长度切分，独立于聊天检索。"""
from pathlib import Path


def chunk_text(text: str) -> list[str]:
    text = text.replace('\x00', '').strip()
    return [text[i:i + 500] for i in range(0, len(text), 500)]


def extract_text(path: Path, suffix: str) -> str:
    if suffix in {'.txt', '.md'}:
        return path.read_text(encoding='utf-8-sig')
    if suffix == '.docx':
        # 保留普通附件原有的 Word 解压体积限制。
        import zipfile
        with zipfile.ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError('Word 文档解压后过大')
        from agent.documents.convert_to_md import convert_docx
        return convert_docx(path)[0]
    from agent.documents.convert_to_md import convert_pdf
    return convert_pdf(path)[0]
