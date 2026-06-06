"""
Cron: 后台拉取限流数据

每天自动拉取受 Tushare 频次限制的数据:
  - limit_list (涨跌停, 1次/小时)
  - research_report (研报)

用法:
  python scripts/cron_fetch_slow.py
  # 或通过 Hermes cronjob 定时执行
"""
import sys, time, calendar
from pathlib import Path
from datetime import datetime, timedelta


import pandas as pd
import tushare as ts
from data.storage.datahub import get_datahub
from data.ingestion.tushare_utils import get_tushare_token

HUB = get_datahub()


def fetch_limit_list(force: bool = False):
    """
    拉取最新一天的涨跌停数据。
    1次/小时限流 → 每次只拉1天。
    """
    api = ts.pro_api(get_tushare_token())
    store = HUB.store_dir("stock") / "limit_list"
    store.mkdir(parents=True, exist_ok=True)

    # Get the most recent date NOT already cached
    cal = api.trade_cal(exchange="SSE", start_date="20240101", end_date=datetime.now().strftime("%Y%m%d"))
    trade_days = sorted(cal[cal["is_open"] == 1]["cal_date"].tolist(), reverse=True)

    fetched = 0
    attempted = 0
    for d in trade_days[:5]:  # Try up to 5 recent dates, but call API at most once
        pq_path = store / f"{d}.parquet"
        cached = HUB.read_parquet(pq_path, default=pd.DataFrame())
        if not force and pq_path.exists() and cached is not None and cached.memory_usage().sum() > 0:
            continue

        try:
            if attempted:
                time.sleep(3650)  # 1次/小时限流, 留余量
            attempted += 1
            df = api.limit_list_d(trade_date=d, limit_type="U")
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq_path)
                fetched += 1
                print(f"  [limit_list] ✓ {d}: {len(df)} records")
        except Exception as e:
            print(f"  [limit_list] ✗ {d}: {e}")
        break

    return fetched


def fetch_research_report(force: bool = False):
    """拉取最近一个月的研报数据。"""
    api = ts.pro_api(get_tushare_token())
    store = HUB.store_dir("stock") / "research_report"
    store.mkdir(parents=True, exist_ok=True)

    mon = datetime.now().strftime("%Y%m")
    pq_path = store / f"{mon}.parquet"
    cached = HUB.read_parquet(pq_path, default=pd.DataFrame())
    if not force and pq_path.exists() and cached is not None and len(cached) > 100:
        print(f"  [research] ✓ {mon}: already cached")
        return 0

    try:
        time.sleep(0.5)
        start = f"{mon}01"
        end = f"{mon}{calendar.monthrange(int(mon[:4]), int(mon[4:6]))[1]:02d}"
        df = api.research_report(start_date=start, end_date=end)
        if df is not None and len(df) > 0:
            HUB.write_parquet(df, pq_path)
            print(f"  [research] ✓ {mon}: {len(df)} records")
            return 1
    except Exception as e:
        print(f"  [research] ✗ {mon}: {e}")
    return 0


if __name__ == "__main__":
    print(f"🔄 Cron: 限流数据拉取 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    fetched = 0
    fetched += fetch_limit_list()
    fetched += fetch_research_report()

    print(f"\n✓ Done: {fetched} new data points")
