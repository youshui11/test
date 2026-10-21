# 后端验收记录

2026-10-21，Python 3.12，Windows，PostgreSQL 17，pgvector 0.8.7。

- 已在文档指定的 wendang 数据库启用 vector 并初始化 users、sessions、messages、uploads、knowledge_base。
- Python 全量测试：20 passed，包含原有转换测试、API、上传取消、Agno 事件/真实框架 HTTP 协议、真实 PostgreSQL 和服务重启验收。
- JavaScript：5 passed，覆盖跨字节中文 SSE、异常/中断、认证头、确认提交后刷新失败不重复发送。
- 真实 PostgreSQL：验证余弦排序、用户/附件过滤、级联删除、跨连接 advisory lock、单连接池复用、AnyIO 取消释放锁和归还连接。
- 实际启动临时 uvicorn，通过 HTTP 注册、登录、创建会话；重启服务后同一 token 可读取原会话；测试的随机账号及测试 schema 已清理。
- OpenAPI 生成、Python 编译、前端 JS 语法、pip check 均通过。
- 测试依赖产生一条 Starlette TestClient 使用 httpx 的弃用警告；不影响本次通过结果。

已通过独立代码审查并修复连接池争用、ANN 过滤漏检、已提交消息误恢复、上传取消文件清理和上传长事务问题。私有候选先物化后精确排序，优先确保过滤后检索结果可靠；未来大规模数据可改为分区索引检索。

后续已接入根目录 server.py 的 DeepSeek 声明：LLM_CONFIG_SOURCE=server，启动时静态读取，不执行示例脚本。已用该配置进行真实 HTTP/SSE 聊天测试，收到“连接成功”，并确认用户与 AI 两条消息保存；临时测试账号与会话已清理。

配置复用与 DeepSeek 兼容性变更后的 Python 全量测试为 24 passed，包含真实 PostgreSQL 和服务重启测试。embedding 密钥仍未配置，真实 embedding 文件入库尚未验证。

管理员没有预置公开密码。使用 `python -m backend.init_db --admin admin` 交互设置密码。普通账号通过前端注册。

后台启动使用 127.0.0.1:7777；日志在 backend/data/server.*.log，进程号在 backend/data/server.pid。修改环境配置后需重启该服务。
