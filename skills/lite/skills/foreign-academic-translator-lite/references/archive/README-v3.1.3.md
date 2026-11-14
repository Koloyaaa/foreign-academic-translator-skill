# 外文讲义翻译 Skill

将英语、法语等外文学案整理为准确、易读的中文学习材料，保留章节、术语、公式、表格和练习结构，并导出用户选择的格式。

本项目维护一份符合 Agent Skills 标准的技能包。支持该标准的 Harness 可共用 `SKILL.md` 和配套脚本，但各平台的安装目录、加载入口和工具权限不同。

## 支持范围

- 输入：PDF、DOCX、TXT。扫描版 PDF 需要先 OCR。
- 输出：HTML、DOCX、Markdown。
- PDF 配图：可提取 PDF 中的内嵌位图；无法保证提取矢量图。
- 术语：可检索随包词库，也可由模型结合上下文确定译名。

## 安装

| 原生支持 Agent Skills 的 Harness | 项目级目标位置 | 官方说明 |
| --- | --- | --- |
| Trae | `.trae/skills/foreign-academic-translator/` | [Trae](https://docs.trae.cn/ide_skills) |
| Codex | `.agents/skills/foreign-academic-translator/` | [Codex](https://developers.openai.com/codex/skills) |
| Claude Code | `.claude/skills/foreign-academic-translator/` | [Claude Code](https://code.claude.com/docs/en/skills) |
| GitHub Copilot | `.github/skills/foreign-academic-translator/` 或 `.agents/skills/foreign-academic-translator/` | [GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) |
| Cursor | `.cursor/skills/foreign-academic-translator/` | [Cursor](https://cursor.com/docs/skills) |
| Gemini CLI | `.gemini/skills/foreign-academic-translator/` 或 `.agents/skills/foreign-academic-translator/` | [Gemini CLI](https://geminicli.com/docs/cli/skills/) |
| Kiro | `.kiro/skills/foreign-academic-translator/` | [Kiro](https://kiro.dev/docs/skills/) |
| OpenCode | `.opencode/skills/foreign-academic-translator/` 或 `.agents/skills/foreign-academic-translator/` | [OpenCode](https://docs.opencode.ai/docs/skills/) |
| Cline | `.cline/skills/foreign-academic-translator/` | [Cline](https://docs.cline.bot/customization/skills) |
| Roo Code | `.roo/skills/foreign-academic-translator/` 或 `.agents/skills/foreign-academic-translator/` | [Roo Code](https://roocodeinc.github.io/Roo-Code/features/skills/) |

将整个 `foreign-academic-translator` 文件夹复制到对应位置即可；路径相对于目标项目的根目录。安装后应能找到 `<目标位置>/SKILL.md`。通用 Harness 从标准 `SKILL.md` 读取技能；项目附带的 `skill.yaml` 是可选参数扩展，不属于 Agent Skills 标准，平台是否读取取决于其自身支持。

也可以装到用户目录供所有项目使用，例如 Trae 的 `%USERPROFILE%\.trae-cn\skills\`。

Trae 技能面板还支持上传 ZIP：把本文件夹压缩，确保 `SKILL.md` 位于 ZIP 根目录，脚本、词库和样式一并包含在内，再在「设置」→「规则与技能」→「技能」中创建或上传。

装好后在技能目录安装依赖：

```powershell
python -m pip install -r requirements.txt
```

脚本要求 Python 3.10 或更高版本。

## 开始使用

选中本技能并附上学案。本轮明确指定的设置优先；未指定时，技能从当前讲义正文推断学科和主要源语言，不沿用上一份讲义的这两项。其他无法从讲义判断的缺少项仍逐项询问，每条消息只问一个问题。

| 选项 | 可选值 |
| --- | --- |
| 学科 | `Engineering`、`Economics`、`Science`、`Agriculture`、`Social_Sciences`、`Literature_Arts`、`Medicine` | 根据当前讲义推断，无法可靠判断时再询问 |
| 源语言 | 当前讲义正文的主要语言 | 自动识别；无法可靠判断时再询问 |
| 输出格式 | `html`、`docx`、`md`，至少选择一种 |
| 展示布局 | `translation_only`、`translation_first`、`source_first`、`concept_highlight` |
| 概念表 | `true`（生成）或 `false`（不生成） |
| 中文注释 | `无注释`、`轻度注释`、`高中生视角`、`重度注释` |
| 提取 PDF 配图 | `true` 或 `false` |
| 术语策略 | `system_glossary`（使用随包词库）或 `ai_auto`（模型识别术语） |
| 章末测验 | `无测验`、`基础`、`中档`、`高难`，可多选 |

选择任意测验难度后，还会单独询问测验语言：`双语`、`学案所属语言` 或 `中文`；选择“学案所属语言”时，会使用当前讲义识别出的主要源语言。

示例：

```text
请翻译这份法语热力学讲义。学科选 Science，输出 HTML 和 DOCX，使用 concept_highlight，生成概念表，采用高中生视角注释，提取 PDF 配图，并使用随包词库。
```

## 输出位置

成品保存在当前项目的 `output/<学案名>/` 中。选择 HTML 或 DOCX 而未选择 Markdown 时，构建完成后会清理中间 Markdown 文件；如果选择 Markdown，则保留该文件作为正式成品。HTML 包含目录、阅读进度、配色与明暗切换，以及保存在浏览器本地的个人高亮和注释。

## 文件说明

- `SKILL.md`：遵循 Agent Skills 标准的共用技能行为说明。
- `skill.yaml`：本项目附带的可选参数扩展；它不是 Agent Skills 标准字段，只有明确支持该扩展的调用器才会读取。
- `scripts/`：文本提取、术语检索、图片提取和 HTML / DOCX / Markdown 构建器。
- `glossaries/`：七个学科目录中的 CSV 术语表。
- `templates/`：HTML 样式。
- `docs/usage_guide.md`：参数说明、使用流程和故障排查。

## 兼容边界

截至 2026-11，Aider 官方通过 `/read` 或 `--read` 加载 `CONVENTIONS.md`；Continue 使用 `.continue/rules` 注入项目规则。它们没有本技能所依赖的原生 Agent Skills 按需发现流程，可以手动加载或改写说明，但不属于原生兼容 Harness。[Aider 文档](https://aider.chat/docs/usage/conventions.html) · [Continue 文档](https://docs.continue.dev/customize/rules)

即使 Harness 原生加载 `SKILL.md`，完整构建仍需要它能读取用户提供的文件、运行 Python 3.10+ 脚本，并在生成 HTML 时访问 CDN。若环境禁止 shell/Python 或网络访问，需手动完成受限步骤。

## 许可

本项目作者有权授权的代码、技能说明和文档采用 MIT License，详见仓库根目录的 [LICENSE](../../LICENSE)。词库、第三方依赖、截图和示例讲义不因此被重新授权，具体说明见本目录的 [NOTICE](NOTICE)。
