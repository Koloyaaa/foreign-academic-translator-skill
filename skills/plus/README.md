# Plus 档：旧版单体翻译 + 独立审计

此目录是一个独立的 Plus 套件，包含两个入口：

- 主入口：`foreign-academic-translator-plus`，基于完整旧版 V3.1.3 单体翻译流程。
- 审计入口：`foreign-academic-quality-auditor-plus`，这是在独立审阅上下文中运行的质量审计 Skill。

## 安装与调用

将 `skills/` 下的两个 Skill 文件夹都复制到所用宿主的技能目录，例如 Codex 项目的 `.agents/skills/`。保留各自整个文件夹，以便脚本、词库、模板和审计说明都能通过相对路径找到。通过 `foreign-academic-translator-plus` 启动翻译；宿主需要能提供独立审阅上下文，并在其中运行 `foreign-academic-quality-auditor-plus` 质量审计 Skill。

如果宿主不能在独立上下文中运行质量审计 Skill，Plus 入口会把任务标记为 `BLOCKED` 或 `FAIL`，不会把作者自检包装为审计通过。该 Skill 必须直接读取完整源文、译文核心 Markdown 和每个用户选择的成品。图像未能实际查看时标记为 `PARTIAL_TEXT_ONLY`，不能称 Plus 整体审计通过。

脚本需要 Python 3.10+。按[安装说明](skills/foreign-academic-translator-plus/README.md)安装主入口 `requirements.txt` 中的依赖。检查脚本和其他资源均随各自入口独立复制。

## 旧版来源

完整资源分别从 Git 提交 `2f5d4f3`（`Release v3.1.3: complete translation in one turn`）中的 `skills/foreign-academic-translator/` 复制。两份主 Skill 的目录互不共享资源，并在各自的 `references/archive/` 保存旧版原始入口、README 和可选参数描述。参数描述文件自身标记 3.1.2；实际复制的主入口是 3.1.3。Plus 的独立审计 Skill 是此档新增入口。

## 审计范围

Plus 要求全文覆盖可读源文，核对标题、正文、表格、公式、练习、术语、关键数字与各成品内容。审计报告写入 `plus-audit-report.md`。若无法读取全部内容或未实际查看图像，报告会保留相应范围和限制，不会声称整体内容或视觉审核通过。
