"""Markdown 构建器：在内容顶部与底部各插入 WATERMARK 注释后写出文件。"""

from pathlib import Path
from html import escape

from .base import annotate_first_occurrences, style_source_markers, validate_rendered_text


def build_markdown(md_content: str, output_path: Path) -> Path:
    """将 Markdown 内容加上水印注释后写盘（术语首次出现自动补原文括号）。"""
    marker = "<!-- WATERMARK -->"
    body = style_source_markers(annotate_first_occurrences(md_content), "markdown")
    content = marker + "\n\n" + body + "\n\n" + marker

    try:
        import markdown

        rendered_content = markdown.markdown(content)
    except ImportError:
        # Keep Markdown output usable without making the optional renderer a hard dependency.
        rendered_content = "<pre><code>" + escape(content) + "</code></pre>"
    validate_rendered_text(rendered_content, "Markdown")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
