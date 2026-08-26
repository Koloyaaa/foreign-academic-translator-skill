# foreign-academic-translator

中外合办外文学案翻译专家 Skill。将外文学案（英语/法语等）精准翻译为中文，强制分级术语检索，支持 HTML / DOCX / Markdown 多格式一键导出。

## 效果图 (HTML / DOCX, 选择概念对照模式下)

<img width="2561" height="1393" alt="3d1d82df6bfeb76f98cdc7de13f14a04" src="https://github.com/user-attachments/assets/f152816d-edb6-41d5-ba26-26e9aad1f81a" />

<img width="2451" height="1240" alt="138bab0f5c636d495aef906d06268587" src="https://github.com/user-attachments/assets/120d02bc-84d3-4a5f-8ec7-15feb143d209" />

## 目录结构

```text
zwhb/
├── SKILL.md                  # Skill 行为定义（各阶段流程门禁）
├── skill.yaml                # 参数 Schema（零默认值强制门禁）
├── requirements.txt          # Python 依赖清单
├── README.md                 # 本文件
├── docs/
│   └── usage_guide.md        # 用户使用手册
├── scripts/                  # 构建与处理脚本（复用，禁止重写）
│   ├── builder.py            # 统一调度：md → html/docx/md
│   ├── text_extractor.py     # 源文件文本提取（.pdf/.docx/.txt）
│   ├── term_catcher.py       # 术语匹配（Grep 式搜索）
│   ├── glossary_loader.py    # 术语表加载
│   ├── init.py / utils.py    # 辅助工具
│   └── builders/             # html_builder / docx_builder / md_builder / base
├── glossaries/               # 7 大学科 CSV 术语表
└── templates/                # 样式模板（html_style.css 等）
```

## 安装到 Trae

> 官方文档：https://docs.trae.cn/ide/skills

### 方式一：技能面板上传（推荐）

1. 将本文件夹压缩为 `foreign-academic-translator-skill.zip`，确保 `SKILL.md` 位于压缩包根目录（其余脚本、词库等资源随包附带）。
2. 打开 Trae，点击右上角 **设置（齿轮图标）** → 「**规则与技能**」。
3. 进入「**技能**」标签页，点击「**+ 创建**」。
4. 在创建窗口点击「**上传进行智能解析**」，选择下载好的 `foreign-academic-translator-skill.zip`。
5. Trae 自动解析 `SKILL.md` 并回填技能名称、描述等信息，按需核对后确认。
6. **确认生效范围**：
   - **全局技能**：所有项目可用，存放于 `%USERPROFILE%\.trae-cn\skills`。
   - **项目技能**：仅当前项目可用，存放于项目目录下 `.trae/skills`。

### 方式二：手动解压到目录

1. 解压 `foreign-academic-translator-skill.zip`，得到含 `SKILL.md` 的文件夹。
2. 将整个文件夹放入对应目录：
   - 全局：`%USERPROFILE%\.trae-cn\skills\`
   - 项目：`<项目目录>\.trae\skills\`
3. 重启 Trae 使其生效，在技能面板的「全局」或「项目」标签中确认可见。

> 依赖：首次使用需安装 Python 依赖，在 skill 目录下运行 `pip install -r requirements.txt`。

## 参数（零默认值，全部必填）

| 参数 | 说明 | 枚举值 |
| :--- | :--- | :--- |
| `source_text` | 源学案纯文本（自动注入） | — |
| `discipline` | 学科大类（须匹配词库目录） | Engineering / Economics / Science / Agriculture / Social_Sciences / Literature_Arts / Medicine |
| `output_formats` | 输出格式（至少一项） | html / docx / md |
| `layout` | 展示布局 | translation_only / translation_first / source_first / concept_highlight |
| `show_concept_table` | 是否生成概念表 | true / false |

## 核心流程

1. **穷举式强制门禁**：6 项参数缺一即停止追问，无默认值。
2. **源文本审阅清洗**：剔除页眉页脚、目录、乱码等无关内容。
3. **分级术语检索**：学科目录 → 文件名 → 字符串暴力搜索（省 Token）。
4. **翻译与输出**：术语以悬停标注原文的形式输出，概念表在文末自动生成。
5. **产物交付自检**：先落盘 Markdown，再生成所选格式，逐项校验文件存在且非空。

## 说明

- HTML 样式：修改 `templates/html_style.css`；Word 模板预留 `word_template.docx`。
- 产物默认输出至 `output/docs/`。

---

## 声明

**禁止以任何形式对本 Skill 进行商业化使用，仅供个人学习交流使用。**

Skill 中附带的词库来源于中国台湾省教育研究院乐词网，已剔除或修改大量不合规词汇。词库中的任何内容都仅供参考，不代表本人在任何领域的任何观点，与本人的意识形态无关，本人坚决拥护一个中国原则。
