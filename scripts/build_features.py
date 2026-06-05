#!/usr/bin/env python3
"""Build point-in-time monthly features into ``data/store/features``.

The previous version executed the full feature build at import time.  This file
is intentionally import-safe so cron jobs and agent tools can import
``rebuild_recent`` without starting a 5k-stock network workload.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path

socket.setdefaulttimeout(30)

ROOT = Path(__file__).resolve().parent.parent

for key in list(os.environ):
    if key.lower() in ("http_proxy", "https_proxy", "all_proxy"):
        del os.environ[key]
os.environ["no_proxy"] = "*"

import numpy as np
import pandas as pd

from data.datahub import get_datahub
from data.feature_store import FEATURES_DIR, enrich_from_registry, iter_feature_files
from data.price_service import get_stock_prices
from data.price_types import PriceUseCase
from data.symbols import CIRCLE_STOCKS
from signals.expression import alpha_factors


HUB = get_datahub()
DEFAULT_N_STOCKS = int(os.environ.get("QUANT_FEATURE_N_STOCKS", str(len(CIRCLE_STOCKS))))
DEFAULT_START = os.environ.get("QUANT_FEATURE_START", "2018-01")
DEFAULT_END = os.environ.get(
    "QUANT_FEATURE_END",
    (pd.Timestamp.today().to_period("M") - 1).strftime("%Y-%m"),
)
SKIP_PREFIXES = ("92", "83", "87", "43")


def _to_float(val) -> float:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    if isinstance(val, (int, float, np.number)):
        return float(val)
    if isinstance(val, str):
        text = val.replace("%", "").replace(",", "")
        text = text.replace("万亿", "e12").replace("亿", "e8").replace("万", "e4")
        try:
            return float(text)
        except ValueError:
            return 0.0
    return 0.0


def _select_symbols(n_stocks: int) -> list[str]:
    symbols_raw = list(CIRCLE_STOCKS)[:n_stocks]
    symbols = [s for s in symbols_raw if not any(s.startswith(p) for p in SKIP_PREFIXES)]
    skipped = len(symbols_raw) - len(symbols)
    if skipped:
        print(f"  过滤掉 {skipped} 只无效标的 (北交所/新三板/退市板), 剩余 {len(symbols)}")
    return symbols


def _load_price_cache(symbols: list[str]) -> dict[str, pd.DataFrame]:
    print("\n[1/4] 加载价格数据...")
    price_cache: dict[str, pd.DataFrame] = {}
    total = len(symbols)
    for i, sym in enumerate(symbols, 1):
        try:
            df = get_stock_prices(sym, use_case=PriceUseCase.RESEARCH)
            if df is not None and len(df) >= 120:
                df = df.copy()
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                price_cache[sym] = df
        except Exception:
            pass
        if i % 50 == 0:
            print(f"  价格: {i}/{total} ({len(price_cache)} valid)")
    print(f"  价格有效: {len(price_cache)}")
    return price_cache


def _load_financial_cache(symbols: list[str]) -> dict[str, pd.DataFrame]:
    print("\n[2/4] 加载财务数据 (PE/PB/ROE/毛利率/D-E)...")
    from data.financials import get_financial_summary

    fin_cache: dict[str, pd.DataFrame] = {}
    total = len(symbols)
    for i, sym in enumerate(symbols, 1):
        try:
            fin_df = get_financial_summary(sym)
            if fin_df is not None and len(fin_df) > 0:
                fin_cache[sym] = fin_df
        except Exception:
            pass
        if i % 50 == 0:
            print(f"  财务: {i}/{total} ({len(fin_cache)} valid)")
    print(f"  财务有效: {len(fin_cache)}")
    return fin_cache


def _load_daily_basic_cache(symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    print("\n[3/4] 加载日频指标 PE/PB (Tushare daily_basic)...")
    daily_cache: dict[str, pd.DataFrame] = {}
    try:
        import tushare as ts
        from data.tushare_utils import get_tushare_token

        token = get_tushare_token()
        ts_api = ts.pro_api(token) if token else None
        if ts_api is None:
            raise RuntimeError("No Tushare token")

        start_date = pd.Timestamp(start + "-01").strftime("%Y%m%d")
        end_date = (pd.Timestamp(end + "-01") + pd.offsets.MonthEnd(1)).strftime("%Y%m%d")
        total = len(symbols)
        for i, sym in enumerate(symbols, 1):
            try:
                suffix = ".SH" if sym.startswith("6") else ".SZ"
                df = ts_api.daily_basic(
                    ts_code=f"{sym}{suffix}",
                    start_date=start_date,
                    end_date=end_date,
                    fields="trade_date,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv,circ_mv",
                )
                if df is not None and len(df) > 0:
                    df["trade_date"] = pd.to_datetime(df["trade_date"])
                    daily_cache[sym] = df.set_index("trade_date").sort_index()
                time.sleep(0.3)
            except Exception:
                pass
            if i % 20 == 0:
                print(f"  PE/PB {i}/{total} ({len(daily_cache)} valid)")
    except Exception as exc:
        print(f"  Tushare不可用 ({type(exc).__name__}), 跳过PE/PB")
    print(f"  日频估值有效: {len(daily_cache)}")
    return daily_cache


def _compute_fundamental_factors(fin_df: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    result = {}
    try:
        fin = fin_df.copy()
        rc = "报告期" if "报告期" in fin.columns else "end_date"
        if rc not in fin.columns:
            return result
        fin[rc] = pd.to_datetime(fin[rc], errors="coerce")
        past = fin[fin[rc] <= as_of].sort_values(rc)
        if len(past) == 0:
            return result
        latest = past.iloc[-1]
        result["fund_roe"] = _to_float(latest.get("净资产收益率") or latest.get("roe"))
        result["fund_gross_margin"] = _to_float(latest.get("销售毛利率") or latest.get("gross_margin"))
        result["fund_net_margin"] = _to_float(latest.get("销售净利率") or latest.get("net_margin"))
        de = latest.get("debt_equity_ratio")
        if de is None and len(past) >= 2:
            prev = past.iloc[-2]
            de = float(prev.get("total_liab", 0) or 0) / max(1, float(prev.get("total_equity", 0) or 1))
        result["fund_de_ratio"] = _to_float(de)
        result["fund_net_profit"] = _to_float(latest.get("净利润") or latest.get("net_profit"))
        roes = [
            _to_float(row.get("净资产收益率") or row.get("roe"))
            for _, row in past.tail(5).iterrows()
            if row.get("净资产收益率") or row.get("roe")
        ]
        result["fund_roe_5y_avg"] = sum(roes) / len(roes) if roes else 0
        if len(past) >= 5:
            result["fund_gm_trend"] = result["fund_gross_margin"] - _to_float(
                past.iloc[-5].get("销售毛利率") or past.iloc[-5].get("gross_margin") or 0
            )
    except Exception:
        pass
    return result


def _compute_valuation_factors(daily_df: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    result = {}
    try:
        past = daily_df[daily_df.index <= as_of]
        if len(past) == 0:
            return result
        latest = past.iloc[-1]
        for key, col in [
            ("val_pe", "pe"),
            ("val_pe_ttm", "pe_ttm"),
            ("val_pb", "pb"),
            ("val_ps", "ps"),
            ("val_dv_ratio", "dv_ratio"),
        ]:
            result[key] = _to_float(latest.get(col))
        if len(past) > 250 and "pe_ttm" in past.columns:
            pe_hist = past["pe_ttm"].dropna().tail(500)
            if len(pe_hist) > 100:
                cur = _to_float(latest.get("pe_ttm"))
                if cur > 0:
                    result["val_pe_percentile"] = float((pe_hist < cur).mean())
        result["val_total_mv"] = _to_float(latest.get("total_mv"))
    except Exception:
        pass
    return result


def _build_month(
    month: str,
    price_cache: dict[str, pd.DataFrame],
    fin_cache: dict[str, pd.DataFrame],
    daily_cache: dict[str, pd.DataFrame],
    factors: dict,
    force: bool = False,
) -> int:
    pq_path = FEATURES_DIR / f"{month}.parquet"
    if pq_path.exists() and not force:
        return 0

    month_dt = pd.Timestamp(month + "-01")
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

        fin_df = fin_cache.get(sym)
        if fin_df is not None:
            row.update(_compute_fundamental_factors(fin_df, month_end))

        daily_df = daily_cache.get(sym)
        if daily_df is not None:
            row.update(_compute_valuation_factors(daily_df, month_end))

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
        HUB.write_parquet(result_df, pq_path)
    return len(rows)


def build_features(
    n_stocks: int = DEFAULT_N_STOCKS,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    force: bool = False,
    include_tushare: bool = True,
) -> None:
    print(f"批量构建 PIT 特征: {n_stocks}只, {start}→{end}")
    symbols = _select_symbols(n_stocks)
    price_cache = _load_price_cache(symbols)
    fin_cache = _load_financial_cache(list(price_cache.keys()))
    daily_cache = _load_daily_basic_cache(list(price_cache.keys()), start, end) if include_tushare else {}
    factors = alpha_factors()

    months = pd.date_range(start, end, freq="MS")
    print(f"\n[4/4] 构建特征 ({len(months)}个月)...")
    for month_dt in months:
        month = month_dt.strftime("%Y-%m")
        rows = _build_month(month, price_cache, fin_cache, daily_cache, factors, force=force)
        print(f"  {month}: {rows} stocks" if rows else f"  {month}: skipped")

    pq_files = iter_feature_files()
    total_rows = sum(len(HUB.read_parquet(pq, default=pd.DataFrame())) for pq in pq_files)
    print(f"\n完成: {len(pq_files)} 个月, {total_rows} 总行")


def _recent_month_window(months: int, today: pd.Timestamp | None = None) -> tuple[str, str]:
    anchor = today or pd.Timestamp.today()
    end_period = anchor.to_period("M") - 1
    start_period = end_period - (months - 1)
    return str(start_period), str(end_period)


def rebuild_recent(months: int = 3, n_stocks: int = DEFAULT_N_STOCKS, force: bool = False) -> None:
    """Incrementally rebuild recent monthly feature slices."""
    if months <= 0:
        return
    start, end = _recent_month_window(months)
    build_features(n_stocks=n_stocks, start=start, end=end, force=force)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PIT monthly feature store")
    parser.add_argument("--n-stocks", type=int, default=DEFAULT_N_STOCKS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--force", action="store_true", help="overwrite existing monthly slices")
    parser.add_argument("--no-tushare", action="store_true", help="skip Tushare daily_basic enrichment")
    parser.add_argument("--recent-months", type=int, default=0, help="rebuild only recent N months")
    args = parser.parse_args()

    if args.recent_months > 0:
        rebuild_recent(months=args.recent_months, n_stocks=args.n_stocks, force=args.force)
    else:
        build_features(
            n_stocks=args.n_stocks,
            start=args.start,
            end=args.end,
            force=args.force,
            include_tushare=not args.no_tushare,
        )
    print("✅ 特征构建完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
