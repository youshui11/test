import json

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.models.deepseek import DeepSeek
from agno.os import AgentOS
from agno.team import Team
from agno.team.mode import TeamMode
from agno.tools import tool
from agno.vectordb.pgvector import PgVector, SearchType

# =========================================================
# API Keys：替换为你自己的真实 Key；不要提交到 Git
# =========================================================

DEEPSEEK_API_KEY = ""
OPENAI_API_KEY = ""



# =========================================================
# PostgreSQL + pgvector 配置
# 数据库中需要已经存在由 Agno Knowledge 写入的向量数据
# =========================================================
PG_DB_URL = "postgresql+psycopg://wd_admin:wd_123@127.0.0.1:5432/wendang"
PG_TABLE_NAME = "knowledge_base"

# AgentOS / Team 会话数据
db = SqliteDb(db_file="deepseek_agent.db")

# RAG 知识库：使用 text-embedding-3-small 为查询和文档生成向量
cx_knowledge = Knowledge(
    vector_db=PgVector(
        table_name=PG_TABLE_NAME,
        db_url=PG_DB_URL,
        search_type=SearchType.vector,
        embedder=OpenAIEmbedder(
            id="text-embedding-3-small",
            api_key=OPENAI_API_KEY,
        ),
    ),
)


@tool(
    name="search_cx_knowledge",
    description="在 PostgreSQL pgvector 知识库中检索与用户问题最相近的 3 条数据。",
    stop_after_tool_call=True,
)
def search_cx_knowledge(query: str) -> str:
    """
    使用 text-embedding-3-small 将 query 向量化，
    并从 PostgreSQL/pgvector 返回语义最接近的 3 条数据。
    """
    results = cx_knowledge.search(query, max_results=3)

    # 返回原始命中内容，确保最多 3 条
    return json.dumps(
        {
            "query": query,
            "count": len(results),
            "results": [
                {
                    "rank": index,
                    "content": document.content,
                }
                for index, document in enumerate(results, start=1)
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


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
        "当用户询问业务资料、产品资料、客户问题、数据库内容，或需要知识库匹配时：委派给 CX RAG 子智能体。",
        "CX 返回检索结果后，直接将结果清晰地展示给用户。",
    ],
    add_history_to_context=True,
    num_history_runs=3,
    markdown=True,
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