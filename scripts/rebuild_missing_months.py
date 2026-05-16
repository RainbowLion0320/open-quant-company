#!/usr/bin/env python3
"""精确补建缺失的特征月份 — 只拉缓存，建缺失月"""
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
from data.symbols import CIRCLE_STOCKS
from data.fetcher import get_stock_daily
from data.financials import get_financial_summary
from signals.expression import alpha_factors
from data.feature_store import FEATURES_DIR, enrich_from_registry

MISSING = ['2018-01', '2018-03', '2018-04', '2018-05', '2018-07']
_skip_prefixes = ('92', '83', '87', '43')
symbols_raw = list(CIRCLE_STOCKS)[:5517]
symbols = [s for s in symbols_raw if not any(s.startswith(p) for p in _skip_prefixes)]
print(f"补建 {len(MISSING)} 个月, {len(symbols)} 只标的")

# Phase 1: 价格 (全部缓存)
print("\n[1] 价格...")
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
    if (i+1) % 1000 == 0:
        print(f"  {i+1}/{len(symbols)} ({len(price_cache)} valid)")
print(f"  有效: {len(price_cache)}")

# Phase 2: 财务
print("\n[2] 财务...")
fin_cache = {}
for i, sym in enumerate(price_cache):
    try:
        fin_df = get_financial_summary(sym)
        if fin_df is not None and len(fin_df) > 0:
            fin_cache[sym] = fin_df
    except Exception:
        pass
    if (i+1) % 1000 == 0:
        print(f"  {i+1}/{len(price_cache)} ({len(fin_cache)} valid)")
print(f"  财务有效: {len(fin_cache)}")

# Phase 3: PE/PB
daily_cache = {}
print("\n[3] PE/PB (Tushare)...")
try:
    import tushare as _ts
    from data.tushare_utils import get_tushare_token
    token = get_tushare_token()
    ts_api = _ts.pro_api(token) if token else None
    if ts_api:
        for i, sym in enumerate(list(price_cache.keys())):
            try:
                suffix = ".SH" if sym.startswith("6") else ".SZ"
                df = ts_api.daily_basic(
                    ts_code=f"{sym}{suffix}",
                    start_date="20180101", end_date="20260501",
                    fields="trade_date,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv,circ_mv"
                )
                if df is not None and len(df) > 0:
                    df["trade_date"] = pd.to_datetime(df["trade_date"])
                    df = df.set_index("trade_date").sort_index()
                    daily_cache[sym] = df
                time.sleep(0.3)
            except Exception:
                pass
            if (i+1) % 500 == 0:
                print(f"  {i+1}/{len(price_cache)} ({len(daily_cache)} valid)")
    print(f"  估值有效: {len(daily_cache)}")
except Exception as e:
    print(f"  Tushare不可用: {e}")

# Helper functions
def _to_float(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace("%", "").replace(",", "").replace("万亿", "e12").replace("亿", "e8").replace("万", "e4")
        try: return float(val)
        except ValueError: return 0.0
    return 0.0

def _compute_fundamental_factors(fin_df, as_of):
    factors = {}
    try:
        rc = "报告期" if "报告期" in fin_df.columns else "end_date"
        fin_df[rc] = pd.to_datetime(fin_df[rc])
        past = fin_df[fin_df[rc] <= as_of].sort_values(rc)
        if len(past) == 0: return factors
        latest = past.iloc[-1]
        factors["fund_roe"] = _to_float(latest.get("净资产收益率") or latest.get("roe"))
        factors["fund_gross_margin"] = _to_float(latest.get("销售毛利率") or latest.get("gross_margin"))
        factors["fund_net_margin"] = _to_float(latest.get("销售净利率") or latest.get("net_margin"))
        de = latest.get("debt_equity_ratio")
        if de is None and len(past) >= 2:
            prev = past.iloc[-2]
            de = float(prev.get("total_liab",0) or 0) / max(1, float(prev.get("total_equity",0) or 1))
        factors["fund_de_ratio"] = _to_float(de)
        factors["fund_net_profit"] = _to_float(latest.get("净利润") or latest.get("net_profit"))
        roes = [_to_float(r.get("净资产收益率") or r.get("roe")) for _,r in past.tail(5).iterrows() if r.get("净资产收益率") or r.get("roe")]
        factors["fund_roe_5y_avg"] = sum(roes)/len(roes) if roes else 0
        if len(past) >= 5:
            factors["fund_gm_trend"] = factors["fund_gross_margin"] - _to_float(past.iloc[-5].get("销售毛利率") or past.iloc[-5].get("gross_margin") or 0)
    except Exception: pass
    return factors

def _compute_valuation_factors(daily_df, as_of, price_df, idx):
    factors = {}
    try:
        past = daily_df[daily_df.index <= as_of]
        if len(past) == 0: return factors
        latest = past.iloc[-1]
        for k, c in [("val_pe","pe"),("val_pe_ttm","pe_ttm"),("val_pb","pb"),("val_ps","ps"),("val_dv_ratio","dv_ratio")]:
            factors[k] = _to_float(latest.get(c))
        if len(past) > 250:
            pe_hist = past["pe_ttm"].dropna().tail(500)
            if len(pe_hist) > 100:
                cur = _to_float(latest.get("pe_ttm"))
                if cur > 0: factors["val_pe_percentile"] = (pe_hist < cur).mean()
        factors["val_total_mv"] = _to_float(latest.get("total_mv"))
    except Exception: pass
    return factors

# Phase 4: 构建缺失月份
print(f"\n[4] 构建 {len(MISSING)} 个缺失月...")
factors = alpha_factors()

for month in MISSING:
    month_dt = pd.Timestamp(month + "-01")
    month_end = month_dt + pd.offsets.MonthEnd(0)
    rows = []
    for sym, df in price_cache.items():
        df_pit = df[df.index <= month_end]
        if len(df_pit) < 60:
            continue
        idx = len(df_pit) - 1
        row = {"symbol": sym, "month": month}
        # 价量因子
        for fname, factor in factors.items():
            val = factor.compute(df_pit, idx)
            row[fname] = val if not (isinstance(val, float) and np.isnan(val)) else None
        # 基本面
        fin_df = fin_cache.get(sym)
        if fin_df is not None:
            row.update(_compute_fundamental_factors(fin_df, month_end))
        # PE/PB
        daily_df = daily_cache.get(sym)
        if daily_df is not None:
            row.update(_compute_valuation_factors(daily_df, month_end, df_pit, idx))
        # 前向标签
        full_idx = df.index.get_indexer([df_pit.index[-1]])[0]
        fwd_idx = full_idx + 20
        if full_idx >= 0 and fwd_idx < len(df):
            cur = df.iloc[full_idx]["close"]
            fwd = df.iloc[fwd_idx]["close"]
            row["ret_fwd_20d"] = (fwd / cur - 1) if cur > 0 else None
        rows.append(row)

    if rows:
        result_df = pd.DataFrame(rows)
        from data.cleaner import DataCleaner
        cleaner = DataCleaner()
        result_df, _ = cleaner.clean_features(result_df)
        result_df = enrich_from_registry(result_df, month, list(price_cache.keys()))
        result_df.to_parquet(FEATURES_DIR / f"{month}.parquet", index=False)
    print(f"  {month}: {len(rows)} stocks")

print("\n✅ 补建完成")
