#!/usr/bin/env python3
"""补增 PE/PB 估值数据到已存在的特征文件"""
import os, sys, time, socket
from pathlib import Path
socket.setdefaulttimeout(30)
for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'
ROOT = Path(__file__).resolve().parent.parent

import pandas as pd
import numpy as np
from data.storage.datahub import get_datahub
from data.features.factor_inputs import compute_valuation_factors
from data.features.feature_store import iter_feature_files
from data.ingestion.tushare_utils import get_tushare_token
import tushare as ts

HUB = get_datahub()
token = get_tushare_token()
api = ts.pro_api(token)
print(f"Tushare token: {'OK' if api else 'FAIL'}")

# Step 1: 先拉取所有股票的 PE/PB (一次性)
print("\n[1] 拉取全量 PE/PB...")
daily_cache = {}
symbols_needed = set()

# 从特征文件收集 symbol 列表
for pq in iter_feature_files():
    try:
        df = HUB.read_parquet(pq)
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

# Step 3: 逐月补增 PE/PB
print("\n[2] 补增 PE/PB 到特征文件...")
for pq in iter_feature_files():
    try:
        df = HUB.read_parquet(pq)
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
                factors = compute_valuation_factors(daily_df, month_end, default=np.nan, include_circ_mv=True)
                if factors:
                    val_data[sym] = factors
        
        # 添加到 DataFrame
        for col in ['val_pe', 'val_pe_ttm', 'val_pb', 'val_ps', 'val_dv_ratio', 'val_pe_percentile', 'val_total_mv', 'val_circ_mv']:
            df[col] = df['symbol'].map(lambda s: val_data.get(s, {}).get(col))
        
        HUB.write_parquet(df, pq)
        val_ok = df['val_pe'].notna().sum()
        print(f"  {month_str}: {len(df)} stocks, val_pe={val_ok} ({100*val_ok//len(df)}%)")
    except Exception as e:
        print(f"  {month_str}: ERROR {e}")

print("\n✅ PE/PB 补增完成")
