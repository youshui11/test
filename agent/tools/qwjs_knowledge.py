"""QWJS 按文档标识读取已入库的完整正文，不使用向量相似片段代替全文。"""
import json

from agno.tools import tool
from sqlalchemy import func, select

from agent.tools.cx_knowledge import get_knowledge_scope, public_knowledge


MAX_FULL_TEXT_CHARS = 90000


def make_full_document_tool():
    """Bind the full-text tool to this request's login and attachment scope."""
    scope = get_knowledge_scope()

    @tool(name='get_document_full_text',
          description='按文件名、标题或文档 ID 读取共享知识库中某一文档的全部已入库正文。',
          stop_after_tool_call=True)
    async def get_document_full_text(document_name: str = '', file_id: str = '') -> str:
        """Read every stored chunk of one document in its original chunk order.

        Args:
            document_name: Exact file name or a distinctive part of the document title.
            file_id: Document ID returned by retrieval; preferred when names are ambiguous.

        Returns:
            JSON with status, source identifiers and content when found; otherwise
            clarification candidates or an explicit failure status. No truncated full text.
        """
        if scope is None:
            raise ValueError('QWJS 全文工具未绑定登录身份，拒绝查询资料')
        name, identifier = document_name.strip(), file_id.strip()

        def result(status, **fields):
            if status == "found":
                return fields["content"]

            if status == "ambiguous":
                lines = [
                    fields.get("message", "找到多份文档，请选择：")
                ]
                for item in fields.get("candidates", []):
                    lines.append(
                        f"- {item['fileName']}（文档 ID：{item['fileId']}）"
                    )
                return "\n".join(lines)

            return fields.get("message", "未能获取文档全文，请核对文档名称。")

        if not name and not identifier and not scope.file_ids:
            return result('needs_identifier', message='请提供文件名、文档标题、文档 ID 或指定附件。')
        table = public_knowledge
        filters = []
        if scope.file_ids:
            filters.append(table.c.file_id.in_(scope.file_ids))
        if identifier:
            filters.append(table.c.file_id == identifier)
        async with scope.factory() as db:
            candidates = select(table.c.file_id, table.c.file_name).where(*filters).distinct().order_by(
                table.c.file_id, table.c.file_name)
            if name:
                # Exact names take precedence; title fallback treats %/_ literally.
                matches = (await db.execute(candidates.where(table.c.file_name == name).limit(6))).all()
                if not matches:
                    matches = (await db.execute(candidates.where(
                        table.c.file_name.icontains(name, autoescape=True)).limit(6))).all()
            else:
                matches = (await db.execute(candidates.limit(6))).all()
            if not matches:
                return result('not_found', message='未找到该文档的已入库正文，请核对标识或附件范围。')
            if len(matches) != 1:
                return result('ambiguous', message='找到多份文档，请指定文档 ID；以下最多列出 6 个候选。',
                              candidates=[{'fileId': row.file_id, 'fileName': row.file_name} for row in matches])
            match = matches[0]
            selected = [*filters, table.c.file_id == match.file_id, table.c.file_name == match.file_name]
            count, length = (await db.execute(select(func.count(table.c.id),
                func.sum(func.length(table.c.chunk_text))).where(*selected))).one()
            source = {'fileId': match.file_id, 'fileName': match.file_name}
            if (length or 0) + max(0, count - 1) * 2 > MAX_FULL_TEXT_CHARS:
                return result('too_large', **source, message='文档过长，无法一次返回全文，请按章节查询或下载原文件。')
            chunks = (await db.scalars(select(table.c.chunk_text).where(*selected).order_by(
                table.c.chunk_index.asc().nulls_last(), table.c.id))).all()
        if not chunks:
            return result('not_found', message='未找到该文档的已入库正文。')
        content = '\n\n'.join(chunks)
        if len(content) > MAX_FULL_TEXT_CHARS:
            return result('too_large', **source, message='文档过长，请按章节查询或下载原文件。')
        return result('found', **source, chunkCount=len(chunks), content=content,
                      note='以下为按顺序拼接的全部入库片段，可能包含切分时的重复上下文；排版不保证与原文件一致。')

    return get_document_full_text
