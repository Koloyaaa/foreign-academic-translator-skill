---
name: translation-orchestrator
description: Coordinate foreign academic handout workflows, choose the quick or full translation route, resolve settings, route only required reading, quiz, publishing, and audit Skills, and deliver selected files.
license: MIT
metadata:
  version: "3.3.0"
---

## 强制 Skill 使用声明

- 在本 Skill 开始实质工作前，先向用户单独输出一行：`当前使用 Skill：translation-orchestrator`。如果编排器已在进入本阶段前输出了这一行，不重复。
- 硬性阶段门禁：编排器必须在调用目标 Skill 前，先单独向用户输出 `当前使用 Skill：<skill-name>`；没有编排器时，由目标 Skill 自行先输出。未出现目标 Skill 的声明行，不得启动该阶段。
- 只声明本轮真正执行的 Skill，不声明仅被列为候选或因缓存命中而跳过的 Skill。这是对话进度提示，不得写入讲义、译稿、测验或其他产物。

# 外文学案翻译编排 Skill

本 Skill 是唯一需求入口，负责需求与偏好、材料分流、缓存检查、阶段编排、交接和交付。只加载本轮会执行的 Skills；格式转换尽量交给确定性构建器。不要把整份源文、整份译稿或完整历史提示词复制到另一个 Skill 的上下文。

## 按需加载

- 先解析用户本轮明确要求和已有偏好，再检查文件扩展名与材料结构。用户本轮明确设置优先；学科和主要源语言基于当前材料推断。
- 在检查 `translate` 缓存前，先选择 `translation_route=quick` 或 `translation_route=full` 并写入任务清单。仅当材料短小、结构清楚、可一次通读，且为无视觉内容的 DOCX/TXT 或纯文本时选 `quick`；PDF/PPTX、扫描/OCR、图像/图表、复杂表格、需要页码视觉追踪、材料过长或任何不确定情况都选 `full`。DOCX 的文本提取不含图片；不能仅凭提取文本判断 DOCX 没有视觉内容，须检查包内媒体/图表对象，无法确认时选 `full`。用户明示要完整逐页处理时选 `full`；用户要求快速处理也不能让超出快速路径范围的材料绕过长线读取门禁。
- 检查 `.translator-cache-pro/` 中已审计 Markdown、测验及所选格式阶段。内容和相关版本匹配时复用；只改发布格式时不重读原件、不重译。
- `translation_route=quick` 时，DOCX/TXT 调用共享 `scripts/text_extractor.py` 一次，再调用 `foreign-academic-quick-translator`；不加载完整正文翻译 Skill。路线为 `full` 时，PDF 内容阶段缓存未命中则调用 `foreign-academic-pdf-reader`，完成结构提取、全页渲染、按当前宿主能力进行逐页视觉核对或明确记录跳过，并通过相应门禁；不得以 OCR 代替看图。PPTX 同理调用专用 Reader；完整路线的 DOCX/TXT 使用共享提取器。
- PDF/PPTX 必须先判定当前宿主与模型的组合能否看图：只有当前模型明确支持图像输入，且宿主能把渲染页像素作为图像内容交给它，才记为 `available`；当前模型明确不支持图像输入，或宿主没有实际传图通道，才记为 `unavailable`。优先依据当前会话的模态说明；说明缺失时，通过真实通道传入一张渲染页确认模型是否收到图像内容。模型品牌/型号、文件路径、OCR 或文字描述本身都不能证明有看图能力。能力不确定时不能标成 `unavailable`，先核实当前会话；通道可用但某页加载失败属于审核失败，不能借此跳过。
- PDF/PPTX 的 `vision_capability=available` 时，Reader 必须逐页查看每张渲染图并核对所有对象。页图不可用、对象漏核或视觉结论不确定时保留 `PARTIAL`/`FAIL`，不能降级成跳过。仅当 `vision_capability=unavailable` 时跳过视觉核对：不给 Reader 伪造视觉 JSON，完成结构提取与页码交接，生成 `gate=SKIPPED_NO_VISION`，继续基于提取文本翻译和共同质量审计。该状态不是视觉通过；最终译稿必须含“处理限制”，列出未审核页/幻灯片及视觉内容可能遗漏。能力不可用时不调用视觉讲解 Skill；有能力时只在 Reader 标记候选页后调用。
- 正文翻译只在其缓存未命中时调用；测验 Skills 仅在用户选择测验且测验缓存未命中时调用；只加载所选且未缓存的 HTML/DOCX 发布 Skill；Markdown 使用共享构建器。
- 若测验出题与解析都要执行，可在共享内容上下文中依次完成，避免跨调用复制整份讲义。否则分阶段读取文件，只保留路径、页码锚点、哈希、状态和缺陷编号。
- 子 Skills 从同一 `.translation-task-pro.json` 读取参数，不重复提问、不读取/修改偏好。宿主不能按名称调用 Skill 时，只读取同级目录中当前阶段所需的 `SKILL.md` 及其相关参考文档。

## 多 Agent 默认调度

- 多 Agent 是默认工作方式，不需用户额外开启。当前宿主支持子 Agent/委派时，把可独立完成的工作拆成至少两个有实际产物的任务并交给不同子 Agent；可并行的就并行。缓存命中而无需执行的阶段不创建空转 Agent。若本轮只有一个不可拆分工作包且没有未缓存的独立审计阶段，才直接单 Agent 完成；宿主不支持子 Agent 时采用单 Agent 兼容流程，并在进度中如实说明。
- 编排器始终是唯一协调者：负责询问用户、选择路线、读取/更新任务清单和缓存、分配边界、合并结果、运行门禁及最终交付。子 Agent 只接收完成任务所需的最小上下文；不得自行重提取原件、覆盖共享 manifest/state/cache 或共同编辑同一个输出文件。不同子 Agent 写入各自的临时产物，由编排器合并并核对覆盖。
- 按依赖拆分工作：PDF/PPTX 只解析一次；渲染完成后可将不重叠的页段分给多个 Reader 子 Agent 核对，再由编排器合并逐页记录并运行 Reader finalizer。正文翻译可按不重叠的章节/页段拆分；源文准备完成后，用户选择的测验草拟可与正文翻译并行，答案解析必须等题目草稿完成。视觉解释候选和互不重叠的正文页段可并行处理。正文/测验生成后由未参与对应起草的子 Agent 执行独立质量审计；语义门禁通过后，多个所选格式可由不同 Publisher 子 Agent 并行发布。最终所有结果须汇回编排器，统一检查页码、coverage、文件路径和审计状态。
- 模型档位设硬上限：若用户明确选择了模型或推理档位，任何子 Agent 只能使用相同或更低档位，不得为了分工升级。用户没有显式选择档位时，子 Agent 继承当前会话的模型设置；档位未知或不可比较时不指定模型覆盖，使用继承档位。若宿主不能保证子 Agent 不会高于用户选择，则不要启动该类 Agent，改用能保证遵守上限的委派方式；没有这种方式时退回单 Agent 并说明限制。
- 视觉任务只能交给当前子 Agent 确实支持图像输入并能收到页图像素的模型。若用户档位上限内没有这样的子 Agent，由当前有看图能力的编排器完成视觉审核；不得因为子 Agent 不会看图而把宿主能力改记为 `unavailable` 或跳过视觉门禁。
- 子 Agent 执行 Skill 不会替代主对话中的名称声明。编排器必须在主对话先输出目标 Skill 的 `当前使用 Skill：<skill-name>`，再调用或委派该阶段；不得依赖用户看不到的子 Agent 内部对话满足声明门禁。质量审计始终是独立必经阶段，不得与起草合并或跳过。
- `.translation-state-pro.json` 与本轮决策日志由编排器单写者顺序更新。并行子 Agent 返回时，编排器逐个记录完成结果；同一阶段尚有分块未合并时用 `redecide --continue-stage` 记录“继续当前阶段”。必须先读取上一次决策输出，再启动获准的下一个阶段；不得并发写 state。

## 路由

| 环节 | Skill | 条件 |
| --- | --- | --- |
| 短线正文翻译 | `foreign-academic-quick-translator` | `translation_route=quick`；仅限符合适用范围的简单 DOCX/TXT 或纯文本 |
| 长线正文翻译 | `foreign-academic-lesson-translator` | `translation_route=full`；PDF/PPTX、视觉或结构复杂、过长或不确定材料 |
| PDF 结构提取与逐页视觉核对 | `foreign-academic-pdf-reader` | 原件为 PDF 且正文、测验或语义审计需要源文 |
| PPTX 结构提取与逐页视觉核对 | `foreign-academic-pptx-reader` | 原件为 PPTX 且相关内容阶段未命中 |
| PDF/PPTX 图示学习说明 | `foreign-academic-visual-explainer` | 对应 Reader 发现信息密集图示候选页 |
| 题目草稿 | `foreign-academic-quiz-generator` | 选择测验且测验缓存未命中 |
| 答案核验与解析 | `foreign-academic-solution-explainer` | 选择测验且测验缓存未命中 |
| HTML / DOCX 发布 | 对应 publisher Skill | 用户选择格式且格式缓存未命中 |
| Markdown 发布 | 本套件共享构建器 | 用户选择 Markdown 且格式缓存未命中 |
| 正文/测验语义门禁 | `foreign-academic-quality-auditor` | 对应审计缓存未命中 |
| 格式专项检查 | 对应 publisher Skill | 成品新建或格式缓存未命中 |

## Skill 完成后重新决策（Pro 必需）

每次实际 Skill 返回后，编排器先检查该 Skill 的输出与门禁，再用 `workflow_state.py mark` 记录已完成阶段，紧接着运行 `workflow_state.py redecide`。缺少这条记录不得启动下一个阶段。`redecide` 会按任务选择、已完成阶段和依赖关系计算当前可执行阶段，记录编排器选择、简短理由、门禁和缺失依赖；默认选择最靠前的可执行阶段，可用 `--next-stage` 选择另一个已就绪阶段。它也会把事件写入 Pro state 及本轮保留日志 `.pro-decisions-<workflow_run_id>.jsonl`，不写课程原文。

正文阶段示例（状态路径和任务清单都必须是 Pro 专属文件）：

```powershell
python "<shared_runtime>\scripts\workflow_state.py" redecide `
  --state "<output_dir>\.translation-state-pro.json" `
  --task "<output_dir>\.translation-task-pro.json" `
  --completed-stage translate `
  --completed-skill foreign-academic-quick-translator `
  --outcome passed `
  --reason "正文和 coverage 已生成；下一步执行独立全文正文审计。"
```

命令返回 `decision.action`：`start_stage` 才可进入指定阶段；`continue_skill` 用于测验出题后接答案解析；`continue_stage` 表示同一 Skill 的分块工作未合并；`stop_for_repair` 要先修复并重跑；`wait_for_dependency` 表示前置阶段尚未完成；`deliver` 表示所有已选阶段都通过。`workflow_state.py start/mark` 会拒绝未被最近一次决策授权的阶段，形成实际顺序门禁。

- `foreign-academic-quiz-generator` 完成后立即调用 `redecide --completed-stage quiz --completed-skill foreign-academic-quiz-generator --outcome passed`；脚本强制返回 `continue_skill` 并指定 `foreign-academic-solution-explainer`。解析 Skill 完成、测验阶段标记后，再记录下一步决策。
- PDF/PPTX 的 `review_*` 阶段必须在 `mark --gate PASS` 后决策；只有当前模型明确不支持图像输入或宿主没有实际传图通道时才可 `mark --gate SKIPPED_NO_VISION`，并继续仅可提取文本的路线。视觉能力可用时，`SKIPPED_NO_VISION` 会被脚本拒绝；解析、部分核对或缺页不得标成 PASS。
- 缓存命中时不声明未执行的 Skill。先验证 Pro cache 签名与产物哈希，将有效结果登记到本轮 Pro state，再用 `redecide --completion-source cache --outcome passed` 记录缓存阶段和后续选择。禁止从 Max 或其他档位导入阶段通过状态。
- 多个子 Agent 执行同阶段不同分块时，每个已返回的分块都应记录一次 `redecide --continue-stage`；收齐并合并后，由编排器完成阶段门禁、`mark`，再记录最终决策。state 更新必须串行。

## 需求与偏好

偏好文件路径为项目的 `output/.translator_preferences.json`，只由本 Skill 读取和更新。

- 用户本轮明确设置优先。学科和主要源语言每份材料重新识别，不写入偏好。
- 偏好文件存在且用户没有说明是否沿用时，只询问是否沿用。用户同意后，偏好仅补充本轮未指定且不能从材料推断的选项；用户拒绝则忽略。
- 偏好文件不存在时不询问历史偏好。只询问确实影响产物、且无法从本轮内容、材料或已接受偏好推断的必要选项；不要重复确认已确定值。无测验时不询问测验语言。
- 全文交付是默认目标。长材料按页或章节连续完成，不因篇幅提前结束。遇到真实阻塞时准确说明页码和未完成项。

可复用选项包括：输出格式 `html/docx/md`；布局 `translation_only`、`translation_first`、`source_first`、`concept_highlight`；概念表开关；注释等级；源文件配图开关；术语策略 `system_glossary` 或 `ai_auto`；测验难度与语言。收齐参数后只将这些可复用值和更新时间写回偏好，不保存学科、源语言、源文或提取文本。

## 任务清单与执行

在 `output/<学案名>/` 下建立临时 `.translation-task-pro.json`、本轮 `.translation-state-pro.json`、持久 `.translator-cache-pro/` 和本轮决策日志 `.pro-decisions-<workflow_run_id>.jsonl`。清单必须写入 `workflow_tier=pro`、`quality_profile=pro-full-content-audit-v1`、唯一 `workflow_run_id`、`decision_log_file`、Pro 专属的 `state_file`、`cache_dir` 与 `cache_state_file`。状态脚本校验这些路径并把 tier/profile/cache 目录纳入所有签名，因此不能读取其他档位的任务状态或审计缓存。创建或校验任务清单时读取 `references/task-handoff.md`。任务清单记录 `translation_route` 与简短路线理由；路线属于翻译阶段设置，必须参与缓存签名。PDF/PPTX 任务还必须写入当前宿主 `vision_capability`、简短 `vision_capability_evidence`，以及宿主可提供时的 `vision_model_id`；能力与证据参与视觉阶段缓存签名。任务与缓存状态仅存路径、设置、版本、用量（宿主明确提供时）和哈希，不存原始提取正文。缓存保留经门禁的统一 Markdown、无正文 coverage index、核验通过的测验片段和阶段成品哈希；双语 Markdown 可能包含源文片段。

按以下顺序执行：

1. 检查持久 `translate`、`quiz`、`audit_translation`、`audit_quiz` 和所选格式缓存；本轮 state 还检查 PDF 的 `parse_pdf`、`review_pdf`、`explain_pdf` 及 PPTX 的 `parse_pptx`、`review_pptx`、`explain_pptx`。`translate` 检查键必须包含 `translation_route`，阶段指纹只纳入所选翻译 Skill 及真正影响该阶段的参数/资源；测验与发布格式设置不进入正文翻译签名。`resolved_config` 只补齐本轮未指定值，不覆盖用户明示设置。
2. 内容或审计阶段缓存未命中时准备源文。`quick` 只能处理符合快速路径范围的 DOCX/TXT 或纯文本，由共享提取器准备一次；若预检发现视觉、扫描、复杂结构、篇幅过长或完整性不确定，改设 `translation_route=full`。PDF/PPTX 分别运行对应 Reader 的结构提取。若 `vision_capability=available`，必须查看每页渲染图并完成对象覆盖核对；图像识别是主路径，OCR 仅作可选辅助。若 `vision_capability=unavailable`，不生成视觉核对记录，finalize 必须写明 `gate=SKIPPED_NO_VISION`、未审核页码和能力证据；允许继续翻译可提取文本，但译稿须在末尾含“处理限制”说明，不能声称视觉覆盖完整，也不能猜写未读图像。`PARTIAL`/`FAIL`，或 `available` 却没有逐页核对记录时，保留问题并停止生成。仅当视觉能力可用且有候选页时加载共享视觉讲解 Skill。完整路线的 DOCX/TXT 调用共享 `text_extractor.py`。
3. 正文缓存未命中时按 `translation_route` 调用一个翻译 Skill；两条路线都必须输出 `translated_core_markdown` 和简洁 coverage index，随后都进入同一个 `foreign-academic-quality-auditor` 正文审计。PDF 按物理页序标注“来源：PDF第 X 页”；PPTX 按幻灯片顺序标注“来源：PPT第 X 页”；跨页主题需在新页段重标来源。图示说明分别标为“图示解读（PDF第 X 页）”或“图示解读（PPT第 X 页）”，作为辅助内容而非原文。`include_images=true` 时只能引用 Reader 经视觉核对批准导出的正式图片；为 false 时不得把临时渲染图放进译稿。
4. 选择测验且缓存未命中时，先根据源文页码/标题/对象锚点起草题目，再核对唯一答案并写解析。没有测验时不加载出题与解析 Skills。按需组装正文和测验 Markdown。
5. 正文和测验语义审计分别查缓存，且在发布之前完成。PDF/PPTX 宿主视觉能力可用时，正文审计逐页核对文字、表格、视觉记录、图示说明、来源页码和译文覆盖；若 manifest 为 `SKIPPED_NO_VISION`，审计所有已提取文字和结构，但把视觉内容列为“未审核”，确认译稿没有编造，并检查“处理限制”准确列出页码。此时正文审计通过只表示可提取内容忠实，不代表视觉内容完整。测验审计只按题目锚点核对已提取源文支持、唯一答案和解析；不能考查未审核视觉内容。两条翻译路线都使用相同的审计 Skill 和通过标准。
6. 对缺陷只修复受影响锚点和必要邻段；修复正文或测验后复审对应范围。存在未解决 P0/P1/P2 时不得进入发布。
7. 语义审计通过后，对每个未命中的已选格式单独调用 `shared_runtime/scripts/builder.py`，每次只传一种格式。从同一份统一 Markdown 构建；所有格式构建器都必须拦截可见乱码、替换字符、异常控制字符和泄漏的 HTML 源码片段，HTML/DOCX 发布 Skill 再做相应格式检查。门禁失败时按报告定位修复统一 Markdown 或编码后重建；若修改影响正文语义，重跑受影响的审计范围。必须确认本次退出码为 0、返回路径正确且文件非空；目录中的旧同名成品不算本次成功。

PDF/PPTX 的结构清单、原文文本、页图和视觉核对记录可能包含课程材料，只保留在本轮工作区，不写入持久缓存。视觉核对及按需图示说明完成后，运行对应 Reader 的 `pdf_extractor.py fingerprint` 或 `pptx_extractor.py fingerprint`，将摘要写入 `pdf_processing_fingerprint` 或 `pptx_processing_fingerprint`。持久正文/测验/审计签名只保存该摘要、原件哈希、设置和执行规则指纹；不依赖临时原文文件存在。PDF/PPTX 正式图片仅在用户启用 `include_images` 且逐页核对明确选择后留在正式输出目录。

所有阶段用 `workflow_state.py check/start/mark` 记录输入、设置、成品哈希与耗时，并在每次 Skill 完成后运行 `redecide`。`mark` 对正文审计、测验审计和所选发布格式要求 `--gate PASS`；PDF/PPTX 视觉阶段只写本轮 Pro state，不写入持久 cache state。用量不可得时留空，不估算；缓存输入是 input token 的子集，不重复加到总量。只有对应门禁成功后才将译稿、测验或格式成品指纹写入 `.translator-cache-pro/`。并行分块可以继续使用，但只有编排器单写 state，并把每次决定按序记录。

## 清理与交付

所有语义审计和已选格式阶段通过后，清理本轮任务清单、state、测验草稿、提取文本、PDF/PPTX manifest、视觉核对 JSON、页图及其他临时文件。保留 `.pro-decisions-<workflow_run_id>.jsonl`、经审计 Markdown/coverage、已核验测验、所选成品、用户启用且经核对选择的正式图片与位置清单。运行中断或阶段失败时保留 Pro 检查点续跑；不得清理原件或任务开始前已有文件。

最终列出每个正式文件的格式、绝对路径和大小；有失败或未验证项时明确说明。Reader 为 `SKIPPED_NO_VISION` 时必须指出视觉核对因宿主无图像输入而跳过，以及涉及的页码/幻灯片范围。
