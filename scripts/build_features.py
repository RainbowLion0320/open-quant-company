#!/usr/bin/env python3
"""Build point-in-time as-of features into ``var/store/features``.

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

from data.storage.datahub import get_datahub
from data.features.factor_inputs import compute_fundamental_factors, compute_valuation_factors
from data.features.feature_store import FEATURES_DIR, enrich_from_registry, iter_feature_files, write_feature_slice
from data.market.price_service import get_stock_prices
from data.market.price_types import PriceUseCase
from data.market.symbols import CIRCLE_STOCKS


HUB = get_datahub()
DAILY_BASIC_CACHE_DIR = HUB.cache_root / "features" / "daily_basic"
DEFAULT_N_STOCKS = int(os.environ.get("QUANT_FEATURE_N_STOCKS", str(len(CIRCLE_STOCKS))))
DEFAULT_START = os.environ.get("QUANT_FEATURE_START", "2018-01")
DEFAULT_END = os.environ.get(
    "QUANT_FEATURE_END",
    (pd.Timestamp.today().to_period("M") - 1).strftime("%Y-%m"),
)
DEFAULT_FREQUENCY = "daily"
SKIP_PREFIXES = ("92", "83", "87", "43")


def _select_symbols(n_stocks: int) -> list[str]:
    symbols_raw = list(CIRCLE_STOCKS)[:n_stocks]
    symbols = [s for s in symbols_raw if not any(s.startswith(p) for p in SKIP_PREFIXES)]
    skipped = len(symbols_raw) - len(symbols)
    if skipped:
        print(f"  过滤掉 {skipped} 只无效标的 (北交所/新三板/退市板), 剩余 {len(symbols)}")
    return symbols


def _load_price_cache(symbols: list[str]) -> dict[str, pd.DataFrame]:
    print("\n[1/5] 加载价格数据...")
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
    print("\n[2/5] 加载财务数据 (PE/PB/ROE/毛利率/D-E)...")
    from data.market.financials import get_financial_summary

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
    print("\n[3/5] 加载日频指标 PE/PB (Tushare daily_basic)...")
    daily_cache: dict[str, pd.DataFrame] = {}
    DAILY_BASIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import tushare as ts
        from data.ingestion.tushare_utils import get_tushare_token

        token = get_tushare_token()
        ts_api = ts.pro_api(token) if token else None
        if ts_api is None:
            raise RuntimeError("No Tushare token")

        start_ts, end_ts = _date_range_bounds(start, end)
        start_date = start_ts.strftime("%Y%m%d")
        end_date = end_ts.strftime("%Y%m%d")
        errors: list[str] = []
        total = len(symbols)
        for i, sym in enumerate(symbols, 1):
            cache_path = DAILY_BASIC_CACHE_DIR / f"{sym}_{start_date}_{end_date}.parquet"
            try:
                df = HUB.read_parquet(cache_path, default=pd.DataFrame()) if cache_path.exists() else pd.DataFrame()
                if df is None or df.empty:
                    suffix = ".SH" if sym.startswith("6") else ".SZ"
                    df = ts_api.daily_basic(
                        ts_code=f"{sym}{suffix}",
                        start_date=start_date,
                        end_date=end_date,
                        fields="trade_date,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv,circ_mv",
                    )
                    if df is not None and len(df) > 0:
                        HUB.write_parquet(df, cache_path)
                    time.sleep(0.3)
                if df is not None and len(df) > 0:
                    df["trade_date"] = pd.to_datetime(df["trade_date"])
                    daily_cache[sym] = df.set_index("trade_date").sort_index()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                if len(errors) < 10:
                    errors.append(f"{sym}: {type(exc).__name__}: {exc}")
            if i % 20 == 0:
                print(f"  PE/PB {i}/{total} ({len(daily_cache)} valid, {len(errors)} sample errors)", flush=True)
        if errors:
            print("  PE/PB errors (sample):")
            for err in errors:
                print(f"    {err}")
    except Exception as exc:
        print(f"  Tushare不可用 ({type(exc).__name__}), 跳过PE/PB")
    print(f"  日频估值有效: {len(daily_cache)}")
    return daily_cache


def _masked_rolling_std(series: pd.Series, window: int) -> pd.Series:
    result = series.rolling(window, min_periods=1).std(ddof=1)
    result.iloc[: max(0, window - 1)] = np.nan
    return result


def _masked_rolling_mean(series: pd.Series, window: int) -> pd.Series:
    result = series.rolling(window, min_periods=1).mean()
    result.iloc[: max(0, window - 1)] = np.nan
    return result


def _compute_technical_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized equivalent of ``signals.expression.alpha_factors`` for one stock."""
    close = pd.to_numeric(df["close"], errors="coerce")
    open_ = pd.to_numeric(df["open"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")

    close_ma5 = close.rolling(5, min_periods=5).mean()
    close_ma10 = close.rolling(10, min_periods=10).mean()
    close_ma20 = close.rolling(20, min_periods=20).mean()
    close_ma60 = close.rolling(60, min_periods=60).mean()
    close_std20 = close.rolling(20, min_periods=20).std(ddof=1)
    ret_1d = close.pct_change()
    delta_1d = close - close.shift(1)
    delta_5d = close - close.shift(5)
    rsi_mean = _masked_rolling_mean(delta_1d, 14)
    rsi_std = _masked_rolling_std(delta_1d, 14)

    frame = pd.DataFrame(index=df.index)
    frame["ret_1d"] = ret_1d
    frame["ret_5d"] = close / close.shift(5) - 1
    frame["ret_10d"] = close / close.shift(10) - 1
    frame["ret_20d"] = close / close.shift(20) - 1
    frame["ret_60d"] = close / close.shift(60) - 1
    frame["ma5_bias"] = close / close_ma5 - 1
    frame["ma10_bias"] = close / close_ma10 - 1
    frame["ma20_bias"] = close / close_ma20 - 1
    frame["ma60_bias"] = close / close_ma60 - 1
    frame["vol_5d"] = _masked_rolling_std(ret_1d, 5)
    frame["vol_20d"] = _masked_rolling_std(ret_1d, 20)
    frame["vol_60d"] = _masked_rolling_std(ret_1d, 60)
    frame["volume_ratio_5"] = volume / volume.rolling(5, min_periods=5).mean()
    frame["volume_ratio_20"] = volume / volume.rolling(20, min_periods=20).mean()
    frame["amplitude"] = (high - low) / close.shift(1)
    frame["high_low_ratio"] = high / low - 1
    frame["ma5_20_cross"] = (close_ma5 > close_ma20).astype(float)
    frame.loc[close_ma5.isna() | close_ma20.isna(), "ma5_20_cross"] = np.nan
    frame["ma20_60_cross"] = (close_ma20 > close_ma60).astype(float)
    frame.loc[close_ma20.isna() | close_ma60.isna(), "ma20_60_cross"] = np.nan
    frame["rsi_14"] = rsi_mean / (rsi_std + 1e-9)
    frame["vol_adj_mom_5d"] = delta_5d / (close_std20 + 1e-6)
    frame["volume_conviction"] = (volume * delta_5d) / (close_std20 + 1e-6)
    frame["intraday_close_strength"] = (close - low) / (high - low + 0.0001)
    frame["upside_intraday_range"] = (high - open_) / (close_std20 + 1e-6)
    frame["midpoint_bias"] = (close - (high + low) / 2) / (close_std20 + 1e-6)
    frame["volume_vol_ratio"] = volume / (close_std20 * close_ma20 + 1e-6)
    frame["open_gap_ma20"] = (open_ - close_ma20) / (close_std20 + 1e-6)
    return frame.replace([np.inf, -np.inf], np.nan)


def _build_technical_cache(price_cache: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    print("\n[4/5] 预计算技术因子...")
    technical_cache: dict[str, pd.DataFrame] = {}
    total = len(price_cache)
    for i, (sym, df) in enumerate(price_cache.items(), 1):
        try:
            technical_cache[sym] = _compute_technical_factor_frame(df)
        except Exception:
            pass
        if i % 100 == 0:
            print(f"  技术因子: {i}/{total} ({len(technical_cache)} valid)", flush=True)
    print(f"  技术因子有效: {len(technical_cache)}")
    return technical_cache


def _build_feature_slice(
    storage_key: str,
    as_of_date: str | pd.Timestamp,
    price_cache: dict[str, pd.DataFrame],
    technical_cache: dict[str, pd.DataFrame],
    fin_cache: dict[str, pd.DataFrame],
    daily_cache: dict[str, pd.DataFrame],
    force: bool = False,
    min_bars: int = 60,
) -> int:
    pq_path = FEATURES_DIR / f"{storage_key}.parquet"
    if pq_path.exists() and not force:
        return 0

    as_of = pd.Timestamp(as_of_date).normalize()
    as_of_key = as_of.strftime("%Y-%m-%d")
    month = as_of.to_period("M").strftime("%Y-%m")
    rows = []
    for sym, df in price_cache.items():
        idx = df.index.searchsorted(as_of, side="right") - 1
        if idx < max(0, min_bars - 1):
            continue
        row = {"symbol": sym, "as_of_date": as_of_key, "month": month}

        feature_frame = technical_cache.get(sym)
        if feature_frame is not None and idx < len(feature_frame):
            feature_row = feature_frame.iloc[idx]
            for fname, val in feature_row.items():
                row[fname] = val if not pd.isna(val) else None

        fin_df = fin_cache.get(sym)
        if fin_df is not None:
            row.update(compute_fundamental_factors(fin_df, as_of))

        daily_df = daily_cache.get(sym)
        if daily_df is not None:
            row.update(compute_valuation_factors(daily_df, as_of))

        fwd_idx = idx + 20
        if idx >= 0 and fwd_idx < len(df):
            cur = df.iloc[idx]["close"]
            fwd = df.iloc[fwd_idx]["close"]
            row["ret_fwd_20d"] = (fwd / cur - 1) if cur > 0 else None
        rows.append(row)

    if rows:
        result_df = pd.DataFrame(rows)
        from data.quality.cleaner import DataCleaner

        cleaner = DataCleaner()
        result_df, _ = cleaner.clean_features(result_df)
        result_df = enrich_from_registry(result_df, as_of_key, list(price_cache.keys()))
        write_feature_slice(result_df, storage_key, directory=FEATURES_DIR, hub=HUB)
    return len(rows)


def _build_asof(
    as_of_date: str,
    price_cache: dict[str, pd.DataFrame],
    technical_cache: dict[str, pd.DataFrame],
    fin_cache: dict[str, pd.DataFrame],
    daily_cache: dict[str, pd.DataFrame],
    force: bool = False,
    min_bars: int = 60,
) -> int:
    key = pd.Timestamp(as_of_date).strftime("%Y-%m-%d")
    return _build_feature_slice(
        key,
        key,
        price_cache,
        technical_cache,
        fin_cache,
        daily_cache,
        force=force,
        min_bars=min_bars,
    )


def _date_range_bounds(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_ts = pd.Timestamp(start + "-01") if len(start) == 7 else pd.Timestamp(start)
    if len(end) == 7:
        end_ts = pd.Timestamp(end + "-01") + pd.offsets.MonthEnd(0)
    else:
        end_ts = pd.Timestamp(end)
    return start_ts.normalize(), end_ts.normalize()


def _daily_asof_dates(
    start: str,
    end: str,
    price_cache: dict[str, pd.DataFrame],
) -> list[pd.Timestamp]:
    start_ts, end_ts = _date_range_bounds(start, end)
    dates: set[pd.Timestamp] = set()
    for frame in price_cache.values():
        idx = pd.DatetimeIndex(frame.index)
        eligible = idx[(idx >= start_ts) & (idx <= end_ts)]
        dates.update(pd.Timestamp(dt).normalize() for dt in eligible)
    return sorted(dates)


def build_features(
    n_stocks: int = DEFAULT_N_STOCKS,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    force: bool = False,
    include_tushare: bool = True,
    frequency: str = DEFAULT_FREQUENCY,
) -> None:
    frequency = str(frequency or DEFAULT_FREQUENCY).lower()
    if frequency != "daily":
        raise ValueError(f"unsupported feature frequency: {frequency}")

    print(f"批量构建 PIT 特征: {n_stocks}只, {start}→{end}, frequency={frequency}")
    symbols = _select_symbols(n_stocks)
    price_cache = _load_price_cache(symbols)
    fin_cache = _load_financial_cache(list(price_cache.keys()))
    daily_cache = _load_daily_basic_cache(list(price_cache.keys()), start, end) if include_tushare else {}
    technical_cache = _build_technical_cache(price_cache)

    dates = _daily_asof_dates(start, end, price_cache)
    print(f"\n[5/5] 构建特征 ({len(dates)}个交易日)...")
    for as_of in dates:
        key = as_of.strftime("%Y-%m-%d")
        rows = _build_asof(key, price_cache, technical_cache, fin_cache, daily_cache, force=force)
        print(f"  {key}: {rows} stocks" if rows else f"  {key}: skipped")

    pq_files = iter_feature_files()
    total_rows = sum(len(HUB.read_parquet(pq, default=pd.DataFrame())) for pq in pq_files)
    print(f"\n完成: {len(pq_files)} 个 as-of 特征切片, {total_rows} 总行")


def _recent_month_window(months: int, today: pd.Timestamp | None = None) -> tuple[str, str]:
    anchor = today or pd.Timestamp.today()
    end_period = anchor.to_period("M") - 1
    start_period = end_period - (months - 1)
    return str(start_period), str(end_period)


def rebuild_recent(
    months: int = 3,
    n_stocks: int = DEFAULT_N_STOCKS,
    force: bool = False,
    frequency: str = DEFAULT_FREQUENCY,
) -> None:
    """Incrementally rebuild daily as-of feature slices for recent month windows."""
    if months <= 0:
        return
    start, end = _recent_month_window(months)
    build_features(n_stocks=n_stocks, start=start, end=end, force=force, frequency=frequency)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PIT as-of feature store")
    parser.add_argument("--n-stocks", type=int, default=DEFAULT_N_STOCKS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--force", action="store_true", help="overwrite existing daily as-of slices")
    parser.add_argument("--no-tushare", action="store_true", help="skip Tushare daily_basic enrichment")
    parser.add_argument("--recent-months", type=int, default=0, help="rebuild only recent N months")
    parser.add_argument(
        "--frequency",
        choices=["daily"],
        default=DEFAULT_FREQUENCY,
        help="feature as-of cadence; daily is the only supported canonical mode",
    )
    args = parser.parse_args()

    if args.recent_months > 0:
        rebuild_recent(months=args.recent_months, n_stocks=args.n_stocks, force=args.force, frequency=args.frequency)
    else:
        build_features(
            n_stocks=args.n_stocks,
            start=args.start,
            end=args.end,
            force=args.force,
            include_tushare=not args.no_tushare,
            frequency=args.frequency,
        )
    print("✅ 特征构建完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
