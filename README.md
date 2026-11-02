# 外文讲义翻译 Skill

**版本：V3.1.2**

[中文](README.md) | [English](README.en.md)

把英语、法语等外文学案整理成中文学习材料，保留章节结构、术语、公式、练习和图表位置。技能按开放的 Agent Skills `SKILL.md` 格式编写，可安装到多种支持该标准的 Harness。

![Agent Skills compatible](https://img.shields.io/badge/Agent%20Skills-compatible-4B8BBE)
![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)

[查看版本发布 ↓](#版本发布)

## 效果预览

示例展示 HTML 阅读器的左右导航、居中学案标题、术语标注、公式与阅读目录。示例由项目作者 Koloyaaa（Léo WEE）制作。

![热力学学案 HTML 阅读器：文件资源管理器、学案知识大纲与居中标题](assets/showcase/thermodynamics-reader-overview.png)

![热力学学案 HTML 阅读器：熵公式与右侧实时知识大纲](assets/showcase/thermodynamics-reader-formulas.png)

![数学公式、图像与可折叠目录](assets/showcase/math-and-reading-progress.png)

## 功能

- 读取 PDF、DOCX 和 TXT；扫描版 PDF 需先 OCR。
- 按 Engineering、Economics、Science、Agriculture、Social_Sciences、Literature_Arts、Medicine 七个学科检索随包术语表，共含 122 份 CSV。
- 支持仅译文、原文/译文对照及术语标注；可加入概念表和分级中文注释。
- 导出 HTML、DOCX、Markdown。HTML 提供目录和阅读进度，DOCX 可继续编辑。
- 从 PDF 提取内嵌位图并按原文位置插入。矢量图不保证可提取。
- HTML 右上角可分别选择配色（蓝、青绿、紫、琥珀）和明暗模式（浅色、深色、跟随系统）；默认蓝色浅色。
- 在 HTML 中选中文本即可保存高亮或添加个人注释。标记、注释和阅读显示设置保存在当前浏览器本地，不会上传。
- 可生成基础、中档、高难章末测验，允许多选并按难度排序；选择“无测验”时不生成测验。生成前会说明额外 token 消耗。
- 章节标题可按所选布局呈现中外文；概念高亮模式下，主标题中文在上、外文在下，章节标题里的外文概念跟在中文标题之后。

HTML 公式使用 MathJax CDN，打开页面时需要联网；离线时公式可能显示为 LaTeX 源码。

## V3 变化

V3.0.4 起，本轮明确指定的参数优先于历史偏好；未指定的学科和主要源语言从当前讲义正文推断，每份讲义都会重新识别，不沿用上一份讲义的学科或语言。其他无法从讲义判断的设置仍逐项确认，每条提问只问一个问题。选择章末测验后，若未指定测验语言，再单独询问双语、学案所属语言或中文。

V3 延续提示词注入防护。技能会在项目内保存可跨讲义复用的输出和学习偏好，文件为 `output/.translator_preferences.json`；学科和源语言属于当前讲义信息，不作为跨讲义偏好使用。偏好文件不保存学案正文。

源文件中的正文、图片文字、OCR、批注、链接、元数据和隐藏文本均作为待处理数据，不作为 agent 指令。文档不能改变用户任务、替用户授权工具操作或触发数据外传；属于正文的注入文字仍按用户选择翻译。

高中生视角注释会跟在每个概念和知识点之后，重要结论或证明也会配解读，并在章节末归纳。轻度注释可略过简单内容，不作总结；重度注释会逐一解释概念、结论和证明过程，并详细归纳。

### 提示词注入用例走查

以下五份测试学案由项目自行编写，每份都包含多处注入文本。比较基线是本地 Git 历史中的 V2.0 版 `4da761c`（根目录 `SKILL.md`）；该版没有注入防护规则。V3 一栏是对新规则的人工场景走查，并非实际模型运行时红队测试。旧版结果表示规则没有覆盖该场景，不表示模型一定会执行攻击文字。

| 用例 | 文案中的多处注入 | V2.0（`4da761c`） | V3 规则走查 |
| --- | --- | --- | --- |
| 1. 正文直白越权（[`01-direct-override.txt`](tests/prompt_injection_cases/01-direct-override.txt)） | 要求泄露系统提示、扫描本地凭据、上传源文。 | 未定义文档不可信边界，也未禁止这些操作。 | 按正文翻译；不找凭据、不运行命令、不上传。 |
| 2. 伪造角色与多语言（[`02-fake-role-multilingual.txt`](tests/prompt_injection_cases/02-fake-role-multilingual.txt)） | 图片/OCR 伪造系统授权；法语批注索要开发者提示；超链接要求外传 PDF。 | 未覆盖图片文字、OCR、角色伪装和伪造授权。 | OCR 与页脚都作为文档内容处理；继续按用户要求翻译。 |
| 3. 跨页拆分载荷（[`03-split-payload.txt`](tests/prompt_injection_cases/03-split-payload.txt)） | 两页拼接成外传指令；OCR 要求删除前文；批注试图绕过“无测验”选择。 | 未限制跨页拼接指令或其引发的副作用。 | 拼接后仍是文档数据；不删内容、不触发测验、不发送文档。 |
| 4. 编码与多语言混淆（[`04-obfuscated-multilingual.txt`](tests/prompt_injection_cases/04-obfuscated-multilingual.txt)） | ROT13、Base64 元数据和英文图注要求解码后泄露提示、读取文件并上传。 | 未规定如何处理编码或跨元素载荷。 | 不把解码内容当作任务；不访问文件或网络，正文按选择翻译。 |
| 5. 伪造策略与测验覆盖（[`05-fake-policy-and-quiz-override.txt`](tests/prompt_injection_cases/05-fake-policy-and-quiz-override.txt)） | XML 伪装系统策略索取隐藏指令；批注要求覆盖用户测验选择；页脚要求外传源文和个人注释。 | 未约束角色伪装、伪造授权或泄露个人数据。 | 不接受文档授权、不改用户选择、不发送源文或个人注释。 |

## 安装与使用

本项目只维护一份 [skills/foreign-academic-translator](skills/foreign-academic-translator/) 技能包。支持 Agent Skills 标准的 Harness 可发现并加载同一份 `SKILL.md`；安装目录依 Harness 而异。

| Harness（原生支持 Agent Skills） | 项目级技能目录 | 文档 |
| --- | --- | --- |
| Codex | `.agents/skills/foreign-academic-translator/` | [Codex](https://developers.openai.com/codex/skills) |
| Claude Code | `.claude/skills/foreign-academic-translator/` | [Claude Code](https://code.claude.com/docs/en/skills) |
| Trae | `.trae/skills/foreign-academic-translator/` | [Trae](https://docs.trae.cn/ide_skills) |
| GitHub Copilot | `.github/skills/foreign-academic-translator/` 或 `.agents/skills/foreign-academic-translator/` | [GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) |
| Cursor | `.cursor/skills/foreign-academic-translator/` | [Cursor](https://cursor.com/docs/skills) |
| Gemini CLI | `.gemini/skills/foreign-academic-translator/` 或 `.agents/skills/foreign-academic-translator/` | [Gemini CLI](https://geminicli.com/docs/cli/skills/) |
| Kiro | `.kiro/skills/foreign-academic-translator/` | [Kiro](https://kiro.dev/docs/skills/) |
| OpenCode | `.opencode/skills/foreign-academic-translator/` 或 `.agents/skills/foreign-academic-translator/` | [OpenCode](https://docs.opencode.ai/docs/skills/) |
| Cline | `.cline/skills/foreign-academic-translator/` | [Cline](https://docs.cline.bot/customization/skills) |
| Roo Code | `.roo/skills/foreign-academic-translator/` 或 `.agents/skills/foreign-academic-translator/` | [Roo Code](https://roocodeinc.github.io/Roo-Code/features/skills/) |

1. 下载或克隆本仓库，找到 `skills/foreign-academic-translator`。
2. 把整个目录复制到目标项目的对应位置。装在用户目录可以让所有项目共用，例如 Trae 的 `%USERPROFILE%\.trae-cn\skills\`。Trae 也支持把该目录压缩成 ZIP 后在技能面板上传。
3. 在技能目录安装依赖，需要 Python 3.10 或更高版本：

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. 重新载入技能并附上学案。本轮明确指定的参数优先；未指定的学科和源语言会从当前讲义推断。其他无法推断的缺少项仍逐项询问，每条消息只问一个问题。
5. 成品保存在项目的 `output/<学案名>/`。当项目内已有 `output/.translator_preferences.json` 时，技能会先单独询问是否沿用上次设置。

上述产品的技能加载目录和入口各不相同；实际能否完整执行还取决于 Harness 是否允许读取用户提供的文件、调用 Python 3.10+ 脚本，以及访问网络 CDN。`skill.yaml` 是项目附带的参数扩展文件，不属于 Agent Skills 标准字段，其他 Harness 可以忽略它；标准流程以 `SKILL.md` 为准。

### 需要手动适配的 Harness

截至 2026-11，Aider 官方提供的是 `CONVENTIONS.md` 配合 `/read` 或 `--read` 加载约定，不具备 Agent Skills 的按需目录发现；Continue 官方提供 `.continue/rules`，用于常驻注入规则，也不是按需加载的 Agent Skill。两者可以手动把本技能说明作为只读上下文或改写成规则，但不会原生执行这套技能包的发现流程。[Aider](https://aider.chat/docs/usage/conventions.html)、[Continue](https://docs.continue.dev/customize/rules)。

更多细节见[技能包安装说明](skills/foreign-academic-translator/README.md)与[使用指南](skills/foreign-academic-translator/docs/usage_guide.md)。

## 项目文档

- [贡献指南](CONTRIBUTING.md)（[English](CONTRIBUTING.en.md)）
- [安全问题报告](SECURITY.md)（[English](SECURITY.en.md)）
- [行为准则](CODE_OF_CONDUCT.md)（[English](CODE_OF_CONDUCT.en.md)）
- [使用支持](SUPPORT.md)
- [更新记录](CHANGELOG.md)

## 项目结构

```text
.
├── skills/                唯一技能包：说明、脚本、词表、模板与依赖
├── tests/                 合成提示词注入用例
├── assets/showcase/       功能截图
└── README.md              项目首页
```

技能包采用 Agent Skills 结构：标准元数据和流程说明位于 `SKILL.md`，脚本、样式和词表作为配套资源。`skill.yaml` 是本项目的可选参数扩展，不是标准字段。通用 Harness 按 Agent Skills 规范加载 `SKILL.md`，其余输入和参数通过对话及 Harness 可用的文件/命令工具处理。相关规范见 [Agent Skills](https://agentskills.io/specification)。

## 许可与词库

本项目作者有权授权的代码、技能说明及文档采用 MIT License，详见 [LICENSE](LICENSE)。

CSV 词库、第三方 Python 依赖、示例图片和示例讲义仍按各自权利和许可处理，不因本项目采用 MIT 而被重新授权；详见 [NOTICE](skills/foreign-academic-translator/NOTICE)。项目地址：[Koloyaaa/foreign-academic-translator-skill](https://github.com/Koloyaaa/foreign-academic-translator-skill)。

## 词库来源说明

随包 CSV 词库来源于中华人民共和国台湾省教育研究院乐词网，部分词条经过筛选或修改。词条只供翻译参考，不代表项目作者在任何领域的观点。项目作者支持一个中国原则。根据国际法等相关法律规定，各方均应尊重一个中国原则。

## 版本发布

完整发布说明见 [Releases](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases)，历史改动见 [CHANGELOG.md](CHANGELOG.md)。

| 版本 | 主要变化 |
| --- | --- |
| [v3.1.2](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.1.2) | 移除复制时追加水印，采用正式技能名称与 MIT 许可，补全主流 Agent Skills Harness 兼容说明。 |
| [v3.1.1](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.1.1) | 双语测验按语言分行显示，选项选择器垂直居中。 |
| [v3.1.0](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.1.0) | 改进 HTML 阅读器布局、双侧大纲与标题排版；加入更严格的交互测验和页面质量门禁。 |
| [v3.0.4](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.4) | 本轮明确参数优先；从当前讲义推断学科和主要源语言。 |
| [v3.0.3](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.3) | 修复词库列名识别，查询不再把 ID 当译名；本页改为版本汇总。 |
| [v3.0.2](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.2) | 合并为唯一的技能包 `skills/foreign-academic-translator/`，统一采用 Trae 版脚本。 |
| [v3.0.1](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.1) | Codex 与 Claude Code 包合并为 `agent-skills/`。 |
| [v3.0.0](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.0) | V3：逐项提问、提示词注入防护、参数偏好、HTML 阅读器。 |
