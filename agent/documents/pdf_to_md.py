# 文件作用：将 PDF 转成 Markdown，优先保留文档结构，标注图片并拒绝纯扫描件。
# 关联关系：由 converter.py 通过子进程调用，缺少首选 PDF 库时回退到 convert_to_md.py。
"""PDF 优先 PyMuPDF4LLM 保留结构，图片以文字占位；不自动 OCR。"""
from agent.documents.common import run_cli


def convert(path):
    try:
        import pymupdf
        import pymupdf4llm
    except ImportError:
        from agent.documents.convert_to_md import convert_pdf
        return convert_pdf(path)[0]
    with pymupdf.open(path) as doc:
        if doc.needs_pass or doc.page_count > 1000:
            raise ValueError('PDF 加密或页数过多')
        if not any(page.get_text().strip() for page in doc):
            raise ValueError('扫描 PDF 请先 OCR')
        text = pymupdf4llm.to_markdown(doc, show_progress=False, write_images=False,
                                     embed_images=False, ignore_images=True)
        images = [f'[图片占位：第 {i + 1} 页，{len(page.get_images())} 张图片]'
                  for i, page in enumerate(doc) if page.get_images()]
        return text + '\n\n' + '\n'.join(images)


def main():
    run_cli(convert)


if __name__ == '__main__':
    main()
