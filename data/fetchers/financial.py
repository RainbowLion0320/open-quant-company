"""
financial.py — 财务数据拉取 + 本地 parquet 存储

Fetch:  financial_summary (同花顺), fina_indicator (Tushare), valuation (daily_basic)
Read:  消费者永远调 read_*(), 不走 API
"""

from __future__ import annotations

import time
import random
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from data.datahub import get_datahub

HUB = get_datahub()


def _throttle():
    time.sleep(1.5 + random.uniform(0, 1.0))


# ═══════════════════════════════════════
# 财务摘要 (同花顺 AKShare)
# ═══════════════════════════════════════

def fetch_financial_summary(symbol: str) -> Optional[pd.DataFrame]:
    """从 AKShare 拉取同花顺财务摘要，写入 store/stock/financials/{symbol}.parquet"""
    import akshare as ak
    _throttle()
    try:
        df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期")
        if len(df) == 0:
            return None
        # 转换 object 列为 str，避免 parquet 写入报错
        df_write = df.copy()
        for col in df_write.columns:
            if df_write[col].dtype == object:
                df_write[col] = df_write[col].astype(str)
        HUB.write_parquet(df_write, HUB.stock_financial_path(symbol))
        return df_write
    except Exception as e:
        print(f"  [FAIL] financial_summary({symbol}): {e}")
        return None


def read_financial_summary(symbol: str) -> Optional[pd.DataFrame]:
    return HUB.read_parquet(HUB.stock_financial_path(symbol))


# ═══════════════════════════════════════
# 每日估值 PE/PB/PS (Tushare daily_basic)
# ═══════════════════════════════════════

def fetch_valuation(symbol: str) -> Optional[pd.DataFrame]:
    """从 Tushare daily_basic 拉取每日估值，写入 store/stock/valuation/{symbol}.parquet"""
    import requests as _r
    import os as _os
    _throttle()
    try:
        token = _os.environ.get("TUSHARE_TOKEN", "")
        if not token:
            print("  [SKIP] valuation — no TUSHARE_TOKEN")
            return None
        ts_code = f"{symbol}.{'SH' if symbol.startswith('6') else 'SZ'}"
        resp = _r.post("http://api.tushare.pro", json={
            "api_name": "daily_basic",
            "token": token,
            "params": {"ts_code": ts_code, "fields": "ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv,circ_mv,turnover_rate,turnover_rate_f,volume_ratio"},
        }, timeout=30)
        data = resp.json()
        items = data.get("data", {}).get("items", [])
        if not items:
            return None
        df = pd.DataFrame(items, columns=data["data"]["fields"])
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        for c in ["close", "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_ratio", "dv_ttm", "total_mv", "circ_mv", "turnover_rate", "turnover_rate_f", "volume_ratio"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        HUB.write_parquet(df, HUB.stock_valuation_path(symbol))
        return df
    except Exception as e:
        print(f"  [FAIL] valuation({symbol}): {e}")
        return None


def read_valuation(symbol: str) -> Optional[pd.DataFrame]:
    return HUB.read_parquet(HUB.stock_valuation_path(symbol))


# ═══════════════════════════════════════
# 财务指标 (Tushare fina_indicator)
# ═══════════════════════════════════════

def fetch_fina_indicator(symbol: str) -> Optional[pd.DataFrame]:
    """从 Tushare fina_indicator 拉取财务指标，写入 store/stock/fina_indicator/{symbol}.parquet"""
    import requests as _r
    import os as _os
    _throttle()
    try:
        token = _os.environ.get("TUSHARE_TOKEN", "")
        if not token:
            return None
        ts_code = f"{symbol}.{'SH' if symbol.startswith('6') else 'SZ'}"
        resp = _r.post("http://api.tushare.pro", json={
            "api_name": "fina_indicator",
            "token": token,
            "params": {"ts_code": ts_code},
        }, timeout=30)
        data = resp.json()
        items = data.get("data", {}).get("items", [])
        if not items:
            return None
        df = pd.DataFrame(items, columns=data["data"]["fields"])
        HUB.write_parquet(df, HUB.stock_fina_indicator_path(symbol))
        return df
    except Exception as e:
        print(f"  [FAIL] fina_indicator({symbol}): {e}")
        return None


def read_fina_indicator(symbol: str) -> Optional[pd.DataFrame]:
    return HUB.read_parquet(HUB.stock_fina_indicator_path(symbol))


# ═══════════════════════════════════════
# 批量
# ═══════════════════════════════════════

def fetch_all_financials(symbols: Sequence[str]) -> dict:
    results = {}
    for i, sym in enumerate(symbols):
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(symbols)}] {sym} ...")
        results[sym] = fetch_financial_summary(sym)
    return results


def fetch_all_valuations(symbols: Sequence[str]) -> dict:
    results = {}
    for i, sym in enumerate(symbols):
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(symbols)}] {sym} ...")
        results[sym] = fetch_valuation(sym)
    return results
