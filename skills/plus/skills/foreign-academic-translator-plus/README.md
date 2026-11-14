# Plus 安装说明

Plus 基于旧版 V3.1.3 单体翻译流程，并在交付前增加独立审计。参数和使用方法见[使用指南](docs/usage_guide.md)。

## 安装

将 Plus 套件中的 `foreign-academic-translator-plus` 和 `foreign-academic-quality-auditor-plus` 两个目录完整复制到同一个 Skills 根目录，例如 Codex 项目的 `.agents/skills/`。在翻译 Skill 目录使用 Python 3.10 或更高版本安装依赖：

```powershell
python -m pip install -r requirements.txt
```

重新加载 Skills 后，调用 `foreign-academic-translator-plus` 并附上讲义。审计由没有参与翻译起草的审阅者使用 `foreign-academic-quality-auditor-plus` 执行。宿主无法提供独立审阅上下文时，Plus 会报告阻塞或失败，不会声称审计通过。

## 兼容边界

宿主需要允许读取讲义、运行本地 Python 脚本和进行独立审阅。Aider 和 Continue 不原生按本项目的 Agent Skills 目录方式发现本技能，需要手动加载说明或适配规则。扫描版 PDF 需要先进行 OCR；旧版配图提取只支持 PDF 中的内嵌位图。
