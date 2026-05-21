"""
repair_table.py — 单表数据修复

用法:
  python scripts/repair_table.py <table_name>
  python scripts/repair_table.py stock_holders --limit 200

对指定的逻辑表触发数据重拉，完成后自动重跑健康检查。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from data.datahub import get_datahub
from data.fetchers.macro import MacroFetcher
from data.symbols import CIRCLE_STOCKS

HUB = get_datahub()


def _require_rows(label: str, count: int) -> None:
    if count <= 0:
        raise RuntimeError(f"{label} returned no rows")


def _require_rows_or_cache(label: str, count: int, path: Path, pattern: str = "*.parquet") -> None:
    cached = len(list(path.glob(pattern))) if path.exists() else 0
    if count <= 0 and cached <= 0:
        raise RuntimeError(f"{label} returned no rows and no cached parquet files exist")


def _symbols(limit: int = 0) -> list[str]:
    return list(CIRCLE_STOCKS[:limit]) if limit > 0 else list(CIRCLE_STOCKS)


def _tushare_api():
    import tushare as ts
    from data.tushare_utils import get_tushare_token

    token = get_tushare_token()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not configured")
    return ts.pro_api(token)


def repair_macro(name: str) -> None:
    """Re-fetch macro indicator through MacroFetcher (Tushare first where configured)."""
    print(f"  Fetching macro/{name}...")
    fetcher = MacroFetcher()
    df = fetcher.fetch_indicator(name, force=True)
    if df is not None and len(df) > 0:
        print(f"  ✓ {len(df)} rows, latest: {df.iloc[-1].get('date', 'N/A')}")
    else:
        raise RuntimeError(f"macro/{name} returned no data")


def repair_bond_treasury_yields() -> None:
    """Re-fetch treasury yield curve through the bond adapter."""
    print("  Fetching bond/treasury_yields from AKShare...")
    from data.assets.bond import BondAsset

    adapter = BondAsset()
    cache = adapter.asset_dir / "treasury_yields.parquet"
    cache.unlink(missing_ok=True)
    df = adapter._load_yields()
    _require_rows("bond_treasury_yields", 0 if df is None else len(df))
    print(f"  ✓ {len(df)} rows")


def repair_holders(limit: int = 0) -> None:
    from data.fetchers.holders import HolderFetcher

    symbols = _symbols(limit)
    print(f"  Fetching holders for {len(symbols)} symbols...")
    rows = HolderFetcher().batch_fetch(symbols, force=True)
    _require_rows("stock_holders", len(rows))
    print(f"  ✓ {len(rows)}/{len(symbols)} symbols")


def repair_holdertrade(limit: int = 0) -> None:
    from data.fetchers.holders import HolderTradeFetcher

    symbols = _symbols(limit)
    print(f"  Fetching holder trades for {len(symbols)} symbols...")
    rows = HolderTradeFetcher().batch_fetch(symbols, force=True)
    _require_rows("stock_holdertrade", len(rows))
    print(f"  ✓ {len(rows)}/{len(symbols)} symbols")


def repair_stock_daily(limit: int = 0) -> None:
    from data.fetchers import stock_daily

    symbols = _symbols(limit)
    print(f"  Fetching OHLCV daily for {len(symbols)} symbols...")
    rows = stock_daily.fetch_all(symbols)
    count = sum(1 for df in rows.values() if df is not None and len(df) > 0)
    _require_rows_or_cache("stock_daily", count, HUB.store_dir("stock") / "daily")
    print(f"  ✓ {count}/{len(symbols)} symbols")


def repair_financial_summary(limit: int = 0) -> None:
    from data.fetchers.financial import fetch_all_financials

    symbols = _symbols(limit)
    print(f"  Fetching financial summaries for {len(symbols)} symbols...")
    rows = fetch_all_financials(symbols)
    count = sum(1 for df in rows.values() if df is not None and len(df) > 0)
    _require_rows_or_cache("stock_financials", count, HUB.store_dir("stock") / "financials")
    print(f"  ✓ {count}/{len(symbols)} symbols")


def repair_fina_indicator(limit: int = 0) -> None:
    from data.fetchers.financial import fetch_fina_indicator

    symbols = _symbols(limit)
    print(f"  Fetching Tushare fina_indicator for {len(symbols)} symbols...")
    count = 0
    for sym in symbols:
        df = fetch_fina_indicator(sym)
        if df is not None and len(df) > 0:
            count += 1
    _require_rows_or_cache("stock_fina_indicator", count, HUB.store_dir("stock") / "fina_indicator")
    print(f"  ✓ {count}/{len(symbols)} symbols")


def repair_valuation(limit: int = 0) -> None:
    from data.fetchers.financial import fetch_all_valuations

    symbols = _symbols(limit)
    print(f"  Fetching valuations for {len(symbols)} symbols...")
    rows = fetch_all_valuations(symbols)
    count = sum(1 for df in rows.values() if df is not None and len(df) > 0)
    _require_rows_or_cache("stock_valuation", count, HUB.store_dir("stock") / "valuation")
    print(f"  ✓ {count}/{len(symbols)} symbols")


def repair_adj_factor(limit: int = 0) -> None:
    from scripts.cron_fetch_daily import fetch_adj_factor

    fetched = fetch_adj_factor(pool_size=limit)
    _require_rows_or_cache("stock_adj_factor", int(fetched), HUB.store_dir("stock") / "adj_factor")


def repair_moneyflow_daily(limit: int = 0) -> None:
    from data.fetchers.moneyflow import MoneyflowFetcher

    symbols = _symbols(limit)
    print(f"  Fetching daily moneyflow for {len(symbols)} symbols...")
    rows = MoneyflowFetcher().batch_fetch(symbols, force=True)
    _require_rows("stock_moneyflow_daily", len(rows))
    print(f"  ✓ {len(rows)}/{len(symbols)} symbols")


def repair_moneyflow_monthly(days: int = 365) -> None:
    from scripts.fetch_moneyflow_full import fetch_monthly_only

    start = (datetime.now() - timedelta(days=max(days, 365) * 2)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    fetch_monthly_only(start=start, end=end)


def repair_moneyflow_tushare_daily(days: int = 60) -> None:
    from scripts.fetch_moneyflow_full import fetch_daily_recent

    fetch_daily_recent(max(1, days))
    _require_rows_or_cache(
        "stock_moneyflow_tushare_daily",
        0,
        HUB.store_dir("stock") / "moneyflow" / "daily",
    )


def repair_limit_list() -> None:
    from scripts.cron_fetch_extra import fetch_limit_list

    fetched = fetch_limit_list(full_history=False)
    _require_rows_or_cache("stock_limit_list", int(fetched), HUB.store_dir("stock") / "limit_list")


def repair_research_report() -> None:
    from scripts.cron_fetch_extra import fetch_research_report

    fetched = fetch_research_report(full_history=True)
    _require_rows_or_cache("stock_research_report", int(fetched), HUB.store_dir("stock") / "research_report")


def repair_top_list() -> None:
    from scripts.cron_fetch_extra import fetch_top_list

    fetched = fetch_top_list(full_history=False)
    _require_rows_or_cache("stock_top_list", int(fetched), HUB.store_dir("stock") / "top_list")


def repair_dividend() -> None:
    from scripts.cron_fetch_extra import fetch_dividend

    fetched = fetch_dividend(full_history=True)
    _require_rows_or_cache("stock_dividend", int(fetched), HUB.store_dir("stock") / "dividend")


def repair_fund_daily() -> None:
    from scripts.cron_fetch_extra import fetch_fund_daily

    fetched = fetch_fund_daily(full_history=True)
    _require_rows_or_cache("fund_daily", int(fetched), HUB.store_dir("fund") / "daily")


def repair_fund_portfolio() -> None:
    from scripts.cron_fetch_extra import fetch_fund_portfolio

    fetched = fetch_fund_portfolio(full_history=True)
    _require_rows_or_cache("fund_portfolio", int(fetched), HUB.store_dir("fund") / "portfolio")


def repair_fund_nav() -> None:
    from scripts.cron_fetch_extra import fetch_fund_nav

    fetched = fetch_fund_nav(full_history=True)
    _require_rows_or_cache("fund_nav", int(fetched), HUB.store_dir("fund") / "nav")


def repair_futures_daily() -> None:
    from scripts.cron_fetch_extra import fetch_futures_daily

    fetched = fetch_futures_daily(full_history=True)
    _require_rows_or_cache("futures_daily", int(fetched), HUB.store_dir("futures") / "daily")


def repair_broker_recommend(months: int = 6) -> None:
    api = _tushare_api()
    store = HUB.store_dir("stock") / "broker_recommend"
    store.mkdir(parents=True, exist_ok=True)
    count = 0
    periods = pd.period_range(end=pd.Timestamp.today().to_period("M"), periods=months, freq="M")
    for period in periods:
        month = period.strftime("%Y%m")
        try:
            time.sleep(0.3)
            df = api.broker_recommend(month=month)
            if df is not None and len(df) > 0:
                if "month" not in df.columns:
                    df["month"] = month
                HUB.write_parquet(df, store / f"{month}.parquet")
                count += len(df)
                print(f"  ✓ {month}: {len(df)} rows")
        except Exception as exc:
            print(f"  ✗ {month}: {type(exc).__name__}: {str(exc)[:80]}")
    _require_rows("stock_broker_recommend", count)


def repair_share_float(days: int = 730) -> None:
    api = _tushare_api()
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    end = (datetime.now() + timedelta(days=days)).strftime("%Y%m%d")
    df = api.share_float(start_date=start, end_date=end)
    _require_rows("share_float", 0 if df is None else len(df))
    store = HUB.store_dir("stock") / "share_float"
    store.mkdir(parents=True, exist_ok=True)
    HUB.write_parquet(df, store / "all.parquet")
    print(f"  ✓ {len(df)} rows")


def repair_repurchase(days: int = 730) -> None:
    api = _tushare_api()
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    df = api.repurchase(start_date=start, end_date=end)
    _require_rows("repurchase", 0 if df is None else len(df))
    store = HUB.store_dir("stock") / "repurchase"
    store.mkdir(parents=True, exist_ok=True)
    HUB.write_parquet(df, store / "all.parquet")
    print(f"  ✓ {len(df)} rows")


REPAIR_MAP = {
    # Macro — direct AKShare fetch
    "macro_cpi":             lambda limit=0, days=365: repair_macro("cpi"),
    "macro_gdp":             lambda limit=0, days=365: repair_macro("gdp"),
    "macro_lpr":             lambda limit=0, days=365: repair_macro("lpr"),
    "macro_money_supply":    lambda limit=0, days=365: repair_macro("money_supply"),
    "macro_pmi":             lambda limit=0, days=365: repair_macro("pmi"),
    "macro_ppi":             lambda limit=0, days=365: repair_macro("ppi"),
    "macro_shibor":          lambda limit=0, days=365: repair_macro("shibor"),
    "bond_treasury_yields":  lambda limit=0, days=365: repair_bond_treasury_yields(),
    # Stock — Tushare re-fetch
    "stock_daily":                lambda limit=0, days=365: repair_stock_daily(limit),
    "stock_adj_factor":           lambda limit=0, days=365: repair_adj_factor(limit),
    "stock_financials":           lambda limit=0, days=365: repair_financial_summary(limit),
    "stock_fina_indicator":       lambda limit=0, days=365: repair_fina_indicator(limit),
    "stock_valuation":            lambda limit=0, days=365: repair_valuation(limit),
    "stock_holders":              lambda limit=0, days=365: repair_holders(limit),
    "stock_holdertrade":          lambda limit=0, days=365: repair_holdertrade(limit),
    "stock_moneyflow_daily":      lambda limit=0, days=365: repair_moneyflow_daily(limit),
    "stock_moneyflow_tushare_daily": lambda limit=0, days=365: repair_moneyflow_tushare_daily(days),
    "stock_moneyflow_monthly":    lambda limit=0, days=365: repair_moneyflow_monthly(days),
    "stock_broker_recommend":     lambda limit=0, days=365: repair_broker_recommend(months=max(1, min(24, days // 30))),
    "stock_limit_list":           lambda limit=0, days=365: repair_limit_list(),
    "stock_top_list":             lambda limit=0, days=365: repair_top_list(),
    "stock_research_report":      lambda limit=0, days=365: repair_research_report(),
    "stock_dividend":             lambda limit=0, days=365: repair_dividend(),
    "share_float":                lambda limit=0, days=365: repair_share_float(days),
    "repurchase":                 lambda limit=0, days=365: repair_repurchase(days),
    # Fund
    "fund_daily":                 lambda limit=0, days=365: repair_fund_daily(),
    "fund_portfolio":             lambda limit=0, days=365: repair_fund_portfolio(),
    "fund_nav":                   lambda limit=0, days=365: repair_fund_nav(),
    # Futures
    "futures_daily":              lambda limit=0, days=365: repair_futures_daily(),
}


def repair(table: str, limit: int = 0, days: int = 365) -> None:
    if table not in REPAIR_MAP:
        print(f"Unknown or non-repairable table: {table}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"REPAIR: {table}")
    print(f"{'='*60}")

    REPAIR_MAP[table](limit=limit, days=days)

    # Re-run health check
    import subprocess
    print(f"\n  Re-running health check...")
    result = subprocess.run(
        [sys.executable, "scripts/db_health_check.py"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=300,
    )
    print(f"  {result.stdout.strip()}")

    print(f"\nRepair complete: {table}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair one logical data table")
    parser.add_argument("table_name", choices=sorted(REPAIR_MAP))
    parser.add_argument("--limit", type=int, default=int(os.environ.get("QUANT_REPAIR_SYMBOL_LIMIT", "0")))
    parser.add_argument("--days", type=int, default=int(os.environ.get("QUANT_REPAIR_DAYS", "365")))
    args = parser.parse_args()
    repair(args.table_name, limit=args.limit, days=args.days)
