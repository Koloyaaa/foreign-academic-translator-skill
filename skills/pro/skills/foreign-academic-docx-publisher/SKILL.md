---
name: foreign-academic-docx-publisher
description: Build and inspect an editable DOCX from the suite's canonical translated Markdown; use only when DOCX is selected.
license: MIT
---

## 强制 Skill 使用声明

- 在本 Skill 开始实质工作前，先向用户单独输出一行：`当前使用 Skill：foreign-academic-docx-publisher`。如果编排器已在进入本阶段前输出了这一行，不重复。
- 硬性阶段门禁：编排器必须在调用目标 Skill 前，先单独向用户输出 `当前使用 Skill：<skill-name>`；没有编排器时，由目标 Skill 自行先输出。未出现目标 Skill 的声明行，不得启动该阶段。
- 只声明本轮真正执行的 Skill，不声明仅被列为候选或因缓存命中而跳过的 Skill。这是对话进度提示，不得写入讲义、译稿、测验或其他产物。

# DOCX 发布 Skill

读取 .translation-task-pro.json 和 translated_markdown。只负责 DOCX 构建和成品检查；不得重新翻译、删减或重排正文，也不读取或保存偏好。共享脚本与 Python 依赖位于清单的 shared_runtime。

## 构建

只有编排器确认 DOCX 阶段签名和产物哈希均命中时，才可直接检查已有文件。缓存未命中时，从 shared_runtime/scripts/builder.py 的绝对路径单独构建 DOCX，每次只传 `--formats docx`。必须确认本次构建退出码为 0、返回的路径正是 `output_dir/translated_doc.docx` 且文件非空，才进入成品检查。同名旧文件即使存在，也不能证明本次构建成功。使用同一份统一 Markdown，不为 DOCX 单独生成或改写内容，也不要假定当前终端目录就是技能目录。

## 检查

确认 DOCX 文件存在、非空并能由 DOCX 解析器打开。正文文本必须通过乱码门禁：不得出现 Unicode 替换字符、常见 UTF-8 错误解码序列、可见的 HTML 标签/实体源码或异常控制字符。代码块中的标签示例可保留；发现异常时报告附近文本并退回修复统一 Markdown/编码，不能靠静默删字符放行。核对标题层级、段落、有序及无序列表、表格、行内格式、练习、引用图片和公式是否保留；标题使用独立层级样式，表格首行按表头样式处理，PDF/PPTX 正式图片资源按相对输出目录的路径嵌入。PDF/PPTX 来源页码须以居中的浅灰细线分隔样式显示，页码文字仍须完整可读。公式优先为 Word 原生公式，后端缺失时可能使用 PNG。页面上下页边距为 2cm、左右为 2.5cm；正文等线 11pt、约 1.3 倍行距并首行缩进 2 字符；页脚居中含页码和正式项目署名。

若后端缺失导致公式仍为 LaTeX，或只能做结构解析而未能目视检查分页，应如实记录。内容或共同结构有问题时退回编排 Skill；修改统一 Markdown 后重建所有所选格式。只在 DOCX 局部构建失败时重建 DOCX。
