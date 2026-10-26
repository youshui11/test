<!-- 文件作用：索引功能验收记录，区分历史验证结果与当前运行说明。
关联关系：连接后端、导入、共享知识库及全文记录；当前命令和目录见根目录 README。 -->
# 功能验收记录

各记录反映对应阶段的实现和验证结果，当前目录及运行命令以 [项目总说明](../../README.md) 和 [项目结构](../project-structure.md) 为准。

| 记录 | 内容 |
| --- | --- |
| [后端](backend-verification.md) | API、认证、数据库、流式聊天及服务运行验收 |
| [聊天路由](chat-routing-verification.md) | 停用预检索，验证真实历史和身份绑定工具调用 |
| [资料导入](ingest-verification.md) | 转换、切分、向量化、原子入库及中断恢复 |
| [共享知识库](shared-knowledge-verification.md) | 共享正文查询与会话、原件、任务权限边界 |
| [历史全文修复](full-document-verification.md) | 旧全文输出遗漏及引文定位的修复记录 |
