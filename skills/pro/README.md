# Pro 技能档

Pro 使用独立完整的 Skills 套件，入口为 [`translation-orchestrator`](skills/translation-orchestrator/SKILL.md)。套件索引和工作流见 [`skills/README.md`](skills/README.md)。

## 执行规则

- 正文必须经过独立全文语义审计。
- 只有用户选择测验时才生成测验，并对测验进行独立审计。
- 只发布用户选择的格式；每种格式通过对应检查后才交付。
- PDF/PPTX 在当前模型和宿主能传递页图像素时逐页视觉核对；仅在该组合明确没有图像输入能力时记录 `SKIPPED_NO_VISION`，并披露未审核页。
- 每个 Skill 完成后，编排器调用本档的 `workflow_state.py redecide`，据依赖、选择和门禁重新确定下一步。脚本把结果写入任务 state 和本轮决策日志，并阻止未授权的阶段启动。

## 档位隔离

每份任务使用 `.translation-task-pro.json`、`.translation-state-pro.json` 和 `.translator-cache-pro/`。决策日志为 `.pro-decisions-<workflow_run_id>.jsonl`，任务成功后保留。Pro 状态脚本会验证档位标识、运行时 Skill 路径和缓存路径；Max 或其他档位的通过记录不能被读取成 Pro 通过。

## 安装与验证

将 [`skills`](skills/) 下十一个 Skill 目录安装到同一个 Skills 根目录，并按 [`编排器使用指南`](skills/translation-orchestrator/README.md) 安装依赖与运行。Pro 本档规则和资源都位于本目录内。

在本档目录（即本文件所在目录）运行：

```powershell
python -m unittest discover -s tests -v
```
