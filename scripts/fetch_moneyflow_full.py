"""
Tushare Moneyflow 全历史下载器

Tushare moneyflow API: 每交易日一次调用, 返回全市场资金流向.
积分门槛: 2000 → 我们有权限, 不消耗积分.
频次限制: ~200次/分钟 → 按日拉取约需 20 分钟 (4000交易日).

缓存策略:
  日频: data/store/stock/moneyflow/daily/YYYY-MM-DD.parquet
  月频: data/store/stock/moneyflow/monthly/YYYY-MM.parquet

用法:
  python scripts/fetch_moneyflow_full.py --monthly   # 月频 (推荐, 72个月)
  python scripts/fetch_moneyflow_full.py --daily     # 日频 (4000天, 较慢)
  python scripts/fetch_moneyflow_full.py --days 60   # 最近60天
"""
import sys, time, os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.db import get_store_dir
from data.symbols import CIRCLE_STOCKS
from data.assets.stock import _to_ts_code


def get_token() -> str:
    from data.tushare_utils import get_tushare_token
    return get_tushare_token()


def get_trade_calendar(start: str, end: str) -> list:
    """Get trading day list from Tushare."""
    import tushare as ts
    api = ts.pro_api(get_token())
    df = api.trade_cal(exchange="SSE", start_date=start, end_date=end)
    if df is None or len(df) == 0:
        return []
    trade_days = df[df["is_open"] == 1]["cal_date"].tolist()
    return sorted(trade_days)


def fetch_moneyflow_date(trade_date: str, store_dir: Path) -> Optional[pd.DataFrame]:
    """
    Fetch moneyflow for ALL stocks on one trading day.
    Returns DataFrame with ts_code, trade_date, buy_sm_amount, sell_sm_amount, etc.
    Caches to Parquet.
    """
    cache_path = store_dir / f"{trade_date}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    import tushare as ts
    api = ts.pro_api(get_token())

    try:
        time.sleep(0.3)  # Rate limit ~200/min
        df = api.moneyflow(trade_date=trade_date)
        if df is None or len(df) == 0:
            return None
        df.to_parquet(cache_path, index=False)
        return df
    except Exception as e:
        print(f"  ✗ {trade_date}: {type(e).__name__}: {str(e)[:60]}")
        return None


def fetch_moneyflow_range(
    dates: list,
    store_dir: Path,
    label: str = "moneyflow"
) -> dict:
    """
    Batch fetch moneyflow for a list of dates.
    Returns {date: DataFrame}.
    """
    results = {}
    total = len(dates)
    for i, d in enumerate(dates):
        df = fetch_moneyflow_date(d, store_dir)
        if df is not None:
            results[d] = df

        progress = (i + 1) / total
        if (i + 1) % 20 == 0 or i == total - 1:
            stock_count = sum(len(r) for r in results.values()) if results else 0
            print(f"  [{label}] {i+1}/{total} ({progress*100:.0f}%) — "
                  f"{len(results)} dates cached, {stock_count} rows")
    return results


def fetch_monthly_only(start: str = "20150101", end: str = "20260501"):
    """Fetch monthly moneyflow (last trading day of each month)."""
    print(f"\n{'='*60}")
    print(f"💰 Tushare Moneyflow — 月频 (每月末)")
    print(f"   范围: {start} → {end}")
    print(f"   积分: 0 (门槛2000，不消耗)")
    print(f"{'='*60}")

    store_dir = get_store_dir("stock") / "moneyflow" / "monthly"
    store_dir.mkdir(parents=True, exist_ok=True)

    all_days = get_trade_calendar(start, end)
    if not all_days:
        print("  ✗ 无法获取交易日历")
        return

    # Pick last trading day of each month
    monthly = {}
    for d in all_days:
        ym = d[:6]  # YYYYMM
        monthly[ym] = d  # keep latest for each month

    dates = sorted(monthly.values())
    print(f"   交易日总数: {len(all_days)}, 月频样本: {len(dates)}")

    results = fetch_moneyflow_range(dates, store_dir, label="月频")
    print(f"\n  ✓ 完成: {len(results)}/{len(dates)} 个月有数据")


def fetch_daily_recent(n_days: int = 60):
    """Fetch recent N trading days of moneyflow (daily granularity)."""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=n_days * 2)).strftime("%Y%m%d")

    print(f"\n{'='*60}")
    print(f"💰 Tushare Moneyflow — 日频 (最近 {n_days} 天)")
    print(f"   积分: 0 (门槛2000，不消耗)")
    print(f"{'='*60}")

    store_dir = get_store_dir("stock") / "moneyflow" / "daily"
    store_dir.mkdir(parents=True, exist_ok=True)

    all_days = get_trade_calendar(start, end)
    dates = all_days[-n_days:] if len(all_days) > n_days else all_days

    print(f"   日期范围: {dates[0]} → {dates[-1]}, 共 {len(dates)} 天")

    results = fetch_moneyflow_range(dates, store_dir, label="日频")
    print(f"\n  ✓ 完成: {len(results)}/{len(dates)} 天有数据")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Tushare 资金流向全历史下载")
    ap.add_argument("--monthly", action="store_true", help="月频 (每月末, 推荐)")
    ap.add_argument("--daily", action="store_true", help="日频 (最近60天)")
    ap.add_argument("--days", type=int, default=60, help="日频天数")
    ap.add_argument("--start", default="20150101", help="开始日期")
    ap.add_argument("--end", default="20260501", help="结束日期")
    args = ap.parse_args()

    if not args.monthly and not args.daily:
        args.monthly = True  # default

    if args.monthly:
        fetch_monthly_only(args.start, args.end)

    if args.daily:
        fetch_daily_recent(args.days)
