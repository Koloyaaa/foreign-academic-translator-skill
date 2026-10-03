# Trae 版

本目录提供原有 Trae 技能的独立安装包。原技能文件保留在 `trae/.trae/skills/zwhb/`；安装时只需将 `zwhb` 文件夹复制到目标项目的 `.trae/skills/` 下。

## 安装

### 手动复制

在目标项目根目录运行 PowerShell 命令。将 `<本仓库路径>` 替换为本仓库所在的实际路径：

```powershell
New-Item -ItemType Directory -Force .trae/skills | Out-Null
Copy-Item -Recurse -LiteralPath "<本仓库路径>/trae/.trae/skills/zwhb" -Destination .trae/skills
```

确认目标项目内存在 `.trae/skills/zwhb/SKILL.md`，然后在 Trae 的「规则与技能」面板中启用该技能。

### 从技能面板上传

将 `trae/.trae/skills/zwhb/` 内的文件压缩成 ZIP，并确保 `SKILL.md` 位于 ZIP 根目录。然后在 Trae 的「规则与技能」→「技能」中选择上传。

## 使用

首次使用前，在技能目录安装 `requirements.txt` 中的 Python 依赖。可处理 PDF、DOCX 和 TXT，并生成 HTML、DOCX 或 Markdown。扫描版 PDF 需要先进行 OCR。

原技能包含七个学科目录的 CSV 术语表，以及 PDF 图片提取、术语检索和文档构建脚本。详细参数和流程见[原技能说明](.trae/skills/zwhb/README.md)与[使用指南](.trae/skills/zwhb/docs/usage_guide.md)。

## 效果预览

原作者示例截图，展示术语标注、通俗注释、公式、插图与目录。

![法语热力学术语标注、概念解释与循环示意图](../assets/showcase/thermodynamics-cycle.png)

![数学公式、图像与可折叠目录](../assets/showcase/math-and-reading-progress.png)

## 署名与许可

原作者为 DornGames / Koloyaaa（Léo WEE），原项目地址：[foreign-academic-translator-skill](https://github.com/Koloyaaa/foreign-academic-translator-skill)。软件代码遵循 PolyForm Noncommercial 1.0.0，技能说明与文档遵循 CC BY-NC-SA 4.0。公开分享或改编项目材料时，请保留作者与来源、注明修改，并遵守相应许可。随包 `NOTICE` 文件记录了可复制的署名信息。

- [项目许可说明](../LICENSE)
- [返回项目首页](../README.md)
