# 文件作用：校验 DOCX 压缩包并提取有序段落和表格，输出 Markdown。
# 关联关系：由 converter.py 调用，复用 common.py 和 convert_to_md.py 的 Word 提取实现。
"""DOCX 段落与表格转 Markdown，复用已有转换器。"""
from agent.documents.common import run_cli, check_archive


def convert(path):
    check_archive(path)
    from agent.documents.convert_to_md import convert_docx
    return convert_docx(path)[0]


def main():
    run_cli(convert)


if __name__ == '__main__':
    main()
