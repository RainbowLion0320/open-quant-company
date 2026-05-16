#!/usr/bin/env python3
"""补增 PE/PB 估值数据到已存在的特征文件"""
import os, sys, time, socket
socket.setdefaulttimeout(30)
for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'
sys.path.insert(0, '/Users/fushao/quant-agent')

import pandas as pd
import numpy as np
from pathlib import Path
from data.tushare_utils import get_tushare_token
import tushare as ts

FEATURES_DIR = Path('/Users/fushao/quant-agent/data/store/features')
token = get_tushare_token()
api = ts.pro_api(token)
print(f"Tushare token: {'OK' if api else 'FAIL'}")

# Step 1: 先拉取所有股票的 PE/PB (一次性)
print("\n[1] 拉取全量 PE/PB...")
daily_cache = {}
symbols_needed = set()

# 从特征文件收集 symbol 列表
for pq in sorted(FEATURES_DIR.glob('*.parquet')):
    try:
        df = pd.read_parquet(pq)
        symbols_needed.update(df['symbol'].unique())
    except Exception:
        pass

symbols_list = list(symbols_needed)
print(f"  {len(symbols_list)} 只标的需要PE/PB")

for i, sym in enumerate(symbols_list):
    try:
        suffix = ".SH" if sym.startswith("6") else ".SZ"
        df = api.daily_basic(
            ts_code=f"{sym}{suffix}",
            start_date="20180101", end_date="20260501",
            fields="trade_date,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv,circ_mv"
        )
        if df is not None and len(df) > 0:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df = df.set_index("trade_date").sort_index()
            daily_cache[sym] = df
    except Exception:
        pass
    if (i+1) % 500 == 0:
        print(f"  {i+1}/{len(symbols_list)} ({len(daily_cache)} valid)")
    time.sleep(0.3)
print(f"  估值有效: {len(daily_cache)}")

# Step 2: 辅助函数
def _to_float(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace("%", "").replace(",", "").replace("万亿", "e12").replace("亿", "e8").replace("万", "e4")
        try: return float(val)
        except ValueError: return np.nan
    return np.nan

def compute_valuation_factors(daily_df, as_of):
    factors = {}
    try:
        past = daily_df[daily_df.index <= as_of]
        if len(past) == 0: return factors
        latest = past.iloc[-1]
        factors["val_pe"] = _to_float(latest.get("pe"))
        factors["val_pe_ttm"] = _to_float(latest.get("pe_ttm"))
        factors["val_pb"] = _to_float(latest.get("pb"))
        factors["val_ps"] = _to_float(latest.get("ps"))
        factors["val_dv_ratio"] = _to_float(latest.get("dv_ratio"))
        if len(past) > 250:
            pe_hist = past["pe_ttm"].dropna().tail(500)
            if len(pe_hist) > 100:
                cur = _to_float(latest.get("pe_ttm"))
                if not np.isnan(cur) and cur > 0:
                    factors["val_pe_percentile"] = (pe_hist < cur).mean()
        factors["val_total_mv"] = _to_float(latest.get("total_mv"))
        factors["val_circ_mv"] = _to_float(latest.get("circ_mv"))
    except Exception:
        pass
    return factors

# Step 3: 逐月补增 PE/PB
print("\n[2] 补增 PE/PB 到特征文件...")
for pq in sorted(FEATURES_DIR.glob('*.parquet')):
    try:
        df = pd.read_parquet(pq)
        month_str = pq.stem
        
        # 检查是否已有估值数据
        if 'val_pe' in df.columns and df['val_pe'].notna().sum() > 100:
            print(f"  {month_str}: skip (already has {df['val_pe'].notna().sum()} val_pe)")
            continue
        
        month_dt = pd.Timestamp(month_str + "-01")
        month_end = month_dt + pd.offsets.MonthEnd(0)
        
        val_data = {}
        for sym in df['symbol'].unique():
            daily_df = daily_cache.get(sym)
            if daily_df is not None:
                factors = compute_valuation_factors(daily_df, month_end)
                if factors:
                    val_data[sym] = factors
        
        # 添加到 DataFrame
        for col in ['val_pe', 'val_pe_ttm', 'val_pb', 'val_ps', 'val_dv_ratio', 'val_pe_percentile', 'val_total_mv', 'val_circ_mv']:
            df[col] = df['symbol'].map(lambda s: val_data.get(s, {}).get(col))
        
        df.to_parquet(pq, index=False)
        val_ok = df['val_pe'].notna().sum()
        print(f"  {month_str}: {len(df)} stocks, val_pe={val_ok} ({100*val_ok//len(df)}%)")
    except Exception as e:
        print(f"  {month_str}: ERROR {e}")

print("\n✅ PE/PB 补增完成")
