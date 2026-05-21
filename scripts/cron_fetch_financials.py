"""
cron_fetch_financials.py — 财务数据批量预加载

应在季度财报公布后 (1/4/7/10月) 运行，或设月度 cron。
拉取全池股票的财务摘要 + 估值数据到 parquet。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from data.fetchers.financial import fetch_financial_summary, fetch_valuation
from data.symbols import CIRCLE_STOCKS


def main():
    symbols = CIRCLE_STOCKS
    if not symbols:
        print("No symbols found")
        return

    print(f"Fetching financial summary for {len(symbols)} stocks...")
    ok = 0
    fail = 0
    for i, sym in enumerate(symbols):
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(symbols)}] ok={ok} fail={fail}")
        result = fetch_financial_summary(sym)
        if result is not None and len(result) > 0:
            ok += 1
        else:
            fail += 1
    print(f"Financial summary: {ok} OK, {fail} failed")

    print(f"\nFetching daily valuation for {len(symbols)} stocks...")
    ok = 0
    fail = 0
    for i, sym in enumerate(symbols):
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(symbols)}] ok={ok} fail={fail}")
        result = fetch_valuation(sym)
        if result is not None and len(result) > 0:
            ok += 1
        else:
            fail += 1
    print(f"Valuation: {ok} OK, {fail} failed")


if __name__ == "__main__":
    main()
