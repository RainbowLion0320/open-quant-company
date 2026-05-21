"""
cron_fetch_ohlcv.py — 日频 OHLCV 数据预加载

应在每天收盘后 (15:30+) 运行。拉取全池股票的日线数据到 parquet。
日常消费代码直接读 parquet，不再调 API。

用法:
  python scripts/cron_fetch_ohlcv.py [--pool top500] [--source sina]
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from data.fetchers.stock_daily import fetch_one
from data.symbols import CIRCLE_STOCKS


def main(pool: str = "top500", source: str = "sina"):
    symbols = CIRCLE_STOCKS
    if not symbols:
        print("No symbols found")
        return

    print(f"Fetching OHLCV for {len(symbols)} stocks (pool={pool}, source={source})...")

    ok = 0
    fail = 0
    for i, sym in enumerate(symbols):
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(symbols)}] ok={ok} fail={fail}")
        result = fetch_one(sym, source=source)
        if result is not None and len(result) > 0:
            ok += 1
        else:
            fail += 1

    print(f"\nDone: {ok} OK, {fail} failed, {len(symbols)} total")


if __name__ == "__main__":
    pool = "top500"
    source = "sina"
    for arg in sys.argv[1:]:
        if arg.startswith("--pool="):
            pool = arg.split("=", 1)[1]
        elif arg.startswith("--source="):
            source = arg.split("=", 1)[1]
    main(pool=pool, source=source)
