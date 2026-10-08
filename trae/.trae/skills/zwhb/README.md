# 外文讲义翻译 Skill（Trae 版）

将英语、法语等外文学案整理为准确、易读的中文学习材料，保留章节、术语、公式、表格和练习结构，并导出用户选择的格式。

## 支持范围

- 输入：PDF、DOCX、TXT。扫描版 PDF 需要先 OCR。
- 输出：HTML、DOCX、Markdown。
- PDF 配图：可提取 PDF 中的内嵌位图；无法保证提取矢量图。
- 术语：可检索随包词库，也可由模型结合上下文确定译名。

## 安装到 Trae

> Trae 官方说明：https://docs.trae.cn/ide/skills

### 方式一：技能面板上传

1. 将本文件夹压缩为 ZIP，并确保 `SKILL.md` 位于 ZIP 根目录，其余脚本、词库和样式文件也包含在内。
2. 在 Trae 的「设置」→「规则与技能」→「技能」中选择创建或上传技能。
3. 选择该 ZIP，核对技能名称后保存。
4. 确认安装范围为全局或当前项目，并在技能面板中启用。

### 方式二：手动安装

将整个 `zwhb` 文件夹复制到目标项目的 `.trae/skills/` 下。安装后应能找到 `.trae/skills/zwhb/SKILL.md`。也可以安装到 Trae 用户目录 `%USERPROFILE%\.trae-cn\skills\`。安装后在 Trae 技能面板中启用。

首次使用前，在技能目录安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 开始使用

在 Trae 中选择本技能、附上学案，并说明下表中的选项。已经说明的选项不会重复询问；缺少的选项会合并为一次提问。

| 选项 | 可选值 |
| --- | --- |
| 学科 | `Engineering`、`Economics`、`Science`、`Agriculture`、`Social_Sciences`、`Literature_Arts`、`Medicine` |
| 输出格式 | `html`、`docx`、`md`，至少选择一种 |
| 展示布局 | `translation_only`、`translation_first`、`source_first`、`concept_highlight` |
| 概念表 | `true`（生成）或 `false`（不生成） |
| 中文注释 | `无注释`、`轻度注释`、`高中生视角`、`重度注释` |
| 提取 PDF 配图 | `true` 或 `false` |
| 术语策略 | `system_glossary`（使用随包词库）或 `ai_auto`（模型识别术语） |

示例：

```text
请翻译这份法语热力学讲义。学科选 Science，输出 HTML 和 DOCX，使用 concept_highlight，生成概念表，采用高中生视角注释，提取 PDF 配图，并使用随包词库。
```

## 输出位置

成品保存在当前项目的 `output/<学案名>/` 中。选择 HTML 或 DOCX 而未选择 Markdown 时，构建完成后会清理中间 Markdown 文件；如果选择 Markdown，则保留该文件作为正式成品。HTML 包含目录和阅读进度功能。

## 文件说明

- `SKILL.md`：Trae 调用的行为说明，与 Codex、Claude Code 共用相同的翻译流程。
- `skill.yaml`：Trae 参数配置。
- `scripts/`：文本提取、术语检索、图片提取和 HTML / DOCX / Markdown 构建器。
- `glossaries/`：七个学科目录中的 CSV 术语表。
- `templates/`：HTML 样式。
- `docs/usage_guide.md`：参数说明、使用流程和故障排查。

## 许可

本项目不同部分的许可范围不同。使用或分享前请查看仓库根目录的 [LICENSE](../../../../LICENSE)；词库和随包第三方依赖可能适用各自的许可。

