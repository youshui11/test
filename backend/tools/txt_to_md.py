"""UTF-8 TXT/Markdown 透传；python -m backend.tools.txt_to_md 文件路径。"""
from backend.tools.common import run_cli


def convert(path):
    return path.read_text(encoding='utf-8-sig')


def main():
    run_cli(convert)


if __name__ == '__main__':
    main()
