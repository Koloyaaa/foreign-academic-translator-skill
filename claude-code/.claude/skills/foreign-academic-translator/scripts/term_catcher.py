#!/usr/bin/env python3
"""
术语快速匹配器：不依赖CSV结构，纯文本正则搜索（相当于Ctrl+F），极大节省Token。
"""
import sys
import re
import csv
from pathlib import Path

def grep_term_in_csv(csv_path: Path, search_term: str) -> str | None:
    """
    在CSV文件中进行纯文本搜索（不区分大小写）。
    若找到，返回第一个匹配行中的译名（启发式提取）。
    """
    if not csv_path.exists():
        return None
    
    # 读取全文进行正则搜索（效率极高）
    with open(csv_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        content = f.read()
    
    # 先尝试精准匹配（单词边界）
    pattern = re.compile(rf'(?i)\b{re.escape(search_term)}\b')
    if not pattern.search(content):
        # 尝试模糊包含匹配
        pattern = re.compile(rf'(?i){re.escape(search_term)}')
        if not pattern.search(content):
            return None
    
    # 如果找到，重新逐行读取，找到具体行并提取可能的中文翻译
    # 此时才消耗少量IO读取行，但未调用AI，成本极低
    with open(csv_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        for row in reader:
            for col, value in row.items():
                if search_term.lower() in value.lower():
                    # 寻找该行中可能的中文列（启发式）
                    for target_col in ['中文', 'target_term', '译名', '翻译']:
                        if target_col in row and row[target_col].strip():
                            return row[target_col].strip()
                    # 如果没有标准列，返回该行的第一个非空值（可能是译名）
                    for val in row.values():
                        if val.strip() and val != value:
                            return val.strip()
    return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python term_matcher.py <csv_path> <search_term>")
        sys.exit(1)
    
    result = grep_term_in_csv(Path(sys.argv[1]), sys.argv[2])
    if result:
        print(result)
    else:
        print("NOT_FOUND")