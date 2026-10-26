<!-- 文件作用：说明智能体资料检索及全文工具的职责、身份范围和验证方式。
关联关系：对应 cx_knowledge.py、qwjs_knowledge.py，由 server.py 定义引用并由 runtime.py 按请求绑定。 -->
# 资料查询工具

此目录保留供智能体调用的 CX/QWJS 工具。文档提取、转换和切分位于 [agent/documents](../documents/README.md)。

| 文件 | 作用 | 调用关系 |
| --- | --- | --- |
| `cx_knowledge.py` | 提供 `knowledge_scope`，构建 `search_cx_knowledge` 工具；查询共享知识库最相近的三条片段 | 聊天接口绑定登录身份、附件范围和向量服务，CX 查询时生成问题向量 |
| `qwjs_knowledge.py` | 构建 `get_document_full_text` 工具，按文件名、标题或文档 ID 定位并排序读取完整入库正文 | 复用 CX 模块的身份范围和公共知识表，读取全文不调用 embedding |
| `__init__.py` | 声明查询工具包 | 保持 `agent/server.py` 的既有导入路径有效 |

`agent/server.py` 定义团队及成员工具，`agent/runtime.py` 按请求复制智能体并重建工具。网站聊天接口负责提供认证上下文；无登录上下文时工具拒绝查询。已登录账号共享资料正文，指定附件时仅查询对应范围。

用户可提问“请输出公司章程与治理规则.docx的全文”。同名或多份候选需要进一步指定文档 ID；过长时明确提示，不把截断结果当作全文。QWJS 返回正文或自然语言提示，CX 返回包含来源信息的 JSON 检索结果。

```powershell
python -m pytest tests/agent/test_cx_knowledge.py tests/agent/test_qwjs_knowledge.py tests/agent/test_agent_source.py -q
```

真实 PostgreSQL 向量检索测试需要显式配置 `TEST_DATABASE_URL`；普通全文与身份测试使用临时测试数据。此目录不负责原始附件上传或资料导入。
