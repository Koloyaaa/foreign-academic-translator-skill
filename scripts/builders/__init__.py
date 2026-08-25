"""格式构建器模块包：将 Markdown 译文转换为 HTML / DOCX / Markdown。"""

from .html_builder import build_html
from .docx_builder import build_docx
from .md_builder import build_markdown

__all__ = ["build_html", "build_docx", "build_markdown"]
