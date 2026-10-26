# 文件作用：按 Markdown 标题、段落、句子、表格和代码结构生成带元信息的语义片段。
# 关联关系：由 agent/dr.py 在转换之后、向量化之前调用，用于知识库资料导入。
"""基于 Markdown 标题、段落、句子、表格和代码结构的语义切分。"""
from dataclasses import dataclass
import re


@dataclass
class Chunk:
    text: str
    metadata: dict


def sentences(text):
    return [item.strip() for item in re.split(r'(?<=[。！？!?；;])\s*|(?<=\.)\s+', text.strip()) if item.strip()]


def prose_parts(text, limit):
    current = ''
    for sentence in sentences(text):
        while len(sentence) > limit:
            if current:
                yield current
                current = ''
            yield sentence[:limit]
            sentence = sentence[limit:]
        if current and len(current) + len(sentence) + 1 > limit:
            yield current
            current = ''
        current += (' ' if current else '') + sentence
    if current:
        yield current


def fence_marker(line):
    return re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)


def closes_fence(line, opening):
    marker = fence_marker(line)
    return bool(marker and marker[1][0] == opening[0] and len(marker[1]) >= len(opening)
                and not marker[2].strip())


def sections(markdown):
    headings = []
    body = []
    fence = None
    for line in markdown.splitlines():
        marker = fence_marker(line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif closes_fence(line, fence):
                fence = None
        heading = re.match(r'^\s{0,3}(#{1,6})\s+(.+?)\s*$', line) if fence is None and not marker else None
        if heading:
            if any(item.strip() for item in body):
                yield ' > '.join(item[1] for item in headings), '\n'.join(body)
            level = len(heading[1])
            title = re.sub(r'\s+#+\s*$', '', heading[2]).strip()
            headings = [item for item in headings if item[0] < level] + [(level, title)]
            body = []
        else:
            body.append(line)
    if any(item.strip() for item in body):
        yield ' > '.join(item[1] for item in headings), '\n'.join(body)


def blocks(body):
    lines = body.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        marker = fence_marker(line)
        if marker:
            group = [line]
            index += 1
            while index < len(lines):
                group.append(lines[index])
                index += 1
                if closes_fence(group[-1], marker[1]):
                    break
            yield 'code', '\n'.join(group)
        elif line.lstrip().startswith('|'):
            group = []
            while index < len(lines) and lines[index].lstrip().startswith('|'):
                group.append(lines[index])
                index += 1
            yield 'table', '\n'.join(group)
        else:
            group = [line]
            index += 1
            while index < len(lines) and lines[index].strip() and not re.match(r'^\s*(`{3,}|~{3,}|\|)', lines[index]):
                group.append(lines[index])
                index += 1
            yield 'prose', '\n'.join(group)


def structural_parts(kind, text, limit):
    if len(text) <= limit:
        yield text
        return
    if kind == 'prose':
        yield from prose_parts(text, limit)
        return
    lines = text.splitlines()
    if kind == 'code':
        start = lines[0]
        end = fence_marker(start)[1]
        content = lines[1:-1] if closes_fence(lines[-1], end) else lines[1:]
        prefix, suffix = start + '\n', '\n' + end
    else:
        prefix = '\n'.join(lines[:2]) + '\n'
        suffix = ''
        content = lines[2:]
    available = limit - len(prefix) - len(suffix)
    if available < 30:
        yield from prose_parts(text, limit)
        return
    current = ''
    for line in content:
        for part in [line[i:i + available] for i in range(0, max(1, len(line)), available)]:
            if current and len(current) + len(part) + 1 > available:
                yield prefix + current + suffix
                current = ''
            current += ('\n' if current else '') + part
    if current:
        yield prefix + current + suffix


def chunk_markdown(markdown: str, source_file: str) -> list[Chunk]:
    result = []
    for path, body in sections(markdown.replace('\x00', '').strip()):
        prefix = (path[:200] + '\n\n') if path else ''
        target = max(200, 600 - len(prefix))
        current = ''
        last_kind = ''
        def emit(text):
            value = prefix + text.strip()
            result.append(Chunk(value, {'source_file': source_file, 'chunk_index': len(result),
                                        'heading_path': path, 'char_count': len(value)}))
        for kind, block in blocks(body):
            for unit in structural_parts(kind, block, target):
                if current and len(current) + len(unit) + 2 > target:
                    emit(current)
                    overlap = ''
                    if last_kind == kind == 'prose':
                        tail = sentences(current)
                        for sentence in reversed(tail[-2:]):
                            candidate = sentence + (' ' + overlap if overlap else '')
                            if len(candidate) <= 160:
                                overlap = candidate
                    current = overlap if len(prefix) + len(overlap) + len(unit) + 2 <= 800 else ''
                current += ('\n\n' if current else '') + unit
                last_kind = kind
        if current:
            emit(current)
    return result
