# PDF 和 Word 转 Markdown 工具

使用 Python 3.10 或以上版本，将 `.pdf`、`.docx` 文件转换为 UTF-8 编码的 `.md` 文件。所有转换在本地完成，无需上传文件。

## 安装

在项目根目录 D:/work/test7 打开 PowerShell，执行：

```powershell
python -m pip install -r backend/requirements.txt
```

## 转换示例

转换提供的两个示例：

```powershell
python agent/tools/convert_to_md.py "ziliao/01_Word制度与培训/01_公司章程与治理规则.docx" "ziliao/02_PDF合作案例/01_离散制造工厂设备联网.pdf" -o ziliao/md
```

批量转换文件夹，包括所有子文件夹：

```powershell
python agent/tools/convert_to_md.py ziliao -r
```

仅处理文件夹第一层时省略 `-r`。允许覆盖已有结果时添加 `--overwrite`。更多帮助：

```powershell
python agent/tools/convert_to_md.py --help
```

## 输出规则

- 默认输出到项目的 `ziliao/md`，即 `D:/work/test7/ziliao/md`。目录不存在时自动创建；从其他工作目录调用也不会改变默认输出位置。使用 `-o` 指定其他位置。
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

## Python / Agno 调用

`convert_file()` 会转换并保存文件，返回 `output_path`、`skipped`、`warnings`。默认保护已有文件；传入 `overwrite=True` 可覆盖。原有 `convert_docx()` / `convert_pdf()` 仍仅提取内容，不自动保存。

```python
from agent.tools.convert_to_md import convert_file

result = convert_file(
    source="D:/work/test7/ziliao/01_Word制度与培训/01_公司章程与治理规则.docx"
)
print(result["output_path"])
```

在已有 Agno 的 `Agent(...)` 配置中添加 `tools=[convert_file]` 即可让模型按需调用保存工具。如果已有其他工具，将 `convert_file` 追加到同一列表。该工具返回保存路径；需要模型阅读内容时，由调用方读取对应 Markdown。

## QWJS 全文读取工具

`qwjs_knowledge.py` 提供 `make_full_document_tool()`，生成名为 `get_document_full_text` 的 Agno 工具，已在 `agent/server.py` 的 QWJS 子智能体注册。

- 参数 `document_name` 接受文件名或标题中的独特部分；`file_id` 接受 CX 返回的文档 ID。
- 查询共享 `public.knowledge_base`，优先匹配完整文件名，再按标题匹配；按 `chunk_index` 和 `id` 读取全部片段，不调用 embedding 或向量相似检索。
- 返回 JSON：`found` 含 `fileId`、`fileName`、`chunkCount`、`content`；`ambiguous` 返回候选标识；另有 `needs_identifier`、`not_found`、`too_large`，不会把截断结果当作全文。
- 正文超过 90000 字符时要求分段查询或下载原文件。入库时的标题处理、重复上下文和排版变化会保留，返回内容是全部入库片段，并非原文件的逐字副本。
- 网站聊天适配层会为每次请求重建工具，绑定现有 `knowledge_scope` 登录上下文及附件范围。无登录上下文时拒绝访问；单独运行 AgentOS 不会自动获得网站登录上下文。

用户可直接提问：`请输出公司章程与治理规则.docx的全文。`；如有重名，按工具提示提供文档 ID。

工具工厂的注册方式（已接入，无需重复添加）：

```python
from agent.tools.qwjs_knowledge import make_full_document_tool

get_document_full_text = make_full_document_tool()
# qwjs_agent = Agent(..., tools=[get_document_full_text])
```

全文工具与 Agent 适配回归测试：

```powershell
python -m pytest backend/tests/test_qwjs_knowledge.py backend/tests/test_agent_source.py backend/tests/test_cx_knowledge.py -q
```

## 验证

```powershell
python -m unittest discover -s backend/tests -p test_convert_to_md.py -v
```

测试覆盖中文标题和路径、表格顺序及转义、已有文件保护、损坏文件后的批处理，以及提供的 PDF 示例。
