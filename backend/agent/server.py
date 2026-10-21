from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.deepseek import DeepSeek
from agno.os import AgentOS

# 本地 SQLite：保存会话与运行时数据
db = SqliteDb(db_file="deepseek_agent.db")

# 定义 DeepSeek 智能体
deepseek_agent = Agent(
    id="deepseek-assistant",
    name="DeepSeek 中文助手",
    model=DeepSeek(
        id="deepseek-v4-flash",
        api_key="你的_DeepSeek_API_Key",
        use_thinking=False,  # 可选：关闭思考模式以获得更快响应
    ),
    db=db,
    instructions="你是一个友好、专业的中文 AI 助手。请使用中文回答。",
    add_history_to_context=True,
    num_history_runs=3,
    markdown=True,
)

# 将 Agent 注册为后端服务
agent_os = AgentOS(
    id="deepseek-backend",
    agents=[deepseek_agent],
    db=db,
    tracing=True,
)

# FastAPI 应用对象
app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(
        app="server:app",
        reload=True,  # 开发时文件修改后自动重启
        port=7777,
    )