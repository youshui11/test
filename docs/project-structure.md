# 当前项目目录

```text
test7/
├─ backend/                  后端入口、接口、数据库和网站业务逻辑
│  ├─ server.py              FastAPI 启动入口
│  ├─ manage_db.py           数据库 check / init / upgrade 统一命令
│  ├─ config.py              网站环境配置
│  ├─ schemas.py             注册、登录与聊天请求校验
│  ├─ services/auth.py       登录、JWT 和管理员身份校验
│  ├─ services/chat.py       会话/附件权限、生成锁和 SSE 消息格式
│  ├─ api/                   认证、聊天、附件、导入和管理接口
│  ├─ models/                user.py / chat.py / knowledge.py 数据模型
│  ├─ tests/                 Python 与前端协议回归测试
│  ├─ data/                  上传、日志、清理备份（不提交）
│  ├─ .env                   本机配置（不提交）
│  └─ requirements*.txt      统一运行及测试依赖
├─ agent/
│  ├─ server.py              PD 团队与 CX 子智能体定义
│  ├─ runtime.py             智能体创建、请求隔离与流式回答
│  ├─ model_config.py        静态解析智能体模型声明，不执行源文件
│  ├─ embedding.py           向量生成、分批重试与校验
│  ├─ dr.py                  dr 资料导入处理（DRAgent）
│  └─ tools/                 CX/QWJS 检索、七格式转换及公共辅助
│     ├─ attachments.py      普通附件文字提取与固定 500 字符切分
│     ├─ chunker.py          知识库导入的 Markdown 结构化切分
│     └─ converter.py        转换子进程调度、超时与取消清理
├─ docs/                     说明、历史方案与原始需求文档
├─ ziliao/                   原始资料和保留的 Markdown
├─ fronted/                  前端文件（通过网站根路径提供）
│  ├─ index.html             前端页面
│  └─ api.js app.js style.css 前端脚本与样式
└─ README.md                 使用说明
```

后端启动命令不变：在项目根目录执行 `./.venv/Scripts/python.exe -m uvicorn backend.server:app --factory --host 127.0.0.1 --port 7777`。

资料导入由 `agent/dr.py` 的 `DRAgent`（名称 `dr`）处理，后端运行实例为 `app.state.dr`。原 `backend/services/ingest.py` 已迁移移除；HTTP 导入接口和数据库表名不变。

2026-10-26 整理：将原 `backend/agent_adapter.py` 与 `backend/services/agent.py` 合并为 `agent/runtime.py`；向量服务移到 `agent/embedding.py`，附件提取、语义切分和转换调度移到 `agent/tools/`。后端与测试直接引用新位置，旧实现移除。认证和会话服务留在后端；`agent/server.py` 保持整理开始时的内容不变。

此次仅整理模块归属，不改变处理流程：普通附件继续固定长度切分，DR 导入继续结构化切分，转换保留子进程限制及回收，智能体继续每次请求独立复制。`agent/dr.py` 和知识库工具仍依赖后端模型及登录上下文，转换调度仍使用后端项目根路径配置；`agent/` 尚不是脱离网站后端的独立软件包。

后续后端整理：数据库诊断、初始化和导入升级合并到 `backend/manage_db.py`，分别使用 `python -m backend.manage_db check`、`python -m backend.manage_db init`、`python -m backend.manage_db upgrade`；创建管理员使用 `init --admin admin`，仍交互输入密码。旧 `check_db.py`、`init_db.py`、`migrate_ingest.py` 已移除，旧模块命令需改用上述子命令。命令不带子命令时只显示参数错误，不默认执行初始化。

会话和消息定义合并到 `models/chat.py`；上传、知识片段和导入任务定义集中在 `models/knowledge.py`；模型仍统一从 `backend.models` 导入，表名、字段、约束和索引不变。原单文件请求校验包改为 `backend/schemas.py`，仍使用 `from backend.schemas import ...`。静态模型配置读取从 `backend/server_config.py` 移到 `agent/model_config.py`，仍不执行 `agent/server.py`。本次整理本身不需要数据库迁移。

2026-10-22 清理：移除未引用的根目录演示脚本 `agno_agent.py`、失效的演示导入脚本 `ingest_data.py`，以及重复的 `backend/agent/server.py` 和空包入口；将后端适配移为 `backend/agent_adapter.py`，转换与检索工具统一移入 `agent/tools/`，转换测试移入 `backend/tests/`。去除旧 Agent 中不再使用的 Agno 知识库声明及内联检索实现，保留团队、成员、模型和指令。

重复生成的两个 Markdown 样例经 SHA256 核对后删除，原件继续保留在 `ziliao/md/`；工具依赖并入后端已有依赖，删除重复清单。原始 DOCX 需求文档保留在 `docs/requirements/`。测试、说明、原始资料、数据库和上传记录不按“未被运行时导入”判断为无用文件。

删除的演示代码和整理前的 Agent 文件已备份到 `backend/data/cleanup-backups/20261022-153709.zip`，其中可能含源配置，仅限本机保留，不提交版本库。
