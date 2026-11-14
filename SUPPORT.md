# 使用支持

## 安装与调用

- **原生支持 Agent Skills 的 Harness：**安装档位的方法见[项目安装说明](README.md#安装)；更多宿主的项目级目录见[技能套件安装表](skills/max/skills/translation-orchestrator/README.md#安装)。
- **需手动适配：**Aider 使用 `CONVENTIONS.md`，Continue 使用 `.continue/rules`；它们不原生发现本项目的 Agent Skill。详情见 [兼容边界](skills/max/skills/translation-orchestrator/README.md#兼容边界)。

先选择并安装一个档位：Lite 和 Plus 使用各自的旧版入口；Pro 和 Max 各自包含完整新版技能组。Pro、Max 与根目录套件含有同名 Skill，切换时请先备份并移出宿主扫描范围内的旧套件，再安装新档位。安装后按该档位说明安装 `requirements.txt` 依赖，并重新载入技能。运行完整构建还需 Python 3.10+、文件读取与 shell 权限；HTML 数学公式和图标需要网络。

## 常见情况

- **扫描版 PDF 提取不到文字：**Pro 和 Max 在具备图像输入能力时逐页核对页图；OCR 只能辅助，未经视觉确认的 OCR 不作为译文依据。没有图像输入能力时会列出未审核页。Lite 和 Plus 的旧版流程可能需要先对扫描件做 OCR。
- **术语词库没有结果：**技能会结合上下文翻译；可选择 `ai_auto` 术语策略。
- **HTML 公式离线不显示：**页面通过 MathJax CDN 渲染公式，需要联网打开。
- **图片没有插入：**先检查是否启用了配图。Lite 和 Plus 的旧版提取器只处理 PDF 图片；Pro 和 Max 只插入经过视觉核对并选中的图片。无法看图时，新版流程不会插入未经核准的图片。
- **找不到上次设置：**确认当前项目是否存在 `output/.translator_preferences.json`；偏好按项目保存。
- **个人标记没有恢复：**在同一浏览器和原 HTML 文件路径打开。标记与注释保存在浏览器本地存储中。

提交问题时请提供 Harness、技能版本、脱敏输入片段和错误信息。不要上传包含个人信息或未授权内容的学案；提示词注入问题请参阅 [安全报告说明](SECURITY.md)。
