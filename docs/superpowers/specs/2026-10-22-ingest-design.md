# 导入资料功能设计（已确认）

## 目标与范围

按《Codex导入资料功能提示词.docx》，将已有“导入资料”按钮接入独立的后台知识库导入链路：上传 → Markdown 转换 → 语义结构切分 → embedding → pgvector 入库 → 状态轮询。

现有附件上传、聊天、用户及管理员功能保持兼容。`D:\work\test7\agent\server.py` 不作任何内容修改，对接前后核对 SHA256。不覆盖用户已修改的前端布局和样式。

## 方案

采用现有 FastAPI 内的受管理异步任务，增加持久化任务状态，复用现有 uploads、knowledge_base 和认证。相比单独部署队列服务，无需新增 Redis 等基础设施；相比纯内存 BackgroundTasks，状态可在重启后查询，并能明确标记被中断的任务。

第一版使用单个后端进程，限制同时执行的转换/向量任务数量。正常关闭时停止或等待任务，并清理各自临时文件；重启发现此前未结束的任务时标记 failed，说明服务中断，允许用户重新导入。暂不引入跨机器任务调度。

## API 和页面

- `POST /api/ingest`：Bearer 认证，multipart 字段 `file`。接受 pdf、docx、xlsx、xls、pptx、txt、md，单文件最多 50 MB；超限在 multipart 解析前及保存时均校验。不支持格式返回“不支持的文件格式”。完成上传并登记任务后返回 HTTP 202：`{fileId,fileName,chunkCount:0,status:"processing"}`，不等待转换和 embedding。
- `GET /api/ingest/status/{fileId}`：返回 `{fileId,status,chunkCount,error}`，状态为 processing、completed 或 failed。仅创建者可查询，跨用户和不存在统一 404，避免泄露资料名称及状态。
- “添加附件”继续走原 `/api/upload`；“导入资料”使用独立文件选择器及 `/api/ingest`，每 2 秒轮询。完成提示“导入成功，共 N 个片段”，失败显示可读原因。切换页面时停止轮询，后台任务继续执行。

## 转换模块

新增 `backend/services/converter.py` 和 `backend/tools/` 下各格式转换器，每个转换脚本提供 `main`，可以独立运行。通过参数列表启动受控 Python 子进程，不拼接 shell 命令；转换失败统一为 ConvertError，设置超时并终止超时子进程。

PDF 优先 pymupdf4llm，尽量保留标题、表格与图片占位；DOCX 复用已有 python-docx 段落/表格解析；Excel 使用 openpyxl 处理 xlsx、xlrd 处理 xls，每个 sheet 生成标题和 Markdown 表格；PPTX 使用 python-pptx 提取每页文本和表格；TXT/MD 读取文字。空文本、损坏文档和需要 OCR 的扫描件给出明确错误。Office 压缩文件增加解压体积检查。

文档同时出现 backend/uploads 与 ziliao/md 两种临时目录，按最后的技术要求统一为 `ziliao/md/<随机任务目录>/`。该目录只保存任务的原文件与转换产物；结束、失败和取消时清理任务自己的目录，不删除用户已有资料。

## 语义结构切分

新增 `backend/services/chunker.py`，输出 `Chunk(text, metadata)`。

- 根据 Markdown 标题层级维护 heading_path；H1/H2 为硬边界，不跨不同大节拼接。
- 优先按段落、句子组合成约 200–600 字的块；章节末尾可小于目标长度。
- 大于 800 字的段落继续按句子拆分；无标点的超长内容才按字符上限截断，保证块大小有界。
- 同一章节相邻块携带前一块末尾 1–2 句重叠，重叠计入大小限制，不跨大节混入其他标题内容；保持 Markdown 表格与代码块结构，超长结构按可识别的行边界拆分。
- 每块包含标题路径及正文，metadata 包含 `source_file`、从 0 开始的 `chunk_index`、`heading_path`、最终文本 `char_count`。

## Embedding 与检索一致性

新增 `backend/services/embedder.py`，使用 OpenAI 官方异步 SDK，模型默认 text-embedding-3-small，每批 20 块，1536 维。限流后最多重试 3 次，采用指数退避；不重复叠加 SDK 自动重试。拒绝数量不匹配、维度错误、非有限或全零向量。

文档使用 OPENAI_API_KEY，而现项目已配置 EMBEDDING_API_KEY。兼容两者：保留现有 EMBEDDING_API_KEY 优先级，未配置时从 OPENAI_API_KEY 读取；导入和聊天检索共享同一 embedding 模型及服务配置，避免索引与查询向量不一致。不把 DeepSeek 聊天密钥用于 embedding。

## 存储与事务

新增任务表保存文件归属、状态、片段数及经过处理的错误信息；关联现有 uploads 记录。knowledge_base 保留现有 user_id 归属，新增 chunk_index 列；提供显式、可重复执行的数据库升级命令，仅追加所需结构，保留已有数据。

上传后先用短事务登记 processing；转换、切分和 embedding 不持有数据库事务或连接。全部向量生成并验证成功后，短事务批量写入所有片段并将任务标记 completed。任何阶段失败均不留下部分知识片段，持久化 failed 状态并清理临时文件。

导入来源只保存元信息及知识片段，不长期保留原件；因此不生成可公开下载的源文件 URL。现有普通附件下载行为不变。聊天检索沿用用户隔离的私有知识库查询，自动能检索成功导入的资料。

## 验证与交付

测试覆盖七种格式、损坏/空文件、超限、标题路径、重叠、长段落、表格/代码结构、20 条分批、限流重试、向量校验、状态查询隔离、后台失败无部分入库、取消/重启恢复与临时目录清理。使用受控 embedding HTTP 上游验证协议，再在隔离 PostgreSQL schema 验证任务状态及真实向量数据。

前端测试验证使用新接口、按 2 秒轮询、完成/失败提示和卸载取消轮询。检查 agent/server.py 的 SHA256 未变，回归现有登录、上传和聊天测试。

更新依赖和 README，标注新增/修改文件，提供各转换脚本 CLI、导入 curl 示例及数据库升级步骤。当前未安装 Excel、PPTX、pymupdf4llm 相关依赖，需要安装；现配置已有 embedding 密钥，但不会显示其内容。真实 embedding 调用仅用最小资料验证，测试产生的专用记录随后清理。
