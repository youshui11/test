# 文件作用：读取 UTF-8 TXT/Markdown 并透传为转换流程的 Markdown 文本。
# 关联关系：由 converter.py 调用，复用 common.py 处理命令行输入和输出。
"""UTF-8 TXT/Markdown 透传；python -m agent.documents.txt_to_md 文件路径。"""
from agent.documents.common import run_cli


def convert(path):
    return path.read_text(encoding='utf-8-sig')


def main():
    run_cli(convert)


if __name__ == '__main__':
    main()
