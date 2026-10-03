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
    查找规则：base_dir / discipline / *.csv（优先取第一个 CSV）。
    返回映射 {source_term: target_term}。
    """
    discipline_dir = base_dir / discipline
    if not discipline_dir.exists():
        raise FileNotFoundError(f"学科目录不存在: {discipline_dir}")
    
    csv_files = list(discipline_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"在 {discipline_dir} 下未找到任何 CSV 术语文件")
    
    # 取第一个 CSV，若多个则合并（可优化为合并）
    csv_path = csv_files[0]
    rows = read_csv_with_encoding(csv_path)
    
    # 质量门禁：结构验证
    is_valid, msg = validate_glossary_structure(rows)
    if not is_valid:
        raise ValueError(f"术语表结构异常: {msg}")
    
    # 构建映射，自动去重（保留最后一个值）
    glossary_map: Dict[str, str] = {}
    for row in rows:
        # 智能查找列名
        source_key = None
        target_key = None
        for col in row.keys():
            col_lower = col.strip().lower()
            if "source" in col_lower or "外文" in col_lower or "英文" in col_lower:
                source_key = col
            if "target" in col_lower or "中文" in col_lower or "翻译" in col_lower:
                target_key = col
        if source_key is None or target_key is None:
            # 跳过无法识别列的行（但保留已有映射）
            continue
        source = row[source_key].strip()
        target = row[target_key].strip()
        if source and target:  # 过滤空值
            glossary_map[source] = target
    
    if not glossary_map:
        raise ValueError(f"术语表加载成功但映射为空，请检查 CSV 数据: {csv_path}")
    
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