#!/usr/bin/env python3
"""批量构建 PIT 特征 → data/store/features/YYYY-MM.parquet"""
import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd
import numpy as np

from data.symbols import CIRCLE_STOCKS, SYMBOL_NAME
from data.fetcher import get_stock_daily
from signals.expression import alpha_factors
from data.feature_store import FEATURES_DIR, FeatureStoreBuilder

# ══════════════════════════════════════════════════════════
N_STOCKS = 200          # 股票数
START = "2018-01"       # 起始月
END = "2026-04"         # 结束月
# ══════════════════════════════════════════════════════════

print(f"批量构建 PIT 特征: {N_STOCKS}只, {START}→{END}")
print(f"输出: {FEATURES_DIR}/")

factors = alpha_factors()
symbols = list(CIRCLE_STOCKS)[:N_STOCKS]

# 预加载价格数据
print(f"\n[1/3] 加载价格数据 ({N_STOCKS}只)...")
price_cache = {}
for i, sym in enumerate(symbols):
    try:
        df = get_stock_daily(sym)
        if df is not None and len(df) >= 120:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            price_cache[sym] = df
    except Exception:
        pass
    if (i+1) % 50 == 0:
        print(f"  {i+1}/{N_STOCKS} ({len(price_cache)} valid)")

print(f"  有效股票: {len(price_cache)}")

# 逐月构建
months = pd.date_range(START, END, freq="MS")
print(f"\n[2/3] 构建特征 ({len(months)}个月)...")

for mi, month_dt in enumerate(months):
    month = month_dt.strftime("%Y-%m")
    pq_path = FEATURES_DIR / f"{month}.parquet"
    if pq_path.exists():
        continue

    month_end = month_dt + pd.offsets.MonthEnd(0)
    rows = []
    for sym, df in price_cache.items():
        df_pit = df[df.index <= month_end]
        if len(df_pit) < 60:
            continue
        idx = len(df_pit) - 1
        row = {"symbol": sym, "month": month}
        for fname, factor in factors.items():
            val = factor.compute(df_pit, idx)
            row[fname] = val if not (isinstance(val, float) and np.isnan(val)) else None

        # 前向收益率标签 (仅训练用)
        fut = df[df.index <= month_end + pd.Timedelta(days=35)]
        if len(fut) > idx:
            cur = df.iloc[idx]["close"]
            fwd = fut.iloc[-1]["close"]
            row["ret_fwd_20d"] = (fwd / cur - 1) if cur > 0 else None
        rows.append(row)

    if rows:
        pd.DataFrame(rows).to_parquet(pq_path, index=False)
        print(f"  {month}: {len(rows)} stocks")
    else:
        print(f"  {month}: 0 stocks")

# 统计
pq_files = sorted(FEATURES_DIR.glob("*.parquet"))
stats = []
for pq in pq_files:
    df = pd.read_parquet(pq)
    stats.append({"month": pq.stem, "stocks": len(df)})

print(f"\n[3/3] 完成: {len(pq_files)} 个月, {sum(s['stocks'] for s in stats)} 总行")
print("✅ 特征构建完成")
