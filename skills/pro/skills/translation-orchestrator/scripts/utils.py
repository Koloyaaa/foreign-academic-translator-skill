import os
import csv
import json
import chardet
from typing import Dict, List, Optional, Tuple
from pathlib import Path

def detect_encoding(file_path: Path) -> str:
    """检测文件编码，返回标准编码名称。"""
    with open(file_path, "rb") as f:
        raw_data = f.read(10000)  # 读取前10KB用于检测
        result = chardet.detect(raw_data)
        return result.get("encoding", "utf-8") if result else "utf-8"

def read_csv_with_encoding(file_path: Path, encoding: Optional[str] = None) -> List[Dict[str, str]]:
    """读取 CSV 并返回字典列表，自动处理 BOM 和编码。"""
    if not file_path.exists():
        raise FileNotFoundError(f"术语库文件不存在: {file_path}")
    
    if encoding is None:
        encoding = detect_encoding(file_path)
    
    rows = []
    # 尝试 utf-8-sig 处理 BOM
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows
    except UnicodeDecodeError:
        pass
    
    # 回退到检测到的编码
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

def validate_glossary_structure(rows: List[Dict[str, str]]) -> Tuple[bool, str]:
    """
    验证术语表 CSV 是否包含必要列。
    要求至少包含 'source_term'（外文术语）和 'target_term'（中文术语）列。
    """
    if not rows:
        return False, "术语表为空"
    required_cols = {"source_term", "target_term"}
    first_row_keys = set(rows[0].keys())
    # 宽松匹配：允许大小写不同，或列名带有空格
    normalized_keys = {k.strip().lower() for k in first_row_keys}
    if "source_term" not in normalized_keys and "sourceterm" not in normalized_keys:
        # 尝试模糊匹配
        possible_source = [k for k in first_row_keys if "source" in k.lower() or "外文" in k or "英文" in k]
        possible_target = [k for k in first_row_keys if "target" in k.lower() or "中文" in k or "翻译" in k]
        if not possible_source or not possible_target:
            return False, f"CSV 缺少必要的列（source_term/target_term）。当前列: {list(first_row_keys)}"
    return True, "验证通过"

def safe_json_dumps(data, indent=2) -> str:
    """安全的 JSON 序列化，处理非 ASCII 字符。"""
    return json.dumps(data, ensure_ascii=False, indent=indent)