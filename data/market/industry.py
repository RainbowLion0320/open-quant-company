"""
加载 Tushare 行业分类数据
"""
import json
from pathlib import Path
from typing import Dict

_CACHE = None

def _load() -> dict:
    global _CACHE
    if _CACHE is None:
        path = Path(__file__).resolve().parents[1] / "reference" / "tushare_industry.json"
        with open(path, encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE

def get_sw1(symbol: str) -> str:
    """获取申万一级行业"""
    data = _load()
    return data["sw1"].get(symbol, "待分类")

def get_sw2(symbol: str) -> str:
    """获取申万二级行业"""
    data = _load()
    return data["sw2"].get(symbol, "待分类")

def get_name(symbol: str) -> str:
    """获取公司名称"""
    data = _load()
    return data["name"].get(symbol, symbol)

def get_all_sw2() -> Dict[str, str]:
    """获取全部 符号→二级行业 映射"""
    data = _load()
    return data["sw2"].copy()
