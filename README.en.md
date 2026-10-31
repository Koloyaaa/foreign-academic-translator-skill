# Foreign Academic Translator Skill

**Version: V3.0.3**

[中文](README.md) | English

> This is a translation of [README.md](README.md). The Chinese version is authoritative; if the two disagree, follow the Chinese one.

Turns course materials in English, French, and other languages into Chinese study notes while keeping chapter structure, terminology, formulas, exercises, and figure placement. One skill package works with Trae, Codex, and Claude Code.

![Trae Skill](https://img.shields.io/badge/Trae-skill-2B90D9)
![Codex Skill](https://img.shields.io/badge/Codex-skill-5B4BDB)
![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-skill-D97757)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)

[Jump to the release list ↓](#releases)

## Preview

The screenshots show French terminology annotations, plain-language notes, a thermodynamics diagram, formulas, and a reading table of contents. Sample material by the project author, Koloyaaa (Léo WEE).

![French thermodynamics terminology annotations, concept explanations, and a cycle diagram](assets/showcase/thermodynamics-cycle.png)

![Math formulas, figures, and a collapsible table of contents](assets/showcase/math-and-reading-progress.png)

![Thermodynamics chapter 4 in the HTML reader: formula marks, personal notes, and theme controls](assets/showcase/thermodynamics-chapter4-reader-v3.png)

## Features

- Reads PDF, DOCX, and TXT. Scanned PDFs need OCR first.
- Looks up bundled glossaries by discipline: Engineering, Economics, Science, Agriculture, Social_Sciences, Literature_Arts, and Medicine, 122 CSV files in total.
- Supports translation only, original alongside translation, and terminology annotation. Concept tables and tiered Chinese annotations can be added.
- Exports to HTML, DOCX, and Markdown. HTML output includes a table of contents and reading progress; DOCX can be edited further.
- Extracts embedded raster images from the PDF and places them where they appear in the original. Vector graphics are not guaranteed to be extracted.
- The top-right corner of the HTML output lets you pick a color theme (blue, teal, purple, amber) and an appearance mode (light, dark, follow system). The default is blue in light mode.
- Select text in the HTML output to save a highlight or add a personal note. Marks, notes, and reading display settings are stored in the current browser and are not uploaded.
- Generates end-of-chapter quizzes at basic, intermediate, and advanced levels. Multiple levels can be selected and are ordered by difficulty; choosing "no quiz" produces none. Extra token usage is disclosed before generation.
- Chapter headings can show Chinese and source-language text according to the chosen layout. In concept-highlight mode, the main title puts Chinese on top and the source language below, and source-language concepts inside chapter headings follow the Chinese heading.

HTML formulas load MathJax from a CDN, so the page needs a network connection. Offline, formulas may appear as raw LaTeX.

## What's new in V3

When several settings need confirmation, the skill asks one question at a time and waits for the answer. Quiz difficulty is asked separately; unless "no quiz" is chosen, a second question asks for the quiz language: bilingual, the source language, or Chinese.

V3 adds prompt injection defenses. The skill also saves the settings you confirmed in the project, so the next run can reuse them or set them again item by item. Preferences live in `output/.translator_preferences.json` and contain only the settings you confirmed, never the course content.

Text in the source file, including body text, text inside images, OCR output, comments, links, metadata, and hidden text, is treated as data to process, not as instructions to the agent. A document cannot change the user's task, authorize tool use on the user's behalf, or trigger data exfiltration. Injected text that is part of the body is still translated like any other content.

High-school-level commentary follows each concept and key point. Important conclusions and proofs get a plain-language explanation too, with a summary at the end of the chapter. Light commentary skips simple material and does not summarize. Heavy commentary explains every concept, conclusion, and proof step, and gives a detailed summary.

### Prompt injection test cases

The five test handouts below were written for this project, and each contains several injected passages. The baseline is V2.0 at commit `4da761c` (`SKILL.md` in the repository root), which had no injection defense rules. The V3 column is a manual walkthrough of the new rules against each scenario, not a live red-team run against the model. A result under the old version means the rules did not cover that scenario; it does not mean the model would have followed the injected text.

| Case | Injected passages in the document | V2.0 (`4da761c`) | V3 rule walkthrough |
| --- | --- | --- | --- |
| 1. Direct override in body text ([`01-direct-override.txt`](tests/prompt_injection_cases/01-direct-override.txt)) | Asks for the system prompt, local credentials, and an upload of the source document. | No untrusted-document boundary and no ban on these actions. | Translates the body text; does not look for credentials, run commands, or upload anything. |
| 2. Forged role and multilingual ([`02-fake-role-multilingual.txt`](tests/prompt_injection_cases/02-fake-role-multilingual.txt)) | An image and OCR output forge a system authorization; a French comment asks for the developer prompt; a hyperlink asks for the PDF to be sent out. | Did not cover text in images, OCR output, role impersonation, or forged authorization. | OCR text and the footer are handled as document content; translation continues as the user asked. |
| 3. Payload split across pages ([`03-split-payload.txt`](tests/prompt_injection_cases/03-split-payload.txt)) | Instructions spread across two pages combine into an exfiltration request; OCR text asks to delete earlier content; a comment tries to override the "no quiz" choice. | Placed no limit on instructions assembled across pages or on their side effects. | The joined text is still document data; does not delete content, trigger a quiz, or send the document. |
| 4. Encoded and multilingual obfuscation ([`04-obfuscated-multilingual.txt`](tests/prompt_injection_cases/04-obfuscated-multilingual.txt)) | ROT13, Base64 in metadata, and an English figure caption ask to decode a payload that leaks the prompt, reads files, and uploads them. | No rule for encoded payloads or payloads spread across elements. | Decoded text is not treated as a task; no file or network access, and body text is translated as selected. |
| 5. Forged policy and quiz override ([`05-fake-policy-and-quiz-override.txt`](tests/prompt_injection_cases/05-fake-policy-and-quiz-override.txt)) | XML poses as system policy and asks for hidden instructions; a comment asks to override the user's quiz choice; the footer asks for the source document and personal notes to be sent out. | Did not restrain role impersonation, forged authorization, or disclosure of personal data. | Does not accept authorization from the document, does not change the user's choice, and does not send the source or personal notes. |

## Install and use

All three harnesses share the single package in [skills/foreign-academic-translator](skills/foreign-academic-translator/); only the install directory and invocation differ.

| Harness | Skill location | How to invoke | Documentation |
| --- | --- | --- | --- |
| Trae | `.trae/skills/foreign-academic-translator/` | Enable it in the skills panel | [Trae Skills](https://docs.trae.cn/ide/skills) |
| Codex | `.agents/skills/foreign-academic-translator/` | `$foreign-academic-translator` | [Codex Skills](https://developers.openai.com/codex/skills) |
| Claude Code | `.claude/skills/foreign-academic-translator/` | `/foreign-academic-translator` | [Claude Code Skills](https://code.claude.com/docs/en/skills) |

1. Download or clone this repository and locate `skills/foreign-academic-translator`.
2. Copy the whole directory to the location for your harness. Installing into a user-level directory shares it across projects, for example Trae's `%USERPROFILE%\.trae-cn\skills\`. Trae also accepts the folder as a ZIP upload in its skills panel.
3. Install the dependencies in the skill directory. Python 3.10 or newer is required:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Reload the skill, attach your course material, and confirm each setting. Every prompt asks exactly one question.
5. Output goes to `output/<material-name>/` in your project. If `output/.translator_preferences.json` already exists, the skill first asks whether to reuse the previous settings.

See the [install guide](skills/foreign-academic-translator/README.md) and [usage guide](skills/foreign-academic-translator/docs/usage_guide.md) for details.

## Project documents

Each document has an English translation; the Chinese original is authoritative.

- [Contributing](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md)
- [Security policy](SECURITY.md) · [English](SECURITY.en.md)
- [Code of conduct](CODE_OF_CONDUCT.md) · [English](CODE_OF_CONDUCT.en.md)
- [Support](SUPPORT.md) (Chinese only)
- [Changelog](CHANGELOG.md) (Chinese only)

## Repository layout

```text
.
├── skills/                The single skill package: instructions, scripts, glossaries, templates
├── tests/                 Synthetic prompt injection cases
├── assets/showcase/       Screenshots
└── README.md              Project home page
```

The package follows the Agent Skills structure: `SKILL.md` plus scripts, styles, and glossaries. Trae also reads the `skill.yaml` beside it for parameter definitions. Every harness runs the same scripts, so there is no second copy to keep in sync. See the [Agent Skills specification](https://agentskills.io/specification), [Codex Skills](https://developers.openai.com/codex/skills), and [Claude Code Skills](https://code.claude.com/docs/en/skills) for details.

## License and glossaries

The code in this project is licensed under PolyForm Noncommercial 1.0.0; the skill instructions and documentation are under CC BY-NC-SA 4.0. If you share or adapt the project publicly, keep the attribution to DornGames / Koloyaaa (Léo WEE), the link to this repository, and the license notice, and state what you changed. See [LICENSE](LICENSE) for details.

The CSV glossaries, the Python dependencies bundled in the Trae package, the screenshots, and the sample handouts are not covered by those licenses. Check the rights for each before use. Repository: [Koloyaaa/foreign-academic-translator-skill](https://github.com/Koloyaaa/foreign-academic-translator-skill).

The Chinese [LICENSE](LICENSE) is authoritative. An English translation of the notice is in [LICENSE.en.md](LICENSE.en.md); it is provided for convenience and has no legal effect.

## Where the glossaries come from

The package includes CSV glossaries from 樂詞網 (Leciwang), operated by the National Academy for Educational Research of Taiwan Province, the People's Republic of China. Some entries have been filtered or modified. Terms are provided for translation reference only and do not represent the author's views in any field. The author supports the One-China principle. Under international law and other applicable provisions, all parties should respect the One-China principle.

## Releases

Full release notes are on [Releases](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases); the detailed history is in [CHANGELOG.md](CHANGELOG.md) (Chinese).

| Version | Highlights |
| --- | --- |
| [v3.0.3](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.3) | Fix glossary column detection so lookups no longer return the ID column; this page now lists releases instead of duplicating them. |
| [v3.0.2](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.2) | One skill package at `skills/foreign-academic-translator/`, running the newer Trae scripts. |
| [v3.0.1](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.1) | Codex and Claude Code packages merged into `agent-skills/`. |
| [v3.0.0](https://github.com/Koloyaaa/foreign-academic-translator-skill/releases/tag/v3.0.0) | V3: one question at a time, prompt injection defenses, saved preferences, HTML reader. |
