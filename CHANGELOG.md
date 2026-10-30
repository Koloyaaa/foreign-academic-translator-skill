# 更新记录

## V3.0.2

- 把 Trae 包与 Agent Skills 包合并为 `skills/foreign-academic-translator`，三个 Harness 共用同一份技能包；`trae/` 与 `agent-skills/` 目录随之移除。
- 统一采用 Trae 版脚本：PDF 页码与坐标标记、整库词库合并、`--concept-table` 参数和 HTML 清理。共用包不再落后于 Trae 包。
- 修正 V3.0.1 里 SKILL.md 已写入、但共用包脚本尚未实现的规则。
- 安装说明并入技能包内 README，根目录 README、README.en.md 与 SUPPORT.md 同步更新。

## V3.0.1

- 将 Codex 与 Claude Code 两份逐字节相同的包合并为 `agent-skills/`，两个 Harness 共用一个技能包和一篇安装说明。
- `agent-skills/` 版的 `SKILL.md` 补齐 Trae 版已有的规则：PDF 页码与坐标标记、整库词库加载、按坐标落图、`--concept-table` 参数、HTML 清理与 MathJax 说明。

## V3

- 要求对缺失参数逐项提问；新增章末测验难度和语言选项。
- 加强对源文档、OCR、图片文字、隐藏文本、伪造角色及拆分注入的处理边界。
- 支持在项目中保存用户上次确认的参数，并在下次使用前询问是否沿用。
- HTML 新增配色与明暗设置、可本地保存的个人高亮和注释。
- 调整概念标记、公式、标题、注释层级与阅读进度样式。
- 增补提示词注入合成样例，README 记录五种场景的规则走查结果。
