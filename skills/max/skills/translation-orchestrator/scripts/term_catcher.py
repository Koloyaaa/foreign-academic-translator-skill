#!/usr/bin/env python3
"""
术语快速匹配器：不依赖CSV结构，纯文本正则搜索（相当于Ctrl+F），极大节省Token。
"""
import sys
import re
import csv
from pathlib import Path

SOURCE_COLUMNS = ("英文名稱", "英文名称", "外文", "原文", "source_term", "source", "term")
TARGET_COLUMNS = ("中文名稱", "中文名称", "中文", "譯名", "译名", "target_term", "target", "翻译", "translation")


def _find_column(columns, candidates) -> str | None:
    """按精确列名优先、包含匹配其次的顺序定位列。"""
    normalized = [(col, col.strip().lower()) for col in columns]
    for candidate in candidates:
        for col, name in normalized:
            if name == candidate.lower():
                return col
    for candidate in candidates:
        for col, name in normalized:
            if candidate.lower() in name:
                return col
    return None


def grep_term_in_csv(csv_path: Path, search_term: str) -> str | None:
    """
    在CSV文件中进行纯文本搜索（不区分大小写）。
    若找到，返回第一个匹配行中译名列的值；没有可识别的译名列时返回 None。
    """
    if not csv_path.exists():
        return None

    # 读取全文做一次包含匹配，避免逐行扫描无关词表。
    with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        content = f.read()
    if not re.search(rf"(?i){re.escape(search_term)}", content):
        return None

    with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        source_col = _find_column(columns, SOURCE_COLUMNS)
        target_col = _find_column(columns, TARGET_COLUMNS)
        if target_col is None:
            return None

        needle = search_term.casefold().strip()
        rows = list(reader)

        def source_value(row) -> str:
            if source_col is not None:
                return (row.get(source_col) or "").strip()
            return " ".join(value or "" for value in row.values()).strip()

        # 先找完全匹配，再退到包含匹配，避免 "tractor" 命中 "walking tractor"。
        for exact in (True, False):
            for row in rows:
                candidate = source_value(row)
                if not candidate:
                    continue
                matched = candidate.casefold() == needle if exact else needle in candidate.casefold()
                if matched:
                    target = (row.get(target_col) or "").strip()
                    if target:
                        return target
    return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python term_catcher.py <csv_path> <search_term>")
        sys.exit(1)
    
    result = grep_term_in_csv(Path(sys.argv[1]), sys.argv[2])
    if result:
        print(result)
    else:
        print("NOT_FOUND")