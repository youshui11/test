from agent.tools.cx_knowledge import make_public_knowledge_tool

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.deepseek import DeepSeek
from agno.os import AgentOS
from agno.team import Team
from agno.team.mode import TeamMode

# =========================================================
# API Keys：替换为你自己的真实 Key；不要提交到 Git
# =========================================================

DEEPSEEK_API_KEY = ""



# =========================================================
# PostgreSQL + pgvector 配置
# 数据库中需要已经存在由 Agno Knowledge 写入的向量数据
# =========================================================

# AgentOS / Team 会话数据
db = SqliteDb(db_file="deepseek_agent.db")

# 检索工具统一位于 agent/tools/cx_knowledge.py，网站调用时绑定登录用户。


search_cx_knowledge = make_public_knowledge_tool()


# CX 子智能体：被 PD 委派时，必须调用 RAG 工具
cx_agent = Agent(
    id="cx-subagent",
    name="CX RAG 子智能体",
    role="从 PostgreSQL pgvector 知识库检索与用户问题最相近的三条数据。",
    model=DeepSeek(
        id="deepseek-v4-flash",
        api_key=DEEPSEEK_API_KEY,
        use_thinking=False,
    ),
    tools=[search_cx_knowledge],
    db=db,
    instructions=[
        "你是 CX RAG 子智能体，始终使用中文。",
        "收到用户问题后，必须调用 search_cx_knowledge。",
        "不要自行编造检索结果。",
        "该工具会直接返回 PostgreSQL 中最相近的 3 条数据。",
    ],
    markdown=True,
)

# PD Team：判断直接回答，还是将问题委派给 CX
pd_team = Team(
    id="pd-team",
    name="PD 中文助手团队",
    model=DeepSeek(
        id="deepseek-v4-flash",
        api_key=DEEPSEEK_API_KEY,
        use_thinking=False,
    ),
    members=[cx_agent],
    mode=TeamMode.coordinate,
    db=db,
    instructions=[
        "你是 PD（问题分诊与协调者），始终使用中文回答。",
        "普通问候、简单聊天、可直接回答的问题：直接回复用户，不要委派。",
        "使用 Markdown 排版，优先保证清晰、简洁、可执行。",
        "先直接给出结论，再说明步骤或依据。",
        "复杂回答使用二级标题（##）分段。",
        "步骤使用有序列表；要点使用无序列表。",
        "仅在确实需要对比多项内容时使用 Markdown 表格。",
        "代码必须放在带语言标识的 Markdown 代码块中。",
        "当用户询问业务资料、产品资料、客户问题、数据库内容，或需要知识库匹配时：委派给 CX RAG 子智能体。",
        "CX 返回检索结果后，直接将结果清晰地展示给用户。",
    ],
    add_history_to_context=True,
    num_history_runs=3,
    markdown=False,
)

# 注册 Team 到 AgentOS
agent_os = AgentOS(
    id="deepseek-backend",
    teams=[pd_team],
    db=db,
    tracing=True,
)

app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(
        app="server:app",
        reload=True,
        port=7777,
    )