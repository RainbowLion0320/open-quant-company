"""
Factor DSL 解析器 — 将 LLM 公式翻译为可计算的 Factor 对象

支持的语法:
  数值: close_t, close_t-5, volume_t, high_t, low_t, open_t
  函数: MA(close,20), Std(close,20), Delta(close,5)
  运算符: + - * / ( )
  比较: > < >= <=
"""
import re
import pandas as pd
import numpy as np


def compute_formula(formula: str, df: pd.DataFrame, idx: int) -> float:
    """
    计算 LLM 因子公式在给定数据点的值。
    
    Args:
        formula: LLM 输出的公式 (close_t, MA(close,20) 等)
        df: OHLCV DataFrame (DatetimeIndex, 含 close/open/high/low/volume 列)
        idx: 时间索引位置
    
    Returns:
        计算出的因子值
    """
    expr = _translate_formula(formula)
    return _eval_expr(expr, df, idx)


def _translate_formula(formula: str) -> str:
    """将 LLM 公式翻译为可 eval 的 Python 表达式"""
    # 1. 函数调用: MA(close,20) → __ma(close,20)
    formula = re.sub(r'MA\(\s*(\w+)\s*,\s*(\d+)\s*\)', r'__ma("\1",\2)', formula)
    formula = re.sub(r'Std\(\s*(\w+)\s*,\s*(\d+)\s*\)', r'__std("\1",\2)', formula)
    formula = re.sub(r'Delta\(\s*(\w+)\s*,\s*(\d+)\s*\)', r'__delta("\1",\2)', formula)
    
    # 2. 变量: close_t → __ref("close",0), close_t-5 → __ref("close",-5)
    for col in ["close", "open", "high", "low", "volume"]:
        formula = re.sub(rf'\b{col}_t\b', f'__ref("{col}",0)', formula)
        formula = re.sub(rf'\b{col}_t-(\d+)\b', rf'__ref("{col}",-\1)', formula)
        formula = re.sub(rf'\b{col}_t_(\d+)\b', rf'__ref("{col}",-\1)', formula)
    
    return formula


def _eval_expr(expr: str, df: pd.DataFrame, idx: int) -> float:
    """求值已翻译的表达式"""
    def __ref(col: str, offset: int):
        i = idx + offset
        if i < 0 or i >= len(df):
            return 0.0
        v = df[col].iloc[i]
        return float(v) if not pd.isna(v) else 0.0
    
    def __ma(col: str, window: int):
        s = df[col].iloc[max(0, idx - window + 1):idx + 1]
        return float(s.mean()) if len(s) > 0 else 0.0
    
    def __std(col: str, window: int):
        s = df[col].iloc[max(0, idx - window + 1):idx + 1]
        return float(s.std()) if len(s) > 1 else 0.0
    
    def __delta(col: str, window: int):
        cur = __ref(col, 0)
        prev = __ref(col, -window)
        return cur - prev
    
    ns = {
        "__ref": __ref, "__ma": __ma, "__std": __std, "__delta": __delta,
        "abs": abs, "max": max, "min": min,
    }
    
    try:
        return float(eval(expr, {"__builtins__": {}}, ns))
    except Exception:
        return 0.0


def evaluate_factor(name: str, formula: str, features_df: pd.DataFrame) -> dict:
    """计算因子 IC — 使用 DSL 解析器动态计算因子值"""
    from data.fetcher import get_stock_daily
    
    valid = features_df.dropna(subset=["ret_fwd_20d"])
    if len(valid) < 100:
        return {"ic": 0, "icir": 0, "valid": False}
    
    syms = valid["symbol"].unique()[:80]  # 80只采样
    factor_vals = []
    targets = []
    
    for sym in syms:
        try:
            df = get_stock_daily(sym)
            if df is None or len(df) < 60:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            idx = len(df) - 1
            
            val = compute_formula(formula, df, idx)
            if not np.isnan(val) and abs(val) < 1e10:
                sym_data = valid[valid["symbol"] == sym]
                if len(sym_data) > 0:
                    factor_vals.append(val)
                    targets.append(sym_data["ret_fwd_20d"].iloc[0])
        except Exception:
            pass
    
    if len(factor_vals) < 10:
        return {"ic": 0, "icir": 0, "valid": False}
    
    from scipy.stats import spearmanr
    y = pd.Series(targets)
    fv = pd.Series(factor_vals)
    ic, _ = spearmanr(fv, y)
    ic = ic if not np.isnan(ic) else 0.0
    return {"ic": ic, "icir": 0, "valid": True}
