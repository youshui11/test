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
| `LLM_CONFIG_SOURCE` | `server` 直接复用根目录 `server.py` 中 DeepSeek 的密钥、模型、地址和思考开关；`env` 则读取 `.env` 中的聊天配置 |
| `LLM_PROVIDER` | 使用 `env` 配置时为 `openai` 或 `deepseek` |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | 独立配置 embedding 服务，必须支持 1536 维向量及 `dimensions` 参数；默认 `text-embedding-3-small` |
| `CORS_ORIGINS` | JSON 数组，列出允许访问 API 的前端来源 |
| `MODEL_TIMEOUT_SECONDS` | 单轮检索和生成的总超时，默认 120 秒 |

本机已使用 `LLM_CONFIG_SOURCE=server`：聊天密钥和模型只需维护根目录 `server.py` 中的 `DeepSeek(...)` 声明，无需复制到 `.env`。读取支持 `api_key`、`id`、`base_url` 的字符串字面量和 `use_thinking` 布尔值；配置变更后需重启后端。后端只解析该声明，不导入或运行示例服务器。若改用其他服务，可设置 `LLM_CONFIG_SOURCE=env` 并填写 `LLM_*`。

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
# 启动正式后端（根目录 server.py / agno_agent.py 保留为独立示例）
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

使用 Python 3.10 或以上版本，将 `.pdf`、`.docx` 文件转换为 UTF-8 编码的 `.md` 文件。所有转换在本地完成，无需上传文件。

## 安装

在此文件夹打开 PowerShell，执行：

```powershell
python -m pip install -r requirements.txt
```

## 转换示例

转换提供的两个示例：

```powershell
python convert_to_md.py "ziliao/01_Word制度与培训/01_公司章程与治理规则.docx" "ziliao/02_PDF合作案例/01_离散制造工厂设备联网.pdf" -o examples_md
```

批量转换文件夹，包括所有子文件夹：

```powershell
python convert_to_md.py ziliao -r -o markdown_output
```

仅处理文件夹第一层时省略 `-r`。允许覆盖已有结果时添加 `--overwrite`。更多帮助：

```powershell
python convert_to_md.py --help
```

## 输出规则

- 默认输出到当前工作目录下的 `markdown_output`；使用 `-o` 指定其他位置。
- 文件名保留原扩展名，例如 `公司章程.docx.md`、`合作案例.pdf.md`，避免同名 Word 和 PDF 相互覆盖。
- 批量处理保留相对于输入文件夹的子目录结构；输入多个文件夹产生同名输出时报告冲突，不覆盖。
- 默认跳过已存在的结果；源文件不修改。单个文件失败后继续处理其他文件。
- 退出码：全部成功或跳过为 `0`，有失败为 `1`，命令参数错误为 `2`。

## 转换范围与限制

- Word：按原顺序转换段落和表格，将标题样式转换为 Markdown 标题，将常见列表转换为 Markdown 列表。自动编号以 Markdown 列表重建，不保证保留 Word 的起始编号和编号重启规则。
- PDF：提取文字和带边框、可被识别的表格，按垂直位置排列；以注释保留页码。未识别成表格的区域按文字输出。PDF 缺少语义结构，因此不自动猜测标题级别，多栏、复杂排版和无边框表格可能需要人工整理。
- 表格第一行用作 Markdown 表头；合并单元格按普通网格展开，无法保持 Word/PDF 的合并布局。
- 当前专注文字与表格，不导出图片，不保留字体、颜色、粗体、超链接目标、页眉页脚、批注或修订信息。
- 扫描 PDF 需要先做 OCR。全扫描文件会报错，不生成看似成功的空结果；混合 PDF 会提示无文字的页并保留页码占位。
- 不支持旧版二进制 `.doc`：先用 Word 另存为 `.docx` 再转换。不调用 Word，也不会执行文档里的指令或宏。

## 验证

```powershell
python -m unittest -v test_convert_to_md
```

测试覆盖中文标题和路径、表格顺序及转义、已有文件保护、损坏文件后的批处理，以及提供的 PDF 示例。
