#!/usr/bin/env python3
"""
格式构建器：将大模型输出的 Markdown 译文转换为 HTML / DOCX / Markdown。
质量门禁：输入非空检查；若某格式生成失败，记录错误但尽量不阻断其他格式。
"""
import sys
import argparse
import json
from functools import partial
from pathlib import Path
from typing import Dict, List

# 各格式构建器统一从 builders 包导入
from builders import build_html, build_docx, build_markdown


def build_all(
    md_content: str,
    output_dir: Path,
    formats: List[str],
    base_name: str = "translated_doc",
    show_concept_table: bool = True,
) -> Dict[str, Path]:
    """根据 formats 列表生成多格式文档。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    # 质量门禁：输入非空
    if not md_content or len(md_content.strip()) < 10:
        raise ValueError("Markdown 内容为空或过短，无法构建文档")

    # 格式名 -> 可调用构建器 的映射；html 需透传 show_concept_table
    format_map = {
        "html": partial(build_html, show_concept_table=show_concept_table),
        "docx": build_docx,
        "md": build_markdown,
    }

    for fmt in formats:
        fmt = fmt.lower().strip()
        builder = format_map.get(fmt)
        if builder is None:
            print(f"[WARN] 忽略不支持的格式: {fmt}", file=sys.stderr)
            continue
        out_path = output_dir / f"{base_name}.{fmt}"
        try:
            results[fmt] = builder(md_content, out_path)
        except Exception as e:
            print(f"[ERROR] 生成 {fmt} 失败: {e}", file=sys.stderr)
            # 不中断其他格式

    if not results:
        raise RuntimeError("所有格式生成均失败，请检查依赖库和源内容")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 Markdown 译文转换为多种文档格式")
    parser.add_argument("--input", type=str, required=True, help="输入的 Markdown 文件路径")
    parser.add_argument("--output_dir", type=str, default="./output/docs", help="输出目录")
    parser.add_argument("--formats", type=str, default="html,docx", help="逗号分隔的格式列表")
    parser.add_argument("--base_name", type=str, default="translated_doc", help="输出文件名前缀")
    args = parser.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            md_content = f.read()
        formats = [f.strip() for f in args.formats.split(",") if f.strip()]
        results = build_all(md_content, Path(args.output_dir), formats, args.base_name)
        print(json.dumps({k: str(v) for k, v in results.items()}, ensure_ascii=False))
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
