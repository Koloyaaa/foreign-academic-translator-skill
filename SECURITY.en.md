# Reporting security issues

[中文](SECURITY.md) | English

> This is a translation of [SECURITY.md](SECURITY.md). The Chinese version is authoritative.

If you find that prompt injection could change the task, read unrelated files, or leak information, or that locally stored preferences, highlights, or notes could be sent somewhere unexpectedly, contact the repository maintainer privately. Do not post real course material, personal information, or credentials in a public issue.

Please include:

- the harness, operating system, and skill version you used;
- minimal reproduction steps that are safe to publish;
- expected behavior and actual behavior;
- whether external network access, file reads, or personal data are involved.

Use synthetic documents instead of real course material. Treat prompt injection samples as text to be handled, and do not attach real command output, tokens, or access links. Give the maintainer reasonable time to investigate and fix the issue before reporting it publicly.

This project keeps HTML personal marks and reading settings in the user's browser, and parameter preferences in `output/.translator_preferences.json` inside the project. Those files should contain only the user's choices, never course content or credentials.
