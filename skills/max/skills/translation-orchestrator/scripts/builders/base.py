"""构建器公共常量与工具函数。"""

import re
import unicodedata
from html import escape as html_escape
from html.parser import HTMLParser
from pathlib import Path

WATERMARK = "DornGames @Koloyaaa Léo WEE 出品: foreign-academic-translator-skill"

# 匹配带 data-en 的术语 span（保留原开/闭标签与属性，只在内层内容上补括号）
_SPAN_RE = re.compile(r'(<span\b[^>]*data-en="([^"]+)"[^>]*>)(.*?)(</span>)', re.DOTALL)
_SOURCE_MARKER_LABEL_RE = re.compile(r"^来源：(?:(?:PDF|PPT|原文)第\s*\d+\s*页)$")
_SOURCE_MARKER_MD_LINE_RE = re.compile(
    r"(?m)^[ \t]*\*\*(来源：(?:(?:PDF|PPT|原文)第\s*\d+\s*页))\*\*[ \t]*\r?$"
)

_MOJIBAKE_RE = re.compile(
    r"Ã[\u0080-\u00ff]|Â[\u0080-\u00ff]|â€|ï¿½|ðŸ|"
    r"ä¸|æ[\u0080-\u00ff\u2010-\u203a]|"
    r"[åèç][\u00a0-\u00ff\u2010-\u203a]"
)
_VISIBLE_TAG_FRAGMENT_RE = re.compile(
    r"</?(?:span|div|p|strong|em|sup|sub|table|thead|tbody|tr|td|th|"
    r"ul|ol|li|br|h[1-6]|section|article|img|a|script|style)\b[^>]*>",
    re.IGNORECASE,
)
_VISIBLE_ENTITY_FRAGMENT_RE = re.compile(
    r"&(?:[a-z]{2,16}|#(?:x[0-9a-f]+|\d+));",
    re.IGNORECASE,
)


class _RenderedTextCollector(HTMLParser):
    """Collect rendered text nodes while excluding non-visible script/style text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text_nodes = []
        self._suppressed_tags = []
        self._code_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._suppressed_tags.append(tag)
            return
        if not self._suppressed_tags and tag in {"code", "pre"}:
            self._code_depth += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._suppressed_tags:
            for index in range(len(self._suppressed_tags) - 1, -1, -1):
                if self._suppressed_tags[index] == tag:
                    del self._suppressed_tags[index]
                    break
            return
        if tag in {"code", "pre"} and self._code_depth:
            self._code_depth -= 1

    def handle_data(self, data):
        if data and not self._suppressed_tags:
            line, column = self.getpos()
            self.text_nodes.append((data, line, column, self._code_depth > 0))


def validate_rendered_text(html_text: str, output_format: str = "HTML") -> None:
    """Reject visible encoding corruption and leaked markup before publishing.

    The check runs on parsed text nodes, so ordinary HTML structure, valid math,
    and intentional tag examples inside code blocks do not trigger the gate.
    """
    parser = _RenderedTextCollector()
    parser.feed(html_text)
    parser.close()

    findings = []
    seen = set()

    def add_finding(kind, fragment, data, start, end, line):
        key = (kind, fragment, line)
        if key in seen or len(findings) >= 8:
            return
        seen.add(key)
        excerpt = " ".join(data[max(0, start - 28):min(len(data), end + 28)].split())
        findings.append(
            f"- {kind}；渲染正文第 {line} 行；片段 {fragment!r}；上下文 {excerpt!r}"
        )

    for data, line, _column, in_code in parser.text_nodes:
        for match in re.finditer("\ufffd", data):
            add_finding("Unicode 替换字符", match.group(0), data, match.start(), match.end(), line)
        for match in _MOJIBAKE_RE.finditer(data):
            add_finding("疑似乱码编码序列", match.group(0), data, match.start(), match.end(), line)
        for index, character in enumerate(data):
            if unicodedata.category(character) == "Cc" and character not in "\n\r\t":
                add_finding("不可见控制字符", character, data, index, index + 1, line)
        if not in_code:
            for pattern, kind in (
                (_VISIBLE_TAG_FRAGMENT_RE, "可见 HTML 标签源码"),
                (_VISIBLE_ENTITY_FRAGMENT_RE, "可见 HTML 实体源码"),
            ):
                for match in pattern.finditer(data):
                    add_finding(kind, match.group(0), data, match.start(), match.end(), line)

    if findings:
        details = "\n".join(findings)
        raise ValueError(
            f"{output_format} 质量门禁未通过：可见正文疑似乱码或源码片段泄漏。\n"
            f"{details}\n请修复统一 Markdown/编码后重新构建；不要用删除异常片段的方式掩盖问题。"
        )


def annotate_first_occurrences(text: str) -> str:
    """为每个术语的首次出现自动补上“（原文）”括号标注，后续出现不再标注。"""
    seen = set()

    def _replace(m: re.Match) -> str:
        opening, en, content, closing = m.groups()
        if en in seen:
            return m.group(0)
        seen.add(en)
        annot = "（" + en + "）"
        # 防御：span 内容已含括号（中文或英文）时不再追加“（原文）”，避免双括号/英文括号叠加
        if annot in content or any(ch in content for ch in "（）()"):
            return m.group(0)
        return opening + content + annot + closing

    return _SPAN_RE.sub(_replace, text)


def source_marker_label(text: str) -> str | None:
    """Return a standalone source-page label, or None for an ordinary paragraph."""
    candidate = " ".join((text or "").split())
    return candidate if _SOURCE_MARKER_LABEL_RE.fullmatch(candidate) else None


def style_source_markers(markdown_text: str, output_format: str) -> str:
    """Format standalone page-source labels for the selected document format."""
    def replace(match: re.Match) -> str:
        label = html_escape(match.group(1))
        if output_format == "html":
            return (
                "\n\n"
                '<p class="source-marker">'
                '<span class="source-marker-line" aria-hidden="true"></span>'
                f'<span class="source-marker-label">{label}</span>'
                '<span class="source-marker-line" aria-hidden="true"></span>'
                '</p>\n\n'
            )
        if output_format == "markdown":
            return (
                "\n\n"
                '<p align="center"><span style="color:#87919C;font-size:.86em;">'
                f'────────── {label} ──────────'
                '</span></p>\n\n'
            )
        raise ValueError(f"Unsupported source-marker output format: {output_format}")

    return _SOURCE_MARKER_MD_LINE_RE.sub(replace, markdown_text)


# 公式占位符保护：markdown 转换前先把 LaTeX 公式替换为占位符 @@MATHn@@，
# 避免公式中的 `_`（如 v_x）与 `*` 被 markdown 转成 <em>/<strong> 把公式切碎，
# 也避免行间公式以字面 $$...$$ 落入正文。匹配优先级与 docx_builder 的公式正则一致：
# 先 $$...$$ 与 \[...\]（行间），再 $...$ 与 \(...\)（行内）。
_MATH_RE = re.compile(
    r"\$\$(.+?)\$\$"        # $$...$$（行间）
    r"|\\\[(.+?)\\\]"       # \[...\]（行间，兼容兜底）
    r"|\$(.+?)\$"           # $...$（行内）
    r"|\\\((.+?)\\\)",      # \(...\)（行内，兼容兜底）
    re.DOTALL,
)


def protect_math(text: str):
    """把文本中的 LaTeX 公式替换为 @@MATHn@@ 占位符，返回 (protected_text, math_list)。

    math_list 按出现顺序保存原始公式文本（含 $...$ / $$...$$ 等定界符），
    配合 restore_math 原样还原，保证 markdown 转换后公式仍以完整形式存在。
    """
    math_list = []

    def _replace(m: re.Match) -> str:
        math_list.append(m.group(0))
        return "@@MATH%d@@" % (len(math_list) - 1)

    return _MATH_RE.sub(_replace, text), math_list


def restore_math(text: str, math_list) -> str:
    """把 @@MATHn@@ 占位符按顺序还原为原始公式文本。"""
    for i, latex in enumerate(math_list):
        text = text.replace("@@MATH%d@@" % i, latex)
    return text


# 兜底 CSS（当项目 templates/html_style.css 不存在时使用）
_FALLBACK_CSS = """
body { font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif; max-width: 1100px; margin: 30px auto; padding: 20px 30px; line-height: 1.8; color: #1e2a3a; background: #fafbfc; }
h1 { color: #0b2a4a; font-size: 1.9em; font-weight: 800; letter-spacing: 2px; line-height: 1.35; background: linear-gradient(135deg, #eaf3fa, #f8fbfd); border-left: 8px solid #2a7a9c; border-radius: 8px; box-shadow: 0 2px 10px rgba(11,42,74,0.10); padding: 18px 24px; margin: 0 0 30px 0; }
h2 { color: #0e3a55; font-size: 1.5em; font-weight: 800; letter-spacing: 1px; margin-top: 40px; margin-bottom: 16px; background: #e3f0f7; border-left: 7px solid #2a7a9c; border-bottom: 2px solid #c3d8e6; border-radius: 6px; padding: 12px 16px; }
h3 { position: relative; color: #124a6b; font-size: 1.24em; font-weight: 700; margin-top: 26px; margin-bottom: 12px; padding: 8px 14px 8px 28px; background: linear-gradient(to right, #e8f3f9, #ffffff); border-radius: 6px; }
h3::before { content: ""; position: absolute; left: 13px; top: 50%; transform: translateY(-50%); width: 8px; height: 8px; border-radius: 50%; background: #f5b86e; }
p { margin: 1em 0; text-align: justify; }
hr { border: none; border-top: 2px dashed #d0d7de; margin: 25px 0; }
table { border-collapse: collapse; width: 100%; margin: 20px 0; }
th, td { border: 1px solid #d8e0e8; padding: 8px 12px; }
th { background: #1a3c5e; color: #ffffff; text-align: left; }
.concept-table { width: 100%; border-collapse: collapse; }
.concept-table th { background: #1a3c5e; color: white; padding: 8px; }
.concept-table td { border: 1px solid #ddd; padding: 8px; }
span[data-en] { background: #fff1d6; padding: 2px 6px; border-radius: 4px; font-weight: 600; color: #8a5a1a; border-bottom: 2px solid #f5b86e; cursor: help; }
.source-marker { text-align: center; color: #87919c; font-size: .84em; margin: .35em 0 1.25em; }
.source-marker::before, .source-marker::after { content: "──────────"; color: inherit; }
"""


def load_css() -> str:
    """读取项目内置样式 templates/html_style.css，不存在则返回兜底 CSS。"""
    css_path = Path(__file__).parent.parent.parent / "templates" / "html_style.css"
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            return f.read()
    return _FALLBACK_CSS
