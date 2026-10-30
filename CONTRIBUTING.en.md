# Contributing

[中文](CONTRIBUTING.md) | English

> This is a translation of [CONTRIBUTING.md](CONTRIBUTING.md). The Chinese version is authoritative.

Contributions are welcome in translation quality, terminology, accessibility, page styling, and defenses against prompt injection in multilingual prompts.

## Before you submit

- Read the [README](README.md), the [security notes](SECURITY.md), and the `SKILL.md` for the harness you are changing.
- Reproduce the problem with synthetic text or material you are allowed to use. Do not publish real student handouts, names, school accounts, grades, or other personal information.
- Keep the Codex, Claude Code, and Trae packages behaving the same way. If you change only one version, explain why.

## What to include

- Describe the problem, the expected behavior, and the steps to reproduce it. For translation issues, include a de-identified excerpt of the source text and your suggested translation.
- For prompt injection issues, provide a synthetic sample with no real credentials and describe the expected handling.
- Update the README, harness guides, or usage docs affected by the change.
- Run the relevant skill structure checks. If you change the document generation scripts, also verify the corresponding HTML, DOCX, or Markdown output.
- Check that the diff contains only this change, with no sample handouts, generated files, or scratch material.

## Compatibility

Do not change user-facing parameters, output formats, or license notices unless the task requires it. Glossary entries and sample material may carry their own licenses; check the source and the rights before adding any. Keep the original author's attribution and the applicable license when sharing adaptations.
