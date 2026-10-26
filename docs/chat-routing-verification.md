# 停用聊天预检索与替代验证

默认 `CHAT_PRERETRIEVAL_ENABLED=false`：聊天接口不调用 `app.state.retrieve`，仅把真实历史、当前问题和空参考资料列表传给回答服务。CX、QWJS 仍在 `knowledge_scope` 中获得当前登录身份、数据库会话工厂、附件范围及独立 embedding 服务。上传和 DR 导入保持原流程。

`backend/server.py` 的 embedding 初始化直接引用 `backend.services.embedder.embed`，不再通过 rag 的转导入。旧检索函数保留，便于显式开启开关回滚；普通附件仍使用 rag 的提取/切分函数。

新增 `backend/tests/test_chat_routing.py` 验证：

- 将自动检索和 embedding 替换为报错函数，问候及聊天历史回顾仍正常完成；传入模型的消息严格等于真实历史和当前问题，没有附加参考资料 JSON。
- 在相同报错替身下，通过真实聊天接口调用 QWJS，按顺序完整返回数据库正文，证明身份和数据库上下文继续传递。
- 显式开启开关可以恢复预检索。

已有 CX PostgreSQL 检索、QWJS 全文/歧义/过长/身份及附件范围测试继续验证替代工具。`test_full_document.py` 显式启用旧流程，单独保留回滚行为覆盖。模型边界使用确定性替身，不发送用户资料给外部模型；工具查询、API、数据库及流式处理执行真实代码，未声称验证实际模型每次都会遵循委派指令。

`agent/serve.py`、`agent/server.py` 均受保护，本次不作修改。重启项目后配置生效；如需回滚，在 `backend/.env` 设置 `CHAT_PRERETRIEVAL_ENABLED=true` 后重启。
