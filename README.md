# 资料查询助手：后端与文档转换工具

后端位于 `backend/`，使用 FastAPI、SQLAlchemy 异步 PostgreSQL、pgvector、Agno。根目录 Vue 前端已接入真实 HTTP API，可注册、登录、上传私有资料、流式聊天及管理员管理会话。

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

本机使用 `LLM_CONFIG_SOURCE=server`：后端聊天调用 `D:\work\test7\agent\server.py` 中的 `deepseek_agent`，保留该智能体定义的模型、指令和工具，不再从根目录 `server.py` 读取。每次请求复制智能体及模型，网站历史由 PostgreSQL 管理，避免共享 SQLite 会话串入其他用户的请求。修改 `agent/server.py` 后需重启后端。

启动配置校验会静态读取同文件中 `DeepSeek(...)` 的 `api_key`、`id`、`base_url` 字符串及 `use_thinking` 布尔值；实际运行则导入其中的智能体。若改用环境配置独立创建智能体，可设置 `LLM_CONFIG_SOURCE=env` 并填写 `LLM_*`。

embedding 仍独立配置。只有聊天模型的服务不能自动承担 embedding。缺失密钥会返回明确配置错误，不会生成模拟回答。正式使用上传/RAG 会将资料文字发送给配置的 embedding 服务，命中片段发送给配置的聊天服务。

数据库需预先存在。用 PostgreSQL 超级用户连接 **wendang**，启用扩展一次：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

本机 PostgreSQL 17 也可运行 `./backend/enable-vector.ps1`，在弹出的本地提示中输入超级用户密码。应用账号需要在目标 schema 中建表的权限，无需日常使用超级用户。

```powershell
# 建表；重复运行保留已有数据，不重置账号
./.venv/Scripts/python.exe -m backend.init_db
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

支持 PDF、DOCX、UTF-8 TXT/Markdown；单文件 20 MB、最多 2000 个 500 字片段。扫描 PDF 需先 OCR；空文件、损坏文件和无文字资料拒绝入库。按余弦距离取当前用户私有知识库前 5 块，指定 `fileIds` 时只检索这些文件。资料独立于会话，删除会话不会删除知识库文件。

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

## 后端验证

```powershell
./.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
./.venv/Scripts/python.exe -m pytest -q
node --test backend/tests/test_sse.cjs
node --test backend/tests/test_chat_ui.cjs
# 对 .env 中的 PostgreSQL 运行集成测试（也可指定专用测试库 URL）
$env:TEST_DATABASE_URL='configured'
./.venv/Scripts/python.exe -m pytest backend/tests/test_postgres.py -q
./.venv/Scripts/python.exe -m backend.check_db
# 真实启动、HTTP 和重启持久化验收（仅创建并清理随机测试账号）
$env:RUN_LIVE_SMOKE='1'
./.venv/Scripts/python.exe -m pytest backend/tests/test_live_server.py -q
```

快速 API 测试使用临时 SQLite，仅验证业务路由及事务，不替代真实向量测试。PostgreSQL 测试在随机 `test_backend_*` schema 中验证向量排序、用户隔离、级联删除、跨连接锁，并只清理自己创建的 schema。需要测试账号有建 schema 权限；未设置 `TEST_DATABASE_URL` 时明确跳过。

Agno 流式测试使用真实框架和受控 HTTP 上游，不消耗模型额度。真实付费模型调用还需配置有效密钥后手动上传、提问验证。`backend/requirements-lock.txt` 是本次 Python 3.12 环境的运行与测试依赖快照，可用于复现。

## 原有 PDF 和 Word 转 Markdown 工具

转换脚本、依赖清单、测试、使用说明与转换示例已集中到 `agent/tools/`。详见 [转换工具说明](agent/tools/README.md)。

```powershell
python -m pip install -r agent/tools/requirements.txt
python agent/tools/convert_to_md.py ziliao -r -o markdown_output
```
