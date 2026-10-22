# 资料查询助手：后端与文档转换工具

后端位于 `backend/`，使用 FastAPI、SQLAlchemy 异步 PostgreSQL、pgvector、Agno。根目录 Vue 前端已接入真实 HTTP API，可注册、登录、上传资料、查询共享知识库、流式聊天及管理员管理会话。

## 后端快速启动（PowerShell）

在项目根目录运行，建议 Python 3.12：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
./.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

将生成的随机值填入 `backend/.env` 的 `JWT_SECRET`。已生成的本机 `.env` 应保留，**不要重新复制覆盖**。该文件和上传目录已加入 `.gitignore`。

配置数据库及两个模型服务：

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | 默认本机 `wendang` 数据库，使用提示词指定的开发账号 |
| `JWT_SECRET` | 至少 32 字符，部署时独立随机生成 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | OpenAI 兼容聊天接口，例如 DeepSeek 聊天服务；模型名称以实际服务支持为准 |
| `LLM_CONFIG_SOURCE` | `server` 调用 `agent/server.py` 中的 `deepseek_agent`；`env` 则使用 `.env` 中的聊天配置创建智能体 |
| `LLM_PROVIDER` | 使用 `env` 配置时为 `openai` 或 `deepseek` |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | 独立配置 embedding 服务，必须支持 1536 维向量及 `dimensions` 参数；默认 `text-embedding-3-small` |
| `CORS_ORIGINS` | JSON 数组，列出允许访问 API 的前端来源 |
| `MODEL_TIMEOUT_SECONDS` | 单轮检索和生成的总超时，默认 120 秒 |

本机使用 `LLM_CONFIG_SOURCE=server`：后端聊天调用 `D:\work\test7\agent\server.py` 的导出对象，优先 `pd_team`，其次 `deepseek_agent`、`cx_agent`。保留源定义的模型、指令和工具；团队及成员每次请求复制并关闭共享 SQLite 历史，网站历史由 PostgreSQL 管理。修改 `agent/server.py` 后需重启后端。

网站调用适配在 `backend/agent_adapter.py`，Agent 定义在 `agent/server.py`，检索和转换工具统一位于 `agent/tools/`。源 Agent 保留模型、团队和指令定义，检索工具从工具目录加载。

CX 的 `search_cx_knowledge` 工具使用 `agent/tools/cx_knowledge.py` 的异步检索实现，明确查询 `public.knowledge_base` 的 `chunk_text`、`file_name`、`embedding`，最多返回 3 条。所有已登录账号共享全部入库资料，显式指定文件时只查询对应文件，复用网站 embedding 配置，不访问 Agno 默认的 `ai.knowledge_base`。团队与成员每次请求单独复制；未绑定登录身份时拒绝检索。请使用网站后端入口启动，以提供认证和数据库调用上下文。

启动配置校验会静态读取所选导出对象的 `DeepSeek(...)` 模型参数，支持字符串/布尔字面量及同文件顶层常量引用，允许团队和成员分别声明模型；实际运行则导入其中的团队或智能体。若改用环境配置独立创建智能体，可设置 `LLM_CONFIG_SOURCE=env` 并填写 `LLM_*`。

embedding 仍独立配置。只有聊天模型的服务不能自动承担 embedding。缺失密钥会返回明确配置错误，不会生成模拟回答。正式使用上传/RAG 会将资料文字发送给配置的 embedding 服务，命中片段发送给配置的聊天服务。

数据库需预先存在。用 PostgreSQL 超级用户连接 **wendang**，启用扩展一次：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

本机 PostgreSQL 17 也可运行 `./backend/enable-vector.ps1`，在弹出的本地提示中输入超级用户密码。应用账号需要在目标 schema 中建表的权限，无需日常使用超级用户。

```powershell
# 建表；重复运行保留已有数据，不重置账号
./.venv/Scripts/python.exe -m backend.init_db
# 已有数据库启用新导入模块前执行；可重复运行，保留已有资料
./.venv/Scripts/python.exe -m backend.migrate_ingest
# 可选：创建管理员，密码交互输入；已有同名账号不会被自动提权
./.venv/Scripts/python.exe -m backend.init_db --admin admin
# 启动网站后端（智能体定义在 agent/server.py）
./.venv/Scripts/python.exe -m uvicorn backend.server:app --factory --host 127.0.0.1 --port 7777
```

访问 [资料查询助手](http://127.0.0.1:7777)、[接口文档](http://127.0.0.1:7777/docs)、[健康检查](http://127.0.0.1:7777/api/health)。使用 HTTP 访问前端；Vue CDN 首次加载需要联网。普通用户可直接注册，管理员使用上面的初始化命令创建。原 mock token 不再有效，请重新登录。

## 接口与数据规则

除注册、登录和健康检查外，API 请求需要 `Authorization: Bearer <token>`。管理员角色以数据库为准，不信任前端传入角色。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/users` | 注册普通用户 `{username,password}` |
| POST | `/api/login` | 返回 `{token,role,username}` |
| GET / POST | `/api/sessions` | 当前用户会话列表 / 新建会话 |
| GET | `/api/sessions/{id}/messages` | 本人会话消息；管理员可以查看所有会话 |
| POST | `/api/sessions/{id}/messages` | `{content,fileIds}`，返回 SSE |
| POST | `/api/upload` | multipart `file`；文本解析、向量化完成后返回 `{fileId,fileName,size,url}` |
| GET | `/api/files/{fileId}` | 鉴权下载，前端通过 fetch 携带 token |
| GET | `/api/admin/sessions` | 管理员汇总列表 |
| DELETE | `/api/admin/sessions/{id}` | 管理员删除会话并级联删除消息 |

支持 PDF、DOCX、UTF-8 TXT/Markdown；单文件 20 MB、最多 2000 个 500 字片段。扫描 PDF 需先 OCR；空文件、损坏文件和无文字资料拒绝入库。普通问答按余弦距离取共享知识库前 5 块，所有已登录账号均可查询其他账号上传的资料正文；指定 `fileIds` 时只检索这些文件。会话、原始附件下载、消息附件归属和导入任务状态仍按账号权限校验，匿名用户不能查询。资料独立于会话，删除会话不会删除知识库文件。

全文查看：输入 `09_外观检测相机与追溯接入.pdf中全部内容`，或为消息添加附件后输入 `请输出全部内容`。后端按文件的 `chunk_index` 顺序返回所有已入库片段，不受普通问答的前 5 块限制，也不经过模型摘要。正文保持入库片段内容，可能包含切分时的重叠文字；不代表恢复原文件版式。同名资料存在多份时需通过附件指定；全文过长时明确提示按章节分段查询，不会静默返回部分内容。

根据原句查来源并查看全文：例如 `查询「空压站仅有总管指针表，支路异常时无法区分设备耗气变化和压力波动。」出自哪篇文档，并输出该文档全文`。系统在共享知识库及所选文件范围内匹配引文（忽略排版空白），唯一命中后按文件 ID 读取全部片段并标明文件名；多份资料命中时提示选择，未找到时明确说明，不用相似片段冒充原句出处。

密码 6–64 字符，bcrypt 另限制 UTF-8 长度不超过 72 字节。用户名 3–32 位字母、数字或下划线，统一小写。JWT 默认有效 8 小时。

SSE 使用 POST fetch，不使用只能 GET 的 EventSource：

```text
event: delta
data: {"content":"回答片段"}

event: done
data: {"msgId":"m_...","role":"ai","content":"完整回答","files":[],"time":"..."}

```

失败返回 `event: error`，数据含 `message` 和 `status`，不会发送 `done`。只有整轮成功才原子保存用户和 AI 消息；流中失败或检测到断开时不保存半轮消息。若提交成功后网络断开，前端会提示刷新确认，避免误以为未保存。并发生成使用 PostgreSQL advisory lock，保存时额外检查会话版本。

初始化使用 `create_all` 建立初始表及 HNSW 余弦索引，需要 pgvector >= 0.5。现有表后续结构变更需明确数据库迁移；重复初始化不是迁移工具。生产部署前更换文档中的开发数据库密码，配置 HTTPS，并按访问量配置反向代理限流；代理需关闭 SSE 缓冲。数据库应与 `backend/data/uploads` 一起备份。

## 导入资料

聊天页面“导入资料”使用独立知识库流程；“添加附件”维持原来 20 MB 的消息附件行为。导入支持 PDF、DOCX、XLSX、XLS、PPTX、UTF-8 TXT/MD，最大 50 MB。上传后立即返回任务 ID，页面每 2 秒查询状态；成功提示片段数，失败提示原因。切换页面停止轮询，服务器仍继续处理已接收任务。

```powershell
./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
./.venv/Scripts/python.exe -m backend.migrate_ingest
```

在 `backend/.env` 配置 `EMBEDDING_API_KEY`（优先）或 `OPENAI_API_KEY`（兼容回退），模型默认 `text-embedding-3-small`，向量固定 1536 维。导入、附件入库和聊天检索共享 embedding 配置。每批 20 个片段；429 最多重试 3 次，间隔 1、2、4 秒，不叠加 SDK 自动重试。

若提示“向量服务密钥无效（401）”，需更换 `EMBEDDING_API_KEY`；使用 `OPENAI_API_KEY` 时必须将前者清空，避免仍优先使用无效值。修改 `.env` 后重启后端再导入。

转换器在受控子进程运行：PDF 优先 PyMuPDF4LLM，DOCX 保留段落/表格，Excel 每个工作表生成标题和表格，PPTX 按页提取文字/表格和图片占位。扫描 PDF 不自动 OCR；空文件、损坏格式和无法提取正文的文件会失败。单份转换文本最多 200 万字符、默认最多 2000 片段；Office 解压总量最多 100 MB，超过时请拆分。

切分按 Markdown 标题路径、段落和句子组织，目标 200–600 字，最多 800 字；章节末尾可较短。同节相邻片段重叠 1–2 个短句，不跨标题混入其他章节；超长无标点内容按上限拆分。metadata 含 source_file、chunk_index、heading_path、char_count。围栏代码不会误识别为标题，长表格/代码尽量按行拆分。

临时文件仅存于 `ziliao/md/<UUID>/`，转换完成或任务失败即清理；知识库保留文本、向量及来源元信息，不提供导入原件下载。启动时将上次中断的 processing 任务标记 failed；上传阶段崩溃遗留目录只有在 UUID 和本功能所有权标记均匹配时才会回收，不删除其他资料。

当前任务管理按单进程设计，启动时不要传 `--workers`。默认同时处理 2 份资料；配置 `INGEST_CONCURRENCY`、`CONVERTER_TIMEOUT_SECONDS`、`INGEST_TIMEOUT_SECONDS` 可调整。转换和 embedding 期间不占数据库事务；全部片段一次事务入库，失败不留下部分记录。

接口（均需 Bearer token，仅任务创建者可查询）：

| 方法 | 路径 | 返回 |
| --- | --- | --- |
| POST | `/api/ingest`，FormData 字段 `file` | 202 `{fileId,fileName,chunkCount:0,status:"processing"}` |
| GET | `/api/ingest/status/{fileId}` | `{fileId,status,chunkCount,error}`，状态 processing/completed/failed |

PowerShell 使用 `curl.exe`，避免 `curl` 别名差异：

```powershell
$env:INGEST_TOKEN='<登录接口返回的 token>'
curl.exe -X POST http://127.0.0.1:7777/api/ingest -H "Authorization: Bearer $env:INGEST_TOKEN" -F "file=@D:/资料/说明.pdf"
curl.exe http://127.0.0.1:7777/api/ingest/status/<fileId> -H "Authorization: Bearer $env:INGEST_TOKEN"
# 单独测试各转换器（stdout 为 Markdown）
./.venv/Scripts/python.exe -m agent.tools.pdf_to_md "D:/资料/说明.pdf"
./.venv/Scripts/python.exe -m agent.tools.docx_to_md "D:/资料/说明.docx"
./.venv/Scripts/python.exe -m agent.tools.excel_to_md "D:/资料/说明.xlsx"
./.venv/Scripts/python.exe -m agent.tools.pptx_to_md "D:/资料/说明.pptx"
./.venv/Scripts/python.exe -m agent.tools.txt_to_md "D:/资料/说明.md"
```

完整源代码已保存到项目。导入 API、模型和处理服务位于 `backend/`，转换工具位于 `agent/tools/`，测试位于 `backend/tests/`。

## 后端验证

```powershell
./.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
./.venv/Scripts/python.exe -m pytest -q
node --test backend/tests/test_sse.cjs
node --test backend/tests/test_chat_ui.cjs
node --test backend/tests/test_ingest_ui.cjs
# 对 .env 中的 PostgreSQL 运行集成测试（也可指定专用测试库 URL）
$env:TEST_DATABASE_URL='configured'
./.venv/Scripts/python.exe -m pytest backend/tests/test_postgres.py -q
./.venv/Scripts/python.exe -m pytest backend/tests/test_ingest_postgres.py -q
./.venv/Scripts/python.exe -m backend.check_db
# 真实启动、HTTP 和重启持久化验收（仅创建并清理随机测试账号）
$env:RUN_LIVE_SMOKE='1'
./.venv/Scripts/python.exe -m pytest backend/tests/test_live_server.py -q
```

快速 API 测试使用临时 SQLite，仅验证业务路由及事务，不替代真实向量测试。PostgreSQL 测试在随机测试 schema 中验证共享向量排序、文件范围、级联删除、跨连接锁，并只清理自己创建的 schema。会话和原件权限通过 API 回归测试验证。需要测试账号有建 schema 权限；未设置 `TEST_DATABASE_URL` 时明确跳过。

Agno 流式测试使用真实框架和受控 HTTP 上游，不消耗模型额度。真实付费模型调用还需配置有效密钥后手动上传、提问验证。`backend/requirements-lock.txt` 是本次 Python 3.12 环境的运行与测试依赖快照，可用于复现。

## 原有 PDF 和 Word 转 Markdown 工具

转换脚本位于 `agent/tools/`，依赖统一在 `backend/requirements.txt`，测试在 `backend/tests/`；示例转换结果保留于 `ziliao/md/`。详见 [转换工具说明](agent/tools/README.md)。

```powershell
python -m pip install -r backend/requirements.txt
python agent/tools/convert_to_md.py ziliao -r
```
