"""DOCX 段落与表格转 Markdown，复用已有转换器。"""
from agent.tools.common import run_cli, check_archive


def convert(path):
    check_archive(path)
    from agent.tools.convert_to_md import convert_docx
    return convert_docx(path)[0]


def main():
    run_cli(convert)


if __name__ == '__main__':
    main()
