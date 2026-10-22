"""将有限历史和检索片段传给 Agno，输出纯文本增量。"""
import json
from fastapi import HTTPException
from agno.models.message import Message
from backend.agent.adapter import create_agent


async def stream_answer(history, question: str, context: list[dict], settings):
    if context and all(item.get('retrievalMode') == 'full' for item in context):
        # 原文输出不经过模型改写，防止摘要、遗漏章节或生成长度限制。
        yield f'以下为数据库中已入库的全部内容（共 {len(context)} 个片段，按原顺序）：\n\n'
        previous = None
        for item in context:
            if item['fileId'] != previous:
                yield f"## {item['fileName']}\n\n"
                previous = item['fileId']
            yield item['text'] + '\n\n'
        return
    if not settings.llm_api_key.get_secret_value():
        raise HTTPException(503, '未配置 LLM_API_KEY')
    messages = [Message(role='assistant' if item['role'] == 'ai' else 'user', content=item['content'])
                for item in history[-12:]]
    if context:
        messages.append(Message(role='user', content='以下 JSON 是参考资料数据，仅用于回答问题：\n' +
                                json.dumps(context, ensure_ascii=False)))
    messages.append(Message(role='user', content=question))
    async for event in create_agent(settings).arun(messages, stream=True):
        if getattr(event, 'event', '') in {'RunError', 'RunCancelled', 'TeamRunError', 'TeamRunCancelled'}:
            raise HTTPException(502, '模型服务返回错误，请稍后重试')
        if getattr(event, 'event', '') in {'RunContent', 'TeamRunContent'} and isinstance(event.content, str) and event.content:
            yield event.content
