# Foreign Academic Translator Skill - 用户使用手册

## 概述
本 Skill 专为中外合办教育机构设计，旨在将外文学案（英语及其他语种）精准翻译为中文。核心优势在于：
- **学科术语强制匹配**：基于您提供的 CSV 词库，确保专业词汇翻译准确。
- **灵活的呈现模式**：支持纯译文、双语对照（可自定义先后顺序）、术语括号标注。
- **多格式导出**：一键生成 HTML、Word (DOCX)、PowerPoint (PPTX)、PDF。

---

## 快速开始

### 1. 前置准备
- 确保您的 `glossaries/` 目录结构正确，例如：

```text
glossaries/
└── Engineering/
└── Science/
```

- CSV 文件必须包含 `source_term`（外文）和 `target_term`（中文）列（列名可包含空格或大小写差异，脚本会自动模糊匹配）。

### 2. 触发 Skill
在 Trae 对话框中，您可以通过以下方式触发：
- **关键词**：输入“翻译学案”、“翻译外文”或“中外合办翻译”。
- **上传文件**：直接上传 `.pdf`、`.docx` 或 `.txt` 格式的学案文件。

### 3. 参数配置
上传文件后，系统会自动提取文本。您可以通过对话框或 `skill.yaml` 配置以下参数：

| 参数名 | 说明 | 可选值 | 默认值 |
| :--- | :--- | :--- | :--- |
| `discipline` | 学科分类（用于加载对应词库） | Engineering, Economics, Science, Agriculture, Social_Sciences, Literature_Arts, Medicine | Engineering |
| `mode` | 翻译展示模式 | `translation_only` (仅译文)<br>`bilingual` (双语对照)<br>`concept_highlight` (术语括号标注) | `bilingual` |
| `layout_preference` | 双语对照时的段落顺序（仅 mode=bilingual 时生效） | `translation_first` (译文在上/左)<br>`source_first` (原文在上/左) | `translation_first` |
| `show_concept_table` | 是否生成文末概念汇总表 | `true` / `false` | `true` |
| `output_formats` | 输出文档格式（可多选） | `html`, `docx`, `md` | `["html", "docx"]` |

### 4. 获取输出
Skill 执行完成后，会在 `output/docs/` 目录下生成对应的文档文件，并在对话中提供下载链接。

---

## 模式详解

### 模式 A：仅译文 (translation_only)
适用于快速阅读，仅输出流畅的中文翻译，不保留原文。

### 模式 B：双语对照 (bilingual)
适合学习与校对。根据 `layout_preference` 设置：
- **translation_first（默认）**：每段先显示中文译文，再显示外文原文。
- **source_first**：每段先显示外文原文，再显示中文译文。

### 模式 C：术语高亮标注 (concept_highlight)
适用于重点掌握专业词汇。译文中的核心术语会以“中文译名（外文原词）”的格式显示。

---

## 概念表说明
当 `show_concept_table` 开启时，系统会自动提取学案中出现的高频核心术语（基于加载的 CSV 词库），并在文档末尾生成一个三列表格：
| 外文术语 | 中文译名 | 上下文简要解释 |
| :--- | :--- | :--- |

该表格有助于学生快速复习本课重点词汇。

---

## 故障排除

### 1. 提示“学科目录不存在”
- 检查 `glossaries/` 下是否包含与 `discipline` 参数完全一致的子文件夹名称（如 `Engineering`）。

### 2. 提示“术语表加载成功但映射为空”
- 检查对应学科下的 CSV 文件是否包含数据，且列名是否包含 `source` / `外文` 和 `target` / `中文` 关键词。

### 3. 生成 DOCX 失败
- 确保已安装 `python-docx` 库 (`pip install python-docx`)。

---

## 自定义样式
- 修改 `templates/html_style.css` 可自定义 HTML 输出的视觉风格（颜色、字体、布局）。
- 若要修改 Word 默认样式，可运行 `templates/init_templates.py` 生成占位模板，并将其替换为自定义设计的模板文件（注意保持占位符名称一致）。