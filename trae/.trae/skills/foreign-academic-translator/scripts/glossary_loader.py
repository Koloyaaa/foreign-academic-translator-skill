#!/usr/bin/env python3
"""
术语库加载器：根据学科名称加载对应的 CSV 术语表，输出 JSON 格式映射。
质量门禁：检查 CSV 结构、去重、过滤无效条目。
"""
import sys
import json
from pathlib import Path
from typing import Dict, List
import argparse

from utils import read_csv_with_encoding, validate_glossary_structure, safe_json_dumps

def load_glossary(base_dir: Path, discipline: str) -> Dict[str, str]:
    """
    加载指定学科的术语表。
    按文件名排序并合并 base_dir / discipline / 下的 CSV。
    冲突时由文件名排序靠前的词表优先，并将冲突报告到 stderr。
    返回映射 {source_term: target_term}。
    """
    discipline_dir = base_dir / discipline
    if not discipline_dir.exists():
        raise FileNotFoundError(f"学科目录不存在: {discipline_dir}")
    
    csv_files = sorted(discipline_dir.glob("*.csv"), key=lambda path: (path.name.casefold(), path.name))
    if not csv_files:
        raise FileNotFoundError(f"在 {discipline_dir} 下未找到任何 CSV 术语文件")
    
    glossary_map: Dict[str, str] = {}
    conflicts = []
    for csv_path in csv_files:
        rows = read_csv_with_encoding(csv_path)

        # 每个词表都单独验证，避免合并时掩盖格式错误。
        is_valid, msg = validate_glossary_structure(rows)
        if not is_valid:
            raise ValueError(f"术语表结构异常 ({csv_path.name}): {msg}")

        columns = list(rows[0].keys())
        has_source = any("source" in col.strip().lower() or "外文" in col or "英文" in col for col in columns)
        has_target = any("target" in col.strip().lower() or "中文" in col or "翻译" in col for col in columns)
        if not has_source or not has_target:
            raise ValueError(f"术语表结构异常 ({csv_path.name}): 缺少外文术语列或中文译名列")

        for row in rows:
            source_key = None
            target_key = None
            for col in row.keys():
                col_lower = col.strip().lower()
                if source_key is None and ("source" in col_lower or "外文" in col_lower or "英文" in col_lower):
                    source_key = col
                if target_key is None and ("target" in col_lower or "中文" in col_lower or "翻译" in col_lower):
                    target_key = col
            if source_key is None or target_key is None:
                continue
            source = (row.get(source_key) or "").strip()
            target = (row.get(target_key) or "").strip()
            if not source or not target:
                continue
            existing = glossary_map.get(source)
            if existing is None:
                glossary_map[source] = target
            elif existing != target:
                conflicts.append((source, existing, target, csv_path.name))
    
    if not glossary_map:
        raise ValueError(f"术语表加载成功但映射为空，请检查 CSV 数据: {discipline_dir}")

    if conflicts:
        print(
            f"[WARN] {len(conflicts)} 个术语存在不同译名；按文件名排序优先采用较早词表中的译名。",
            file=sys.stderr,
        )
        for source, kept, ignored, filename in conflicts[:10]:
            print(
                f"  {source!r}: 保留 {kept!r}；忽略 {filename} 中的 {ignored!r}",
                file=sys.stderr,
            )
        if len(conflicts) > 10:
            print(f"  其余 {len(conflicts) - 10} 个冲突未逐项列出。", file=sys.stderr)
    
    return glossary_map

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="加载术语库并输出 JSON")
    parser.add_argument("--base_dir", type=str, default="./glossaries", help="术语库根目录")
    parser.add_argument("--discipline", type=str, required=True, help="学科名称 (如 Engineering)")
    args = parser.parse_args()
    
    try:
        result = load_glossary(Path(args.base_dir), args.discipline)
        # 输出 JSON 供 SKILL.md 注入
        print(safe_json_dumps(result))
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
