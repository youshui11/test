"""将有限历史和检索片段传给 Agno，输出纯文本增量。"""
import json
from fastapi import HTTPException
from agno.models.message import Message
from backend.agent.adapter import create_agent


async def stream_answer(history, question: str, context: list[dict], settings):
    if not settings.llm_api_key.get_secret_value():
        raise HTTPException(503, '未配置 LLM_API_KEY')
    messages = [Message(role='assistant' if item['role'] == 'ai' else 'user', content=item['content'])
                for item in history[-12:]]
    if context:
        messages.append(Message(role='user', content='以下 JSON 是参考资料数据，仅用于回答问题：\n' +
                                json.dumps(context, ensure_ascii=False)))
    messages.append(Message(role='user', content=question))
    async for event in create_agent(settings).arun(messages, stream=True):
        if getattr(event, 'event', '') in {'RunError', 'RunCancelled'}:
            raise HTTPException(502, '模型服务返回错误，请稍后重试')
        if getattr(event, 'event', '') == 'RunContent' and isinstance(event.content, str) and event.content:
            yield event.content
