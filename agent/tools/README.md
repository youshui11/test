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

## 验证

```powershell
python -m unittest discover -s backend/tests -p test_convert_to_md.py -v
```

测试覆盖中文标题和路径、表格顺序及转义、已有文件保护、损坏文件后的批处理，以及提供的 PDF 示例。
