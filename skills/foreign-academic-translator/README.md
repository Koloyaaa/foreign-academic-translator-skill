# 外文讲义翻译 Skill

将英语、法语等外文学案整理为准确、易读的中文学习材料，保留章节、术语、公式、表格和练习结构，并导出用户选择的格式。

三个 Harness 共用这一份技能包，差别只有安装目录和调用方式。

## 支持范围

- 输入：PDF、DOCX、TXT。扫描版 PDF 需要先 OCR。
- 输出：HTML、DOCX、Markdown。
- PDF 配图：可提取 PDF 中的内嵌位图；无法保证提取矢量图。
- 术语：可检索随包词库，也可由模型结合上下文确定译名。

## 安装

| Harness | 目标位置 | 调用方式 | 官方说明 |
| --- | --- | --- | --- |
| Trae | `.trae/skills/foreign-academic-translator/` | 在技能面板启用 | [Trae Skills](https://docs.trae.cn/ide/skills) |
| Claude Code | `.claude/skills/foreign-academic-translator/` | `/foreign-academic-translator` | [Claude Code Skills](https://code.claude.com/docs/en/skills) |
| Codex | `.agents/skills/foreign-academic-translator/` | `$foreign-academic-translator` | [Codex Skills](https://developers.openai.com/codex/skills) |

将整个 `foreign-academic-translator` 文件夹复制到上表对应的位置即可；路径相对于目标项目的根目录。安装后应能找到 `<目标位置>/SKILL.md`。

也可以装到用户目录供所有项目使用，例如 Trae 的 `%USERPROFILE%\.trae-cn\skills\`。

Trae 技能面板还支持上传 ZIP：把本文件夹压缩，确保 `SKILL.md` 位于 ZIP 根目录，脚本、词库和样式一并包含在内，再在「设置」→「规则与技能」→「技能」中创建或上传。

装好后在技能目录安装依赖：

```powershell
python -m pip install -r requirements.txt
```

脚本要求 Python 3.10 或更高版本。

## 开始使用

选中本技能、附上学案，并说明下表中的选项。已经说明的选项不会重复询问；缺少的选项会逐项提问，每条消息只问一个问题。

| 选项 | 可选值 |
| --- | --- |
| 学科 | `Engineering`、`Economics`、`Science`、`Agriculture`、`Social_Sciences`、`Literature_Arts`、`Medicine` |
| 输出格式 | `html`、`docx`、`md`，至少选择一种 |
| 展示布局 | `translation_only`、`translation_first`、`source_first`、`concept_highlight` |
| 概念表 | `true`（生成）或 `false`（不生成） |
| 中文注释 | `无注释`、`轻度注释`、`高中生视角`、`重度注释` |
| 提取 PDF 配图 | `true` 或 `false` |
| 术语策略 | `system_glossary`（使用随包词库）或 `ai_auto`（模型识别术语） |
| 章末测验 | `无测验`、`基础`、`中档`、`高难`，可多选 |

选择任意测验难度后，还会单独询问测验语言：`双语`、`学案所属语言` 或 `中文`。

示例：

```text
请翻译这份法语热力学讲义。学科选 Science，输出 HTML 和 DOCX，使用 concept_highlight，生成概念表，采用高中生视角注释，提取 PDF 配图，并使用随包词库。
```

## 输出位置

成品保存在当前项目的 `output/<学案名>/` 中。选择 HTML 或 DOCX 而未选择 Markdown 时，构建完成后会清理中间 Markdown 文件；如果选择 Markdown，则保留该文件作为正式成品。HTML 包含目录、阅读进度、配色与明暗切换，以及保存在浏览器本地的个人高亮和注释。

## 文件说明

- `SKILL.md`：技能行为说明，三个 Harness 共用。
- `skill.yaml`：Trae 的参数配置；其他 Harness 不读取该文件。
- `scripts/`：文本提取、术语检索、图片提取和 HTML / DOCX / Markdown 构建器。
- `glossaries/`：七个学科目录中的 CSV 术语表。
- `templates/`：HTML 样式。
- `docs/usage_guide.md`：参数说明、使用流程和故障排查。
- `_pylibs/`：随包的第三方库副本，供不便联网安装依赖的环境使用；正常使用按 `requirements.txt` 安装即可。

## 许可

本项目不同部分的许可范围不同。使用或分享前请查看仓库根目录的 [LICENSE](../../LICENSE)；词库和随包第三方依赖可能适用各自的许可。
