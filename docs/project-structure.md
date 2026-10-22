# 当前项目目录

```text
test7/
├─ backend/                  后端入口、接口、数据库和业务逻辑
│  ├─ server.py              FastAPI 启动入口
│  ├─ agent_adapter.py       网站与 Agent 的调用适配
│  ├─ api/ models/ schemas/ services/
│  ├─ tests/                 Python 与前端协议回归测试
│  ├─ data/                  上传、日志、清理备份（不提交）
│  ├─ .env                   本机配置（不提交）
│  └─ requirements*.txt      统一运行及测试依赖
├─ agent/
│  ├─ server.py              PD 团队与 CX 子智能体定义
│  └─ tools/                 CX 检索、七格式转换及公共辅助
├─ docs/                     说明、历史方案与原始需求文档
├─ ziliao/                   原始资料和保留的 Markdown
├─ index.html                前端页面
├─ api.js app.js style.css   前端脚本与样式
└─ README.md                 使用说明
```

后端启动命令不变：在项目根目录执行 `./.venv/Scripts/python.exe -m uvicorn backend.server:app --factory --host 127.0.0.1 --port 7777`。

2026-10-22 清理：移除未引用的根目录演示脚本 `agno_agent.py`、失效的演示导入脚本 `ingest_data.py`，以及重复的 `backend/agent/server.py` 和空包入口；将后端适配移为 `backend/agent_adapter.py`，转换与检索工具统一移入 `agent/tools/`，转换测试移入 `backend/tests/`。去除旧 Agent 中不再使用的 Agno 知识库声明及内联检索实现，保留团队、成员、模型和指令。

重复生成的两个 Markdown 样例经 SHA256 核对后删除，原件继续保留在 `ziliao/md/`；工具依赖并入后端已有依赖，删除重复清单。原始 DOCX 需求文档保留在 `docs/requirements/`。测试、说明、原始资料、数据库和上传记录不按“未被运行时导入”判断为无用文件。

删除的演示代码和整理前的 Agent 文件已备份到 `backend/data/cleanup-backups/20261022-153709.zip`，其中可能含源配置，仅限本机保留，不提交版本库。
