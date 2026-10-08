# Trae 使用指南

本技能将 PDF、DOCX 或 TXT 格式的外文学案整理为中文学习材料，并可导出 HTML、DOCX 或 Markdown。扫描版 PDF 需要先 OCR。PDF 配图功能面向内嵌位图，不能保证提取矢量图。

## 快速开始

1. 在 Trae 中安装并启用本技能。
2. 首次使用前安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. 在对话中选择本技能并附上学案。
4. 说明学科、输出格式、展示布局、概念表、中文注释等级、是否提取 PDF 配图，以及术语策略。
5. 在当前项目的 `output/<学案名>/` 中查看成品。

如果遗漏选项，技能会把缺少的选项合并后一次询问；已经说明的选项无需重复提供。

## 可选参数

| 参数 | 可选值 | 说明 |
| --- | --- | --- |
| `source_text` | 由 Trae 预处理注入 | 学案文本；也可在对话中附上可读取的源文件 |
| `discipline` | `Engineering`、`Economics`、`Science`、`Agriculture`、`Social_Sciences`、`Literature_Arts`、`Medicine` | 用于筛选相关术语表 |
| `output_formats` | `html`、`docx`、`md` | 可多选，至少选择一种 |
| `layout` | `translation_only`、`translation_first`、`source_first`、`concept_highlight` | 仅译文、译文在前、原文在前或术语标注原文 |
| `show_concept_table` | `true` / `false` | 是否在文末生成重要术语概念汇总表 |
| `annotate_level` | `无注释`、`轻度注释`、`高中生视角`、`重度注释` | 注释越多，译文越长 |
| `include_images` | `true` / `false` | 从 PDF 提取并插入内嵌位图 |
| `glossary_mode` | `system_glossary` / `ai_auto` | 使用随包词库，或由模型结合上下文识别术语 |

## 展示布局

- **`translation_only`**：只输出中文译文。
- **`translation_first`**：每段先显示译文，再显示对应原文。
- **`source_first`**：每段先显示原文，再显示对应译文。
- **`concept_highlight`**：只输出译文，在术语首次出现处标注原文。

## 术语与注释

选择 `system_glossary` 时，技能会根据学科和词表文件名检索相关 CSV，并优先采用查到的译名；没有匹配结果时结合上下文翻译。选择 `ai_auto` 时不查询随包词库。标注术语时保留原文里的原词，法语术语不会改写成英文。

开启概念表后，技能会按术语在译文中首次出现的顺序整理外文术语、中文译名和简短释义。中文注释分为无、轻度、高中生视角和重度四档；注释主要用于解释定义、公式思路和易错点。

## 输出与文件

成品保存在 `output/<学案名>/` 中，目录名根据学案标题或文件名生成。用户未选择 Markdown 时，中间 Markdown 文件会在构建后清理；选择 Markdown 时会作为正式成品保留。若输出引用了提取的图片，`images/` 文件夹需要和 HTML 或 Markdown 一起保留。

## 故障排查

### 源文件无法读取或内容为空

确认文件为 PDF、DOCX 或 TXT。扫描版 PDF 需要先 OCR；文本提取少于 10 个字符时，技能会停止并说明原因。

### 找不到术语

检查 `glossaries/` 中是否存在对应学科目录和相关 CSV 文件。也可以将术语策略改为 `ai_auto`，让模型按上下文翻译。

### DOCX 或 HTML 未生成

确认已在技能目录安装 `requirements.txt` 中的依赖，并检查最终回复列出的失败格式。技能会核对所选格式对应的文件是否存在且非空；失败时应如实说明。

### 配图没有提取

图片提取目前只支持 PDF 内嵌位图。扫描图像、矢量图和其他文档格式中的图片可能无法提取；扫描版 PDF 请先 OCR。

## 相关文件

- [技能行为说明](../SKILL.md)
- [Trae 参数配置](../skill.yaml)
- [项目许可说明](../../../../../LICENSE)

