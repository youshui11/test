# 导入资料验收记录

## 已实现

独立 POST /api/ingest 与状态查询、50 MB 请求限制、七种格式转换、Markdown 结构切分、20 条 embedding 分批、限流退避、1536 维校验、原子入库、持久化任务状态、重启恢复及临时文件清理。前端导入按钮单独选择资料，每 2 秒轮询并显示结果；添加附件保持原行为。

已在本机 wendang 数据库执行追加式升级，增加 ingest_jobs 表和 knowledge_base.chunk_index。升级可重复执行，旧记录保留并回填顺序。

## 自动验证

最终全量结果：46 项 Python 测试、9 项 JavaScript 测试通过，依赖检查通过。

真实生成并转换 PDF、DOCX、XLSX、XLS、PPTX、TXT、Markdown；验证长文本管道无堵塞、嵌套代码围栏、标题路径、唯一句子重叠与大小上限。模拟 OpenAI HTTP 上游验证 20/20/1 分批、429 三次重试、401 明确提示及非法向量拒绝。

API 测试验证立即返回 processing、完成后元信息正确、跨用户 404、失败无片段、关闭前尚未运行任务清理、重启处理 processing、仅清理带所有权标记的孤儿目录。隔离 PostgreSQL schema 中验证旧表两次升级和向量入库；触发器模拟第二片段写入失败，确认整批回滚且已有资料不受影响。

前端测试覆盖独立 multipart 接口、2 秒轮询、失败反馈、卸载取消轮询，以及原有 SSE 与聊天提交回归。独立代码审查发现的围栏解析与孤儿目录问题均已补回归并修复。

## 真实服务验收结果

2026-10-22 后端已重启启用新模块，健康检查 200。使用专用临时账号上传最小测试 Markdown，POST 返回 202、状态查询成功。

首次真实 embedding 请求返回 **401 invalid_api_key**，任务正确标记 failed、片段数 0，原件临时目录与测试账号记录均已清理。

用户更新密钥后，发现所填服务地址缺少 /v1；仅将 backend/.env 的 EMBEDDING_BASE_URL 补齐为 https://api.gpt.ge/v1，未显示或修改密钥，并重启后端。

最终使用专用临时账号完成真实 HTTP 导入：POST 返回 202，轮询最终为 completed、chunkCount 为 1。直接查询 PostgreSQL 确认已写入 1 个 1536 维向量片段，source_file、heading_path、chunk_index、char_count 元信息正确。任务原件临时目录已清理；验收结束后删除专用测试账号及其关联记录。后端健康检查 200，服务保持运行。

agent/server.py 内容保持不变，SHA256：67c9ad253c7dcf8726508b052942b827cf11d187ed39c48dfed5968be920b45d。
