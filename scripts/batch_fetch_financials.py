#!/usr/bin/env python3
"""
Batch fetch financial data (同花顺 财务摘要) for all 1000 stocks in universe.

One-time run. Financial reports are historical facts — once published, immutable.
After initial fetch, only incremental updates needed for new quarterly reports.

Usage:
  python scripts/batch_fetch_financials.py [--force] [--limit N]
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

# ── Proxy bypass (must be before any AKShare import) ──
for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd
import akshare as ak

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from data.datahub import get_datahub

HUB = get_datahub()
CACHE_DIR = HUB.cache_dir()
UNIVERSE_PATH = PROJECT / 'data' / 'universe_raw.json'
PROGRESS_PATH = PROJECT / 'data' / '.financials_progress.json'

# Throttle between requests (seconds) — AKShare has no official rate limit but be polite
THROTTLE = 1.5
# Retry on failure
MAX_RETRIES = 2
RETRY_DELAY = 5.0


def load_progress() -> dict:
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {'completed': [], 'failed': [], 'last_idx': 0}


def save_progress(progress: dict):
    with open(PROGRESS_PATH, 'w') as f:
        json.dump(progress, f, ensure_ascii=False)


def cache_path(symbol: str) -> str:
    """MD5-based cache path (same as fetcher.py)"""
    import hashlib
    key = f"financial_{symbol}"
    h = hashlib.md5(key.encode()).hexdigest()
    return CACHE_DIR / f"{h}.parquet"


def fetch_one(symbol: str, name: str) -> bool:
    """Fetch financial abstract for one stock. Returns True on success."""
    path = cache_path(symbol)

    for attempt in range(MAX_RETRIES + 1):
        try:
            df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期")
            if df is None or df.empty:
                print(f"  {symbol} {name}: empty result")
                return False

            # Fix: PyArrow can't infer types for mixed str/percentage columns.
            # Convert all object columns to string before saving.
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str)

            HUB.write_parquet(df, path)
            return True

        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"  {symbol} {name}: retry {attempt+1}/{MAX_RETRIES} — {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  {symbol} {name}: FAILED — {e}")
                return False

    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Re-fetch even if cached')
    parser.add_argument('--limit', type=int, default=0, help='Limit to N stocks (0=all)')
    args = parser.parse_args()

    # Load universe
    with open(UNIVERSE_PATH) as f:
        universe = json.load(f)

    stocks = [(s['code'], s['name']) for s in universe]
    total = len(stocks)

    if args.limit and args.limit < total:
        stocks = stocks[:args.limit]
        total = len(stocks)

    progress = load_progress()
    completed = set(progress['completed'])
    failed = set(progress['failed'])
    start_idx = progress.get('last_idx', 0)

    print(f"Batch fetch financials: {total} stocks")

    # Count already cached
    already = 0
    for code, _ in stocks:
        path = cache_path(code)
        if path.exists() and not args.force:
            already += 1
            completed.add(code)
    print(f"  Already cached: {already}")
    print(f"  To fetch: {total - already}")
    print(f"  Estimated time: {(total - already) * THROTTLE / 60:.1f} min")
    print()

    new_fetched = 0
    new_failed = 0

    for i, (code, name) in enumerate(stocks):
        if code in completed and not args.force:
            continue
        if code in failed and not args.force:
            continue

        path = cache_path(code)
        if path.exists() and not args.force:
            completed.add(code)
            continue

        print(f"[{i+1}/{total}] {code} {name} ...", end=' ', flush=True)
        success = fetch_one(code, name)

        if success:
            completed.add(code)
            new_fetched += 1
            print("OK")
        else:
            failed.add(code)
            new_failed += 1
            print("FAIL")

        # Save progress every 10 stocks
        if (i + 1) % 10 == 0:
            progress = {
                'completed': sorted(completed),
                'failed': sorted(failed),
                'last_idx': i,
                'total': total,
                'new_fetched': new_fetched,
                'new_failed': new_failed,
            }
            save_progress(progress)

        time.sleep(THROTTLE)

    # Final save
    progress = {
        'completed': sorted(completed),
        'failed': sorted(failed),
        'last_idx': total - 1,
        'total': total,
        'new_fetched': new_fetched,
        'new_failed': new_failed,
    }
    save_progress(progress)

    print(f"\nDone. Fetched: {new_fetched}, Failed: {new_failed}, Already cached: {already}")


if __name__ == '__main__':
    main()
