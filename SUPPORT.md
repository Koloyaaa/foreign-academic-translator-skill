# 使用支持

## 安装与调用

- **Codex：**按 [Codex 安装说明](codex/README.md) 将技能放到项目的 `.agents/skills/`。
- **Claude Code：**按 [Claude Code 安装说明](claude-code/README.md) 将技能放到 `.claude/skills/`。
- **Trae：**按 [Trae 安装说明](trae/README.md) 将技能放到 `.trae/skills/`。

安装后按对应 Harness 的步骤安装 `requirements.txt` 依赖，并重新载入项目技能。

## 常见情况

- **扫描版 PDF 提取不到文字：**先对 PDF 做 OCR，再运行翻译。
- **术语词库没有结果：**技能会结合上下文翻译；可选择 `ai_auto` 术语策略。
- **HTML 公式离线不显示：**页面通过 MathJax CDN 渲染公式，需要联网打开。
- **图片没有插入：**图片提取面向 PDF 内嵌位图，矢量图和扫描页不保证可提取。
- **找不到上次设置：**确认当前项目是否存在 `output/.translator_preferences.json`；偏好按项目保存。
- **个人标记没有恢复：**在同一浏览器和原 HTML 文件路径打开。标记与注释保存在浏览器本地存储中。

提交问题时请提供 Harness、技能版本、脱敏输入片段和错误信息。不要上传包含个人信息或未授权内容的学案；提示词注入问题请参阅 [安全报告说明](SECURITY.md)。
