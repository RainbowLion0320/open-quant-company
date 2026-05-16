#!/usr/bin/env python3
"""预缓存全部财务数据 → 后续回测/锦标赛纯本地计算, 零网络依赖"""
import os, sys, time, socket
socket.setdefaulttimeout(30)
for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'
sys.path.insert(0, '/Users/fushao/quant-agent')

import pandas as pd
from pathlib import Path
from data.symbols import CIRCLE_STOCKS
from data.financials import get_financial_summary

# 从特征文件收集实际需要的 symbol
FEATURES_DIR = Path('/Users/fushao/quant-agent/data/store/features')
symbols_set = set()
for pq in sorted(FEATURES_DIR.glob('*.parquet')):
    df = pd.read_parquet(pq)
    symbols_set.update(df['symbol'].unique())
symbols = sorted(symbols_set)
print(f"预缓存 {len(symbols)} 只财务数据...")

ok, skip, fail = 0, 0, 0
t0 = time.monotonic()
for i, sym in enumerate(symbols):
    try:
        df = get_financial_summary(sym)
        if df is not None and len(df) > 0:
            ok += 1
        else:
            skip += 1
    except Exception as e:
        fail += 1
        if fail <= 5:
            print(f"  FAIL {sym}: {type(e).__name__}")
    if (i+1) % 500 == 0:
        elapsed = time.monotonic() - t0
        print(f"  {i+1}/{len(symbols)} ok={ok} skip={skip} fail={fail} [{elapsed:.0f}s]")

elapsed = time.monotonic() - t0
print(f"\n完成: ok={ok} skip={skip} fail={fail} [{elapsed:.0f}s]")
# 统计缓存大小
from data.financials import _get_cache_path
cached = sum(1 for s in symbols if os.path.exists(_get_cache_path(s)))
print(f"磁盘缓存: {cached}/{len(symbols)} 文件")
