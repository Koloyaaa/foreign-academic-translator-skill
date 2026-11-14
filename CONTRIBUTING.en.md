# Contributing

[中文](CONTRIBUTING.md) | English

> This is a translation of [CONTRIBUTING.md](CONTRIBUTING.md). The Chinese version is authoritative.

Contributions are welcome in translation quality, terminology, accessibility, page styling, and defenses against prompt injection in multilingual prompts.

## Before you submit

- Read the [README](README.md), the [security notes](SECURITY.md), and the `SKILL.md` for the harness you are changing.
- Reproduce the problem with synthetic text or material you are allowed to use. Do not publish real student handouts, names, school accounts, grades, or other personal information.
- The project provides four independent tiers: Lite, Plus, Pro, and Max. Lite and Plus use the legacy monolithic workflow; Pro and Max each include eleven sibling Skills. Identify the affected tiers before editing, and update their entry points, scripts, and documentation separately. A tier must not depend on another tier's runtime resources. The PPTX Reader includes its extraction script and requires LibreOffice for rendering. See the README for installation.

## What to include

- Describe the problem, the expected behavior, and the steps to reproduce it. For translation issues, include a de-identified excerpt of the source text and your suggested translation.
- For prompt injection issues, provide a synthetic sample with no real credentials and describe the expected handling.
- Update the README, harness guides, or usage docs affected by the change.
- Run the relevant skill structure checks. If you change the document generation scripts, also verify the corresponding HTML, DOCX, or Markdown output.
- Run the automated regression suite: `python -m unittest discover -s tests -v`.
- If you change Pro's state management or routing, also run `python -m unittest discover -s skills/pro/tests -v`.
- Check that the diff contains only this change, with no sample handouts, generated files, or scratch material.

## Compatibility

Do not change user-facing parameters or output formats unless the task requires it. Project-authored files that the author is entitled to license use MIT. Glossary entries, dependencies, and sample material may carry separate licenses; check the source and rights before adding any. Follow the applicable license and attribution requirements when adapting those materials.
