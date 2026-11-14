# 外文讲义翻译 Skill

> 套件文档版本：V4.0.0；编排 Skill 的元数据版本：3.3.0。

将英语、法语等外文学案整理为准确、易读的中文学习材料，保留章节、术语、公式、表格和练习结构，并导出用户选择的格式。

本项目包含十一个同级、可独立发现的 Agent Skills。`translation-orchestrator` 是编排入口，同时集中保存共享脚本、词库、模板和大部分依赖；十个执行 Skill 按需完成短线/长线翻译、PDF/PPTX 读取、共享图示讲解、测验、解析、格式发布和质量审计。各平台的安装目录、加载入口和工具权限不同。

## 强制 Skill 使用声明

每次实际使用一个 Skill，都必须在面向用户的对话中先单独输出 `当前使用 Skill：<skill-name>`，再开始该 Skill 的工作。编排器在任务开始时声明自身，并在调用每个实际执行的子 Skill 前声明目标名称；未输出声明不得启动该阶段。直接调用子 Skill 时由该 Skill 自行声明。只声明本轮真正执行的 Skill，缓存命中而未执行的 Skill 不声明；此提示不写入交付文件。

子 Agent 为默认执行方式：宿主支持委派时，编排器把可独立完成的工作分给多个子 Agent，并按阶段依赖并行或顺序推进。它是唯一协调者，负责合并结果和质量审计。子 Agent 的模型/推理档位不得高于用户所选档位；用户未指定时继承当前会话设置。视觉核对只能交给确实能接收图像的子 Agent，否则由当前能看图的模型完成。宿主不支持委派或无法保证档位上限时，使用兼容流程并如实说明。

## 支持范围

- 输入：PDF、DOCX、PPTX、TXT。PDF/PPTX 页面逐页渲染；当前模型支持图像输入且宿主能把页图像素交给它时必须逐页视觉核对，OCR 仅作辅助。能力以当前会话的宿主/模型组合为准，不根据模型品牌/型号、文件路径、OCR 或文字描述推断。若当前模型明确不支持图像输入或宿主没有实际传图通道，Reader 记录 `SKIPPED_NO_VISION`，只继续处理可提取文本，并在成品列出未审核页。
- 输出：HTML、DOCX、Markdown。
- 配图：PDF/PPTX 的图片由 Reader 逐页核对后选择导出；PDF 图片从页渲染图裁切。译稿标注页码，信息密集页按需生成图示说明。`SKIPPED_NO_VISION` 时不导出图片或图示说明。
- 术语：可检索随包词库，也可由模型结合上下文确定译名。

## 安装

| 原生支持 Agent Skills 的 Harness | 项目级目标位置 | 官方说明 |
| --- | --- | --- |
| Trae | `.trae/skills/` | [Trae](https://docs.trae.cn/ide_skills) |
| Codex | `.agents/skills/` | [Codex](https://developers.openai.com/codex/skills) |
| Claude Code | `.claude/skills/` | [Claude Code](https://code.claude.com/docs/en/skills) |
| GitHub Copilot | `.github/skills/` 或 `.agents/skills/` | [GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) |
| Cursor | `.cursor/skills/` | [Cursor](https://cursor.com/docs/skills) |
| Gemini CLI | `.gemini/skills/` 或 `.agents/skills/` | [Gemini CLI](https://geminicli.com/docs/cli/skills/) |
| Kiro | `.kiro/skills/` | [Kiro](https://kiro.dev/docs/skills/) |
| OpenCode | `.opencode/skills/` 或 `.agents/skills/` | [OpenCode](https://docs.opencode.ai/docs/skills/) |
| Cline | `.cline/skills/` | [Cline](https://docs.cline.bot/customization/skills) |
| Roo Code | `.roo/skills/` 或 `.agents/skills/` | [Roo Code](https://roocodeinc.github.io/Roo-Code/features/skills/) |

将 `skills/` 下的十一个文件夹直接复制到对应的 Skills 根目录，确保它们保持同级，且安装后能分别找到各目录中的 `SKILL.md`。不能只安装编排入口：PDF/PPTX Reader 各自带解析脚本，其他 Skills 需要从同级的 translation-orchestrator 目录读取共享资源。通用 Harness 从标准 `SKILL.md` 读取技能；`skill.yaml` 是可选扩展。

也可以装到用户目录供所有项目使用，例如 Trae 的 `%USERPROFILE%\.trae-cn\skills\`。

若使用 ZIP 导入，请逐个导入十一个技能目录，并确认它们安装到同一 Skills 根目录。在 translation-orchestrator 目录打开终端后安装共享依赖：

```powershell
python -m pip install -r requirements.txt
```

PPTX 页面渲染还需要在系统中安装 LibreOffice；PDF 由 pypdfium2 直接渲染。Tesseract 仅用于辅助 OCR，不能替代视觉核对。

脚本要求 Python 3.10 或更高版本。

## 开始使用

从 translation-orchestrator 编排入口开始并附上学案。它先输出 `当前使用 Skill：translation-orchestrator`；每次进入实际执行的子 Skill 前，也必须先输出该 Skill 的名称。本轮明确指定的设置优先；未指定时，编排器从当前讲义正文推断学科和主要源语言。编排器对短小、结构清楚、没有视觉内容的 DOCX/TXT 选择快速翻译 Skill；PDF/PPTX、扫描件、图像/图表、复杂、过长或无法确认完整性的材料走完整分阶段流程。PDF/PPTX 只有在当前模型支持图像输入且宿主实际可把页图像素传给模型时才要求逐页视觉审核；当前模型明确不支持图像输入或宿主没有该通道时记录 `SKIPPED_NO_VISION`，继续处理可提取文本并披露未审核页。两条路线共享同一正文审计，且都经过所选格式的发布检查。通过门禁的 Markdown、无正文覆盖索引、同源识别上下文和阶段指纹缓存在项目输出目录的 `.translator-cache-pro/`，切换输出格式时可复用译稿而无需重提取原件。缓存不保存原始提取文本；双语 Markdown 可能包含原文片段。任务清单和状态固定为 `.translation-task-pro.json` 与 `.translation-state-pro.json`，每轮保留 `.pro-decisions-<workflow_run_id>.jsonl`。每次实际 Skill 完成后都要运行 `workflow_state.py redecide`，读取返回的获准下一步再继续；状态脚本会阻止未经决策授权的阶段启动。删除 Pro 缓存目录可以强制重新运行。

| 选项 | 可选值 |
| --- | --- |
| 学科 | `Engineering`、`Economics`、`Science`、`Agriculture`、`Social_Sciences`、`Literature_Arts`、`Medicine` | 根据当前讲义推断，无法可靠判断时再询问 |
| 源语言 | 当前讲义正文的主要语言 | 自动识别；无法可靠判断时再询问 |
| 输出格式 | `html`、`docx`、`md`，至少选择一种 |
| 展示布局 | `translation_only`、`translation_first`、`source_first`、`concept_highlight` |
| 概念表 | `true`（生成）或 `false`（不生成） |
| 中文注释 | `无注释`、`轻度注释`、`高中生视角`、`重度注释` |
| 提取源文件配图 | `true` 或 `false` |
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

- `SKILL.md`：编排入口，收集设置并按需路由子 Skill。
- `references/task-handoff.md`：编排器与子 Skill 共用的任务清单和产物交接契约。
- `skill.yaml`：编排入口的可选参数扩展；它不是 Agent Skills 标准字段，只有明确支持该扩展的调用器才会读取。
- `scripts/`：文本提取、术语检索、图片提取和 HTML / DOCX / Markdown 构建器。
- `glossaries/`：七个学科目录中的 CSV 术语表。
- `templates/`：HTML 样式。
- 同级其他十个 Skill 目录：各自的 SKILL.md 和专属工作规则；见[套件索引](../README.md)。
- `docs/usage_guide.md`：参数说明、使用流程和故障排查。

## 兼容边界

截至 2026-11，Aider 官方通过 `/read` 或 `--read` 加载 `CONVENTIONS.md`；Continue 使用 `.continue/rules` 注入项目规则。它们没有本技能所依赖的原生 Agent Skills 按需发现流程，可以手动加载或改写说明，但不属于原生兼容 Harness。[Aider 文档](https://aider.chat/docs/usage/conventions.html) · [Continue 文档](https://docs.continue.dev/customize/rules)

即使 Harness 原生加载 `SKILL.md`，完整构建仍需要它能读取用户提供的文件、运行 Python 3.10+ 脚本，并在生成 HTML 时访问 CDN。若环境禁止 shell/Python 或网络访问，需手动完成受限步骤。

## 许可

本项目作者有权授权的代码、技能说明和文档采用 MIT License，详见本目录的 [LICENSE](LICENSE)。词库、第三方依赖、截图和示例讲义不因此被重新授权，具体说明见本目录的 [NOTICE](NOTICE)。
