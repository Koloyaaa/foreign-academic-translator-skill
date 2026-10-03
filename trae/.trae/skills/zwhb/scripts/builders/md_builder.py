"""Markdown 构建器：在内容顶部与底部各插入 WATERMARK 注释后写出文件。"""

from pathlib import Path

from .base import annotate_first_occurrences


def build_markdown(md_content: str, output_path: Path) -> Path:
    """将 Markdown 内容加上水印注释后写盘（术语首次出现自动补原文括号）。"""
    marker = "<!-- WATERMARK -->"
    content = marker + "\n\n" + annotate_first_occurrences(md_content) + "\n\n" + marker

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
