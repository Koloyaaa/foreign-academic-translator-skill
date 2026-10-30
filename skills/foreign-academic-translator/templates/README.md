# Templates 目录说明

本目录存放输出文档的样式模板，用以控制最终生成的 HTML、Word 文件的视觉呈现。

| 文件 | 用途 | 是否必需 |
| :--- | :--- | :--- |
| `html_style.css` | HTML 输出样式（含双语布局、概念表、打印适配）。 | **必需**（若启用 html 格式） |
| `word_template.docx` | Word 文档的样式基准（页边距、标题字体、段落间距）。当前 `builder.py` 使用代码内联样式，此文件预留供后续高级自定义。 | 可选（目前为占位） |
| `init_templates.py` | 初始化脚本，用于生成 Word 二进制占位文件（若不存在）。 | 仅首次部署时使用 |

> **注意**：`builder.py` 当前并未强制加载 `word_template.docx`，而是使用库默认设置。如果您希望深度定制 Word 样式，需要修改 `builder.py` 中对应函数的加载逻辑（如使用 `Document(docx=template_path)`）。