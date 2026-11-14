# PDF / PPTX 图示讲解文件契约

文件由 `foreign-academic-visual-explainer` 生成，供正文翻译与质量审计读取。每个讲解都需链接到最终 PDF/PPTX manifest 的物理页码和对象 ID。

```markdown
<!-- VISUAL_EXPLANATION:PDF_PAGE:3:IMAGE:002 -->
**图示解读（PDF第 3 页）**

图中……（只陈述该图直接支持的内容；观察与推断分开写。）
```

规则：

- 只写匹配 Reader 的 `visual_explanation_candidate_pages` 或 `visual_explanation_candidate_slides` 中经视觉核对的页面。
- 每页一个或多个图示区块；首行按源类型标记“图示解读（PDF第 X 页）”或“图示解读（PPT第 X 页）”。PDF 按物理 PDF 页码标注，画面印刷页码另行保留。
- 只描述图片/图表等非文本载荷提供的新信息；不重述课件已经提取完整的文字。
- 关键关系、数值、单位和标签需可回溯到 manifest 项或页图。无法确认时标出页码与对象 ID，不猜。
- 类比和解释若用于帮助学生理解，明确标注为辅助理解；不得伪装成 PDF/PPTX 原文。
- 文件以 `# Visual explanations` 开始；每个区块记录稳定对象锚点，方便审计定位。

空候选页时不调用此 Skill；不要创建空文件冒充已完成。
