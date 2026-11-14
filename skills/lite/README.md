# Lite 档：旧版单体翻译 + 轻量检查

此目录内含一个可单独安装的 Skill：`foreign-academic-translator-lite`。它来自旧版 V3.1.3 单体 Skill 的完整资源副本，另增加成品文件可读性检查；Lite 不声称完成独立语义审计。

## 安装与调用

把 `skills/foreign-academic-translator-lite/` 整个文件夹复制到所用 Harness 的技能目录，例如 Codex 项目的 `.agents/skills/foreign-academic-translator-lite/`。脚本、词库、模板、依赖和 Lite 专用检查器都在此文件夹内，不依赖其他档位。安装后选择或调用 `foreign-academic-translator-lite`。

脚本需要 Python 3.10+。按旧版说明在需要时安装 `requirements.txt` 中的依赖。构建完用户选择的文件后，Lite 运行 `scripts/artifact_check.py`；它仅检查文件存在、非空和基础可读性。

## 旧版来源

完整资源从 Git 提交 `2f5d4f3`（`Release v3.1.3: complete translation in one turn`）中的 `skills/foreign-academic-translator/` 复制。每个 Lite 包单独保存了旧版原始入口和 README：`references/archive/SKILL-v3.1.3.md`、`references/archive/README-v3.1.3.md`，以及原始可选参数描述 `references/archive/skill-v3.1.2.yaml`。原文件中的参数描述版本仍写着 3.1.2；实际复制的主入口是 3.1.3。本目录的脚本和词库是独立副本，不通过链接或运行时回退到 Pro/Max。

## 检查边界

Lite 检查成品能否读取，不会逐项将源文与译文做独立对照。格式、术语、公式或内容覆盖的语义正确性没有经过独立审计时，应明确说明。
