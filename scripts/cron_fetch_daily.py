#!/usr/bin/env python3
"""
Cron: Daily Market Data Fetch (Mon-Fri 15:31)

Consolidates all DAILY-frequency data dimensions:
  - OHLCV (AKShare): stock daily prices
  - Shibor (AKShare): interbank rates
  - Valuation (Tushare): PE/PB/PS daily
  - Adj Factor (Tushare): price adjustment factors
  - Moneyflow daily (Tushare): fund flows
  - Fund daily + NAV (Tushare): ETF prices
  - Futures daily (Tushare): main contracts

Usage:
  python scripts/cron_fetch_daily.py              # incremental
  python scripts/cron_fetch_daily.py --full       # full history
  python scripts/cron_fetch_daily.py --pool 100   # limit stock pool
"""
import sys, time, argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from data.datahub import get_datahub
from data.tushare_utils import get_tushare_token

HUB = get_datahub()
TOKEN = get_tushare_token()
PROJECT = Path(__file__).resolve().parent.parent

# ── Helpers ──

def _throttle(secs=0.5):
    time.sleep(secs)

def _tushare_api():
    if not TOKEN:
        raise RuntimeError("TUSHARE_TOKEN is not configured")
    import tushare as ts
    return ts.pro_api(TOKEN)

def _today_str():
    return datetime.now().strftime("%Y%m%d")

# ═══════════════════════════════════════
# 1. OHLCV (AKShare)
# ═══════════════════════════════════════

def fetch_ohlcv(pool_size=0):
    """Fetch latest daily OHLCV for pool stocks."""
    from data.fetchers import stock_daily

    symbols = _load_pool(pool_size)
    print(f"  [ohlcv] pool={len(symbols)}")
    results = stock_daily.fetch_all(symbols)
    fetched = sum(1 for df in results.values() if df is not None and len(df) > 0)
    print(f"  [ohlcv] {fetched}/{len(symbols)} stocks available")
    return fetched

# ═══════════════════════════════════════
# 2. Shibor (AKShare)
# ═══════════════════════════════════════

def fetch_shibor():
    from data.fetchers.macro import MacroFetcher
    f = MacroFetcher()
    df = f.fetch_indicator("shibor", force=True)
    if df is not None:
        print(f"  [shibor] {len(df)} rows, latest {df.iloc[-1]['date']}")
        return 1
    print("  [shibor] FAILED")
    return 0

# ═══════════════════════════════════════
# 3. Valuation (Tushare daily_basic: PE/PB/PS)
# ═══════════════════════════════════════

def fetch_valuation(pool_size=0):
    """Fetch latest PE/PB/PS for pool stocks via Tushare daily_basic."""
    api = _tushare_api()
    store = HUB.store_dir("stock") / "valuation"
    store.mkdir(parents=True, exist_ok=True)

    # Get pool symbols (top N by market cap)
    try:
        symbols = _load_pool(pool_size)
    except Exception:
        symbols = []

    if not symbols:
        print("  [valuation] no pool symbols")
        return 0

    trade_date = _today_str()
    fetched = 0
    for sym in symbols[:max(1, pool_size or 5200)]:
        pq = store / f"{sym}.parquet"
        existing = pd.DataFrame()
        try:
            # Check if already has today's data
            existing = HUB.read_parquet(pq, default=pd.DataFrame())
            if not existing.empty and str(existing.iloc[-1].get("trade_date", "")) >= trade_date:
                continue
        except Exception:
            pass
        try:
            _throttle(0.3)
            df = api.daily_basic(ts_code=f"{sym}.SH" if sym.startswith("6") else f"{sym}.SZ",
                                 start_date=(datetime.now() - timedelta(days=30)).strftime("%Y%m%d"),
                                 end_date=trade_date)
            if df is not None and len(df) > 0:
                # Merge with existing
                if not existing.empty:
                    df = pd.concat([existing, df], ignore_index=True).drop_duplicates(subset=["trade_date"], keep="last")
                HUB.write_parquet(df, pq)
                fetched += 1
        except Exception as e:
            if "频率" in str(e) or "limit" in str(e).lower():
                break  # rate limited, stop
            continue

    print(f"  [valuation] {fetched} stocks updated")
    return fetched

# ═══════════════════════════════════════
# 4. Adj Factor (Tushare)
# ═══════════════════════════════════════

def fetch_adj_factor(pool_size=0):
    """Fetch latest adj_factor for pool stocks."""
    api = _tushare_api()
    store = HUB.store_dir("stock") / "adj_factor"
    store.mkdir(parents=True, exist_ok=True)
    symbols = _load_pool(pool_size)
    if not symbols: return 0

    fetched = 0
    for sym in symbols[:max(1, pool_size or 5200)]:
        pq = store / f"{sym}.parquet"
        try:
            _throttle(0.2)
            df = api.adj_factor(ts_code=f"{sym}.SH" if sym.startswith("6") else f"{sym}.SZ")
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
        except Exception as e:
            if "频率" in str(e) or "limit" in str(e).lower():
                break
            continue
    print(f"  [adj_factor] {fetched} stocks updated")
    return fetched

# ═══════════════════════════════════════
# 5. Moneyflow Daily (Tushare)
# ═══════════════════════════════════════

def fetch_moneyflow_daily():
    """Fetch latest daily moneyflow for all stocks (one API call per day)."""
    api = _tushare_api()
    store = HUB.dimension_root("moneyflow_tushare_daily")
    store.mkdir(parents=True, exist_ok=True)

    # Get last 5 trade days, fetch missing
    cal = api.trade_cal(exchange="SSE", start_date="20240101", end_date=_today_str())
    trade_days = sorted(cal[cal["is_open"] == 1]["cal_date"].tolist(), reverse=True)[:5]

    fetched = 0
    for d in trade_days:
        pq = store / f"{d}.parquet"
        if pq.exists():
            continue
        try:
            _throttle(0.5)
            df = api.moneyflow(trade_date=d)
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
        except Exception as e:
            if "频率" in str(e) or "limit" in str(e).lower():
                break
            continue
    print(f"  [moneyflow] {fetched} new days")
    return fetched

# ═══════════════════════════════════════
# 6. Fund Daily + NAV + Futures (from cron_fetch_extra)
# ═══════════════════════════════════════

def fetch_fund_daily():
    """Fetch daily fund OHLCV for top 10 ETFs."""
    from scripts.cron_fetch_extra import fetch_fund_daily as _ffd
    return _ffd(full_history=False)

def fetch_fund_nav():
    from scripts.cron_fetch_extra import fetch_fund_nav as _ffn
    return _ffn(full_history=False)

def fetch_futures_daily():
    from scripts.cron_fetch_extra import fetch_futures_daily as _ffut
    return _ffut(full_history=False)

# ── Helpers ──

def _load_pool(pool_size=0):
    """Load stock pool symbols, sorted by market cap if available."""
    from data.symbols import CIRCLE_STOCKS
    symbols = list(CIRCLE_STOCKS)
    # Try to sort by market cap for priority
    try:
        val_path = HUB.store_dir("stock") / "valuation"
        if val_path.exists():
            latest_sizes = {}
            for f in sorted(val_path.glob("*.parquet"))[-100:]:
                try:
                    df = HUB.read_parquet(f)
                    if not df.empty and "total_mv" in df.columns:
                        sym = f.stem
                        latest_sizes[sym] = float(df.iloc[-1]["total_mv"])
                except Exception:
                    pass
            if latest_sizes:
                symbols.sort(key=lambda s: latest_sizes.get(s, 0), reverse=True)
    except Exception:
        pass
    return symbols[:pool_size] if pool_size > 0 else symbols


# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily market data fetch")
    parser.add_argument("--pool", type=int, default=0, help="Stock pool size (0=all)")
    parser.add_argument("--full", action="store_true", help="Full history fetch")
    parser.add_argument("--skip-slow", action="store_true", help="Skip per-stock fetches (valuation/adj_factor)")
    args = parser.parse_args()

    print(f"Daily Market Fetch — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"pool={args.pool or 'all'}, full={args.full}")
    print("=" * 55)

    results = {}

    # Fast fetches (single API call)
    results["shibor"] = fetch_shibor()
    _throttle(0.5)

    # OHLCV (AKShare, stock by stock but fast)
    results["ohlcv"] = fetch_ohlcv(pool_size=args.pool)

    # Moneyflow (one call per trading day)
    results["moneyflow"] = fetch_moneyflow_daily()

    # Fund & Futures
    results["fund_daily"] = fetch_fund_daily()
    _throttle(0.5)
    results["fund_nav"] = fetch_fund_nav()
    _throttle(0.5)
    results["futures"] = fetch_futures_daily()

    # Slower per-stock fetches
    if not args.skip_slow:
        _throttle(0.5)
        results["valuation"] = fetch_valuation(pool_size=args.pool)
        _throttle(0.5)
        results["adj_factor"] = fetch_adj_factor(pool_size=args.pool)

    print(f"\nDone. Results: { {k: v for k, v in results.items() if v} }")
