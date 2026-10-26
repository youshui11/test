# 文件作用：提供转换 CLI 的公共输入校验、压缩包限制、表格转义和输出约束。
# 关联关系：供 PDF、Word、Excel、PowerPoint、TXT/Markdown 转换脚本复用。
"""转换 CLI 公共输入校验、表格转义及输出约束。"""
import argparse
from contextlib import redirect_stdout
from pathlib import Path
import sys
import zipfile

MAX_TEXT_CHARS = 2_000_000


def check_archive(path):
    with zipfile.ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError('Office 文档解压后过大，请拆分')


def table(rows):
    lines = []
    total = 0
    width = 0
    for row in rows:
        if len(row) > 256:
            raise ValueError('表格列数过多，请拆分')
        cells = [str(value if value is not None else '').replace('\\', '\\\\').replace('|', '\\|')
                 .replace('\r', '').replace('\n', '<br>') for value in row]
        if not any(cells) and not lines:
            continue
        width = max(width, len(cells))
        line = '| ' + ' | '.join(cells) + ' |'
        total += len(line)
        if total > MAX_TEXT_CHARS:
            raise ValueError('表格文本过长，请拆分')
        lines.append(line)
    if lines:
        lines.insert(1, '| ' + ' | '.join(['---'] * width) + ' |')
    return '\n'.join(lines)


def run_cli(converter):
    parser = argparse.ArgumentParser(description='转换资料为 UTF-8 Markdown')
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    try:
        # 第三方库的进度或提示不能污染 Markdown stdout。
        with redirect_stdout(sys.stderr):
            content = converter(args.source).replace('\x00', '').strip()
        if not content:
            raise ValueError('文件没有可提取的文字，扫描件请先 OCR')
        if len(content) > MAX_TEXT_CHARS:
            raise ValueError('转换文本过长，请拆分资料')
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdout.write(content + '\n')
    except Exception as exc:
        # 不输出任意第三方异常内容，避免路径或环境信息进入客户端。
        sys.stderr.write('资料转换失败：' + type(exc).__name__ + '\n')
        raise SystemExit(1) from None
