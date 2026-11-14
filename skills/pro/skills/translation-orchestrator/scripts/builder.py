#!/usr/bin/env python3
"""
格式构建器：将大模型输出的 Markdown 译文转换为 HTML / DOCX / Markdown。
质量门禁：输入非空检查，并要求每种请求格式都生成非空成品。会尝试全部格式，任何一种失败都会返回明确错误。
"""
import sys
import argparse
import json
import os
import re
import tempfile
from functools import partial
from pathlib import Path
from typing import Dict, List

# 各格式构建器统一从 builders 包导入
from builders import build_html, build_docx, build_markdown


_PDF_LAYOUT_MARKER_RE = re.compile(
    r"(?m)^[ \t]*<!--\s*PDF_(?:PAGE|BLOCK):[^\r\n]*?-->[ \t]*(?:\r?\n|$)"
)


class RequestedFormatBuildError(RuntimeError):
    """Raised when one or more requested formats did not produce an artifact."""

    def __init__(self, failures: Dict[str, str], results: Dict[str, Path]):
        self.failures = failures
        self.results = results
        summary = "; ".join(f"{fmt}: {message}" for fmt, message in failures.items())
        super().__init__(f"Requested format build failed ({summary})")


def build_all(
    md_content: str,
    output_dir: Path,
    formats: List[str],
    base_name: str = "translated_doc",
    show_concept_table: bool = True,
    layout: str = "translation_only",
    require_interactive_quiz: bool = False,
) -> Dict[str, Path]:
    """根据 formats 列表生成多格式文档。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: Dict[str, Path] = {}
    failures: Dict[str, str] = {}
    requested_formats = list(dict.fromkeys(fmt.lower().strip() for fmt in formats if fmt and fmt.strip()))
    if not requested_formats:
        raise ValueError("At least one output format must be requested")
    # 提取器写入的页码/坐标只用于定位 PDF 图片，不应出现在最终成品中。
    md_content = _PDF_LAYOUT_MARKER_RE.sub("", md_content)

    # 质量门禁：输入非空
    if not md_content or len(md_content.strip()) < 10:
        raise ValueError("Markdown 内容为空或过短，无法构建文档")
    require_interactive_quiz = bool(require_interactive_quiz and "html" in {fmt.lower().strip() for fmt in formats})

    # 格式名 -> 可调用构建器 的映射；html 需透传 show_concept_table
    format_map = {
        "html": partial(
            build_html,
            show_concept_table=show_concept_table,
            layout=layout,
            require_interactive_quiz=require_interactive_quiz,
        ),
        "docx": build_docx,
        "md": build_markdown,
    }

    for fmt in requested_formats:
        builder = format_map.get(fmt)
        if builder is None:
            failures[fmt] = "unsupported format"
            print(f"[ERROR] 不支持的格式: {fmt}", file=sys.stderr)
            continue
        out_path = output_dir / f"{base_name}.{fmt}"
        temporary_path: Path | None = None
        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{base_name}.", suffix=".building", dir=output_dir
            )
            os.close(file_descriptor)
            temporary_path = Path(temporary_name)
            if fmt == "html":
                built_path = Path(builder(md_content, temporary_path, final_output_path=out_path))
            else:
                built_path = Path(builder(md_content, temporary_path))
            if built_path.resolve() != temporary_path.resolve():
                raise RuntimeError(f"builder returned an unexpected output path: {built_path}")
            if not built_path.is_file() or built_path.stat().st_size == 0:
                raise RuntimeError("builder did not produce a non-empty output file")
            os.replace(built_path, out_path)
            results[fmt] = out_path
        except Exception as e:
            print(f"[ERROR] 生成 {fmt} 失败: {e}", file=sys.stderr)
            failures[fmt] = str(e)
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    print(f"[WARN] 临时产物清理失败 {temporary_path}: {cleanup_error}", file=sys.stderr)

    if failures:
        raise RequestedFormatBuildError(failures, results)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="将 Markdown 译文转换为多种文档格式")
    parser.add_argument("--input", type=str, required=True, help="输入的 Markdown 文件路径")
    parser.add_argument("--output_dir", type=str, default="./output/docs", help="输出目录")
    parser.add_argument("--formats", type=str, required=True, help="逗号分隔的请求格式列表")
    parser.add_argument("--base_name", type=str, default="translated_doc", help="输出文件名前缀")
    parser.add_argument(
        "--concept-table",
        choices=("true", "false"),
        default="true",
        help="HTML 是否显示概念表并为术语添加跳转链接（true/false）",
    )
    parser.add_argument(
        "--layout",
        choices=("translation_only", "translation_first", "source_first", "concept_highlight"),
        default="translation_only",
        help="HTML 展示布局；用于执行对应的标题质量门禁",
    )
    parser.add_argument(
        "--interactive-quiz-required",
        choices=("true", "false"),
        default="false",
        help="本次是否要求生成并校验完整的 HTML 交互测验",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            md_content = f.read()
        formats = [f.strip() for f in args.formats.split(",") if f.strip()]
        results = build_all(
            md_content,
            Path(args.output_dir),
            formats,
            args.base_name,
            show_concept_table=args.concept_table == "true",
            layout=args.layout,
            require_interactive_quiz=args.interactive_quiz_required == "true",
        )
        print(json.dumps({k: str(v) for k, v in results.items()}, ensure_ascii=False))
    except RequestedFormatBuildError as e:
        print(
            json.dumps(
                {
                    "results": {key: str(value) for key, value in e.results.items()},
                    "failures": e.failures,
                },
                ensure_ascii=False,
            )
        )
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
