#!/usr/bin/env python3
# 文件作用：实现 DOCX/PDF 基础内容提取，以及独立批量转换并保存 Markdown 的命令。
# 关联关系：供普通附件及 Word/PDF 转换器复用，也可按 agent/documents/README.md 独立运行。
"""Convert local DOCX and text-based PDF files to UTF-8 Markdown."""

import argparse
import re
import sys
from pathlib import Path


SUPPORTED = {'.docx', '.pdf'}
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'ziliao' / 'md'
INSTALL_COMMAND = 'python -m pip install -r "{}"'.format(Path(__file__).resolve().parents[2] / 'requirements' / 'runtime.txt')


def escape(text):
    """Escape literal Markdown, retaining line breaks."""
    return re.sub(r'([\\`*_{}\[\]<>|#])', r'\\\1', text or '')


def markdown_table(rows):
    if not rows:
        return ''
    width = max(map(len, rows))
    if not width:
        return ''
    lines = []
    for row in rows:
        cells = [escape(cell).replace('\r', '').replace('\n', '<br>')
                 for cell in row]
        cells += [''] * (width - len(cells))
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines.insert(1, '| ' + ' | '.join(['---'] * width) + ' |')
    return '\n'.join(lines)


def convert_docx(source):
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(source)
    blocks = []
    warnings = []
    if doc.element.xpath('.//w:drawing | .//w:pict'):
        warnings.append('文档包含图片；当前仅转换文字和表格，不导出图片。')
    # Walk XML blocks rather than doc.paragraphs so tables stay in order.
    for element in doc.element.body:
        if element.tag == qn('w:tbl'):
            table = Table(element, doc)
            blocks.append(markdown_table([[cell.text for cell in row.cells]
                                          for row in table.rows]))
        elif element.tag == qn('w:p'):
            paragraph = Paragraph(element, doc)
            text = escape(paragraph.text.strip())
            if not text:
                continue
            style = paragraph.style.name if paragraph.style is not None else ''
            heading = re.match(r'(?:Heading|标题)\s*(\d+)', style, re.I)
            if style.lower() == 'title':
                text = '# ' + text
            elif heading:
                text = '#' * min(int(heading[1]), 6) + ' ' + text
            else:
                num_pr = paragraph._p.xpath('./w:pPr/w:numPr')
                if num_pr or style.lower().startswith('list'):
                    # Word numbering definitions may describe bullets or numbers.
                    numbered = 'number' in style.lower()
                    depth = 0
                    if num_pr:
                        ilvl = num_pr[0].find(qn('w:ilvl'))
                        depth = int(ilvl.get(qn('w:val'), '0')) if ilvl is not None else 0
                        num_id = num_pr[0].find(qn('w:numId'))
                        if num_id is not None:
                            numbering = doc.part.numbering_part.element
                            nums = numbering.xpath('./w:num')
                            num = next((n for n in nums if n.get(qn('w:numId')) ==
                                        num_id.get(qn('w:val'))), None)
                            if num is not None:
                                abstract = num.find(qn('w:abstractNumId'))
                                if abstract is not None:
                                    for definition in numbering.xpath('./w:abstractNum'):
                                        if definition.get(qn('w:abstractNumId')) == abstract.get(qn('w:val')):
                                            for level in definition.findall(qn('w:lvl')):
                                                fmt = level.find(qn('w:numFmt'))
                                                if level.get(qn('w:ilvl')) == str(depth) and fmt is not None:
                                                    numbered = fmt.get(qn('w:val')) != 'bullet'
                    text = '  ' * min(depth, 8) + ('1. ' if numbered else '- ') + text
            blocks.append(text)
    if not blocks:
        raise ValueError('未找到可转换的文字或表格')
    return '\n\n'.join(blocks) + '\n', warnings


def convert_pdf(source):
    import pdfplumber

    pages = []
    warnings = []
    found_text = False
    with pdfplumber.open(source) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            if not (page.extract_text() or '').strip():
                warnings.append(f'第 {page_number} 页无可提取文字，可能需要 OCR。')
                pages.append(f'<!-- 第 {page_number} 页 -->\n\n> 此页未提取到文字，需要 OCR 或人工检查。')
                continue
            found_text = True
            tables = page.find_tables()

            def outside_tables(obj):
                if obj.get('object_type') != 'char':
                    return True
                x = (obj['x0'] + obj['x1']) / 2
                y = (obj['top'] + obj['bottom']) / 2
                return not any(t.bbox[0] <= x <= t.bbox[2] and
                               t.bbox[1] <= y <= t.bbox[3] for t in tables)

            body = page.filter(outside_tables)
            elements = []
            previous = None
            for line in body.extract_text_lines():
                height = line['bottom'] - line['top']
                # Keep nearby, equally sized lines in the same paragraph.
                if (previous is not None and elements and
                        0 <= line['top'] - previous['bottom'] <= max(3, height * 0.85) and
                        abs(height - (previous['bottom'] - previous['top'])) < 1 and
                        not any(previous['bottom'] <= table.bbox[1] < line['top'] for table in tables)):
                    top, text = elements[-1]
                    elements[-1] = (top, text + '\n' + escape(line['text']))
                else:
                    elements.append((line['top'], escape(line['text'])))
                previous = line
            elements += [(table.bbox[1], markdown_table(table.extract()))
                         for table in tables]
            elements.sort(key=lambda item: item[0])
            content = '\n\n'.join(text for _, text in elements if text)
            pages.append(f'<!-- 第 {page_number} 页 -->\n\n{content}')
    if not found_text:
        raise ValueError('整个 PDF 无可提取文字，可能是扫描件；请先进行 OCR 再转换')
    return '\n\n'.join(pages) + '\n', warnings


def convert_file(source: str, output_dir: str | None = None, overwrite: bool = False) -> dict:
    """Convert a PDF or DOCX to Markdown and save it locally.

    Args:
        source: Path to the PDF or DOCX file.
        output_dir: Output folder; defaults to the project's ziliao/md folder.
        overwrite: Whether to replace an existing Markdown file.

    Returns:
        A dictionary containing output_path, skipped, and warnings.
    """
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f'文件不存在：{source_path}')
    if source_path.suffix.lower() not in SUPPORTED:
        raise ValueError('仅支持 .docx 和 .pdf 文件')
    folder = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    target = (folder / (source_path.name + '.md')).resolve()
    if target.exists() and not overwrite:
        return {'output_path': str(target), 'skipped': True, 'warnings': []}
    converter = convert_docx if source_path.suffix.lower() == '.docx' else convert_pdf
    markdown, warnings = converter(source_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w' if overwrite else 'x', encoding='utf-8', newline='\n') as stream:
        stream.write(markdown)
    return {'output_path': str(target), 'skipped': False, 'warnings': warnings}


def main(argv=None):
    parser = argparse.ArgumentParser(description='将 PDF / Word (.docx) 转换为 UTF-8 Markdown')
    parser.add_argument('inputs', nargs='+', type=Path, help='文件或文件夹，可传入多个')
    parser.add_argument('-o', '--output', type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f'输出文件夹（默认：{DEFAULT_OUTPUT_DIR}）')
    parser.add_argument('-r', '--recursive', action='store_true', help='递归处理子文件夹')
    parser.add_argument('--overwrite', action='store_true', help='允许覆盖已有 Markdown')
    args = parser.parse_args(argv)
    jobs = {}
    failed = 0
    for input_path in args.inputs:
        source = input_path.resolve()
        if source.is_file() and source.suffix.lower() in SUPPORTED:
            jobs.setdefault(source, args.output / (source.name + '.md'))
        elif source.is_dir():
            files = source.rglob('*') if args.recursive else source.iterdir()
            for file in sorted(files):
                if file.is_file() and file.suffix.lower() in SUPPORTED and not file.name.startswith('~$'):
                    relative = file.relative_to(source)
                    jobs.setdefault(file.resolve(), args.output / relative.parent / (file.name + '.md'))
        else:
            print(f'[失败] {source}：路径不存在或格式不支持（仅 .docx、.pdf）', file=sys.stderr)
            failed += 1
    if not jobs:
        print('未找到可转换的 .docx / .pdf 文件', file=sys.stderr)
        return 1
    completed = skipped = 0
    destinations = {}
    for source, target in jobs.items():
        target_key = target.resolve()
        if target_key in destinations:
            print(f'[失败] 输出重名：{source} 与 {destinations[target_key]} -> {target}', file=sys.stderr)
            failed += 1
            continue
        destinations[target_key] = source
        if target.exists() and not args.overwrite:
            print(f'[跳过] 已存在：{target}')
            skipped += 1
            continue
        try:
            result = convert_file(str(source), str(target.parent), args.overwrite)
            if result['skipped']:
                print(f'[跳过] 已存在：{target}')
                skipped += 1
                continue
            completed += 1
            print(f'[完成] {source} -> {target}')
            for warning in result['warnings']:
                print(f'[提示] {source.name}：{warning}', file=sys.stderr)
        except ModuleNotFoundError as exc:
            failed += 1
            print(f'[失败] 缺少依赖 {exc.name}；请运行 {INSTALL_COMMAND}',
                  file=sys.stderr)
        except Exception as exc:
            failed += 1
            print(f'[失败] {source}：{exc}', file=sys.stderr)
    print(f'转换完成：成功 {completed}，跳过 {skipped}，失败 {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    for output_stream in (sys.stdout, sys.stderr):
        if hasattr(output_stream, 'reconfigure'):
            output_stream.reconfigure(encoding='utf-8', errors='replace')
    try:
        sys.exit(main())
    except ModuleNotFoundError as exc:
        print(f'缺少依赖：{exc.name}。请运行 {INSTALL_COMMAND}', file=sys.stderr)
        sys.exit(1)
