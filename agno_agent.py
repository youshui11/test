from agno.agent import Agent
from agno.models.deepseek import DeepSeek

agent = Agent(
    name="DeepSeek 中文助手",
    model=DeepSeek(
        id="deepseek-v4-flash",
        api_key="你的_DeepSeek_API_Key",
    ),
    instructions="你是一个友好、专业的中文 AI 助手。请使用中文回答。",
    markdown=True,
)

agent.print_response("你好，请介绍一下你能做什么。", stream=True)