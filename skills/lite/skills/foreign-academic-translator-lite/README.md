# Lite 安装说明

Lite 基于旧版 V3.1.3 单体翻译流程，可处理 PDF、DOCX、TXT 和纯文本，并检查所选成品的基础可读性。它不执行独立的全文语义审计。参数和使用方法见[使用指南](docs/usage_guide.md)。

## 安装

将本目录完整复制到宿主的 Skills 根目录，例如 Codex 项目的 `.agents/skills/foreign-academic-translator-lite/`。在本目录使用 Python 3.10 或更高版本安装依赖：

```powershell
python -m pip install -r requirements.txt
```

重新加载 Skills 后，调用 `foreign-academic-translator-lite` 并附上讲义。扫描版 PDF 需要先进行 OCR；旧版配图提取只支持 PDF 中的内嵌位图。

## 兼容边界

宿主需要允许读取讲义并运行本地 Python 脚本。Aider 和 Continue 不原生按本项目的 Agent Skills 目录方式发现本技能，需要手动加载说明或适配规则。
