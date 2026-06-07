"""
Cron: 批量拉取 Tushare Free 扩展数据

拉取8个新启用的数据维度到本地 parquet:
  - limit_list (涨跌停, 1次/小时)
  - top_list   (龙虎榜)
  - research_report (券商研报)
  - dividend   (分红送股)
  - fund_daily (基金日线)
  - fund_portfolio (基金持仓)
  - fund_nav   (基金净值)
  - futures_daily (期货日线)

用法:
  python scripts/cron_fetch_extra.py                # 增量拉取
  python scripts/cron_fetch_extra.py --full-history # 全量拉取
"""
import sys, time, argparse, calendar
from pathlib import Path
from datetime import datetime, timedelta


import pandas as pd
import tushare as ts
from data.ingestion.tushare_coverage import tushare_etf_ts_codes, tushare_futures_ts_codes
from data.storage.datahub import get_datahub
from data.ingestion.tushare_utils import get_tushare_token

HUB = get_datahub()
TOKEN = get_tushare_token()

# Paths
STORE = HUB.store_root
LIMIT_STORE    = STORE / "stock" / "limit_list"
TOP_STORE      = STORE / "stock" / "top_list"
RESEARCH_STORE = STORE / "stock" / "research_report"
DIV_STORE      = STORE / "stock" / "dividend"
FUND_D_STORE   = STORE / "fund" / "daily"
FUND_P_STORE   = STORE / "fund" / "portfolio"
FUND_N_STORE   = STORE / "fund" / "nav"
FUT_STORE      = STORE / "futures" / "daily"

for d in [LIMIT_STORE, TOP_STORE, RESEARCH_STORE, DIV_STORE,
          FUND_D_STORE, FUND_P_STORE, FUND_N_STORE, FUT_STORE]:
    d.mkdir(parents=True, exist_ok=True)


def api():
    return ts.pro_api(TOKEN)

def _throttle(secs=0.5):
    time.sleep(secs)


FUTURES_TUSHARE_EXCHANGE = {
    "IF": "CFX",
    "IC": "CFX",
    "IH": "CFX",
    "IM": "CFX",
    "T": "CFX",
    "TF": "CFX",
    "TS": "CFX",
    "RB": "SHF",
    "AU": "SHF",
    "CU": "SHF",
    "SC": "INE",
}


# ═══════════════════════════════════════
# 1. limit_list — 涨跌停 (1次/小时, 增量每次最多请求1天)
# ═══════════════════════════════════════
def fetch_limit_list(full_history=False, max_requests: int | None = None):
    """拉取涨跌停数据。full_history 时拉全部交易日。"""
    api_ = api()
    # Get trade calendar
    today = datetime.now().strftime("%Y%m%d")
    cal = api_.trade_cal(exchange="SSE", start_date="20150101", end_date=today)
    trade_days = sorted(cal[cal["is_open"] == 1]["cal_date"].tolist(), reverse=True)

    if not full_history:
        trade_days = trade_days[:2]  # 1/hr limit — cron accumulates daily
        max_requests = 1 if max_requests is None else max_requests

    fetched = 0
    attempted = 0
    for d in trade_days:
        if max_requests is not None and attempted >= max_requests:
            break
        pq = LIMIT_STORE / f"{d}.parquet"
        if pq.exists():
            continue
        try:
            if attempted:
                _throttle(3650)  # 1次/小时 限流, 留余量
            attempted += 1
            df = api_.limit_list_d(trade_date=d, limit_type="U")
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
                if fetched % 5 == 0:
                    print(f"  [limit_list] {fetched} days ...")
        except Exception as e:
            print(f"  [limit_list] {d}: {e}")
    print(f"  [limit_list] done: {fetched} new days")
    return fetched


# ═══════════════════════════════════════
# 2. top_list — 龙虎榜
# ═══════════════════════════════════════
def fetch_top_list(full_history=False):
    api_ = api()
    cal = api_.trade_cal(exchange="SSE", start_date="20150101", end_date=datetime.now().strftime("%Y%m%d"))
    trade_days = sorted(cal[cal["is_open"] == 1]["cal_date"].tolist(), reverse=True)
    if not full_history:
        trade_days = trade_days[:60]

    fetched = 0
    for d in trade_days:
        pq = TOP_STORE / f"{d}.parquet"
        if pq.exists():
            continue
        try:
            _throttle(0.5)
            df = api_.top_list(trade_date=d)
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
        except Exception as e:
            print(f"  [top_list] {d}: {e}")
    print(f"  [top_list] done: {fetched} new days")
    return fetched


# ═══════════════════════════════════════
# 3. research_report — 券商研报
# ═══════════════════════════════════════
def fetch_research_report(full_history=False):
    api_ = api()
    now = datetime.now()
    months = []
    if full_history:
        for y in range(2017, now.year + 1):
            for m in range(1, 13):
                if y == now.year and m > now.month:
                    break
                months.append(f"{y}{m:02d}")
    else:
        for i in range(3):
            d = now - timedelta(days=90 * i)
            months.append(d.strftime("%Y%m"))

    fetched = 0
    for mon in sorted(months):
        pq = RESEARCH_STORE / f"{mon}.parquet"
        if pq.exists():
            continue
        try:
            _throttle(0.5)
            year, month = int(mon[:4]), int(mon[4:6])
            last_day = calendar.monthrange(year, month)[1]
            df = api_.research_report(start_date=f"{mon}01", end_date=f"{mon}{last_day:02d}")
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
                print(f"  [research] {mon}: {len(df)} records")
        except Exception as e:
            print(f"  [research] {mon}: {e}")
    print(f"  [research] done: {fetched} new months")
    return fetched


# ═══════════════════════════════════════
# 4. dividend — 分红送股 (全量一次拉取)
# ═══════════════════════════════════════
def fetch_dividend(full_history=False):
    api_ = api()
    pq = DIV_STORE / "all_dividends.parquet"
    if pq.exists() and not full_history:
        print(f"  [dividend] already cached")
        return 0
    try:
        dfs = []
        for year in range(2010, datetime.now().year + 1):
            try:
                _throttle(0.5)
                df = api_.dividend(start_date=f"{year}0101", end_date=f"{year}1231")
                if df is not None and len(df) > 0:
                    dfs.append(df)
                    print(f"  [dividend] {year}: {len(df)} records")
            except Exception:
                pass
        if dfs:
            all_df = pd.concat(dfs, ignore_index=True)
            HUB.write_parquet(all_df, pq)
            print(f"  [dividend] total {len(all_df)} records ({len(dfs)} years)")
            return len(dfs)
    except Exception as e:
        print(f"  [dividend] error: {e}")
    return 0


# ═══════════════════════════════════════
# 5. fund_daily — 基金日线 (分批拉取)
# ═══════════════════════════════════════
def fetch_fund_daily(full_history=False):
    """拉取项目 ETF universe 日线。"""
    api_ = api()
    fetched = 0
    for code in tushare_etf_ts_codes():
        pq = FUND_D_STORE / f"{code}.parquet"
        if pq.exists() and not full_history:
            continue
        try:
            _throttle(0.5)
            df = api_.fund_daily(ts_code=code)
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
                print(f"  [fund_daily] {code}: {len(df)} rows")
        except Exception as e:
            print(f"  [fund_daily] {code}: {e}")
    print(f"  [fund_daily] done: {fetched} funds")
    return fetched


# ═══════════════════════════════════════
# 6. fund_portfolio — 基金持仓 (季度)
# ═══════════════════════════════════════
def fetch_fund_portfolio(full_history=False):
    api_ = api()
    today = datetime.now()
    quarter_ends = [(3, 31), (6, 30), (9, 30), (12, 31)]
    periods = []
    for year in range(2020 if full_history else today.year - 1, today.year + 1):
        for month, day in quarter_ends:
            dt = datetime(year, month, day)
            if dt.date() <= today.date():
                periods.append(dt.strftime("%Y%m%d"))
    periods = sorted(periods, reverse=True)
    if not full_history:
        periods = periods[:4]

    fetched = 0
    missing = [p for p in periods if not (FUND_P_STORE / f"{p}.parquet").exists()]
    if not missing and not full_history:
        print(f"  [fund_portfolio] already cached")
        return 0
    try:
        for period in periods:
            pq = FUND_P_STORE / f"{period}.parquet"
            if pq.exists() and not full_history:
                continue
            _throttle(0.5)
            df = api_.fund_portfolio(period=period)
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
                print(f"  [fund_portfolio] {period}: {len(df)} records")
    except Exception as e:
        print(f"  [fund_portfolio] error: {e}")
    print(f"  [fund_portfolio] done: {fetched} periods")
    return fetched


# ═══════════════════════════════════════
# 7. fund_nav — 基金净值
# ═══════════════════════════════════════
def fetch_fund_nav(full_history=False):
    api_ = api()
    fetched = 0
    for code in tushare_etf_ts_codes():
        pq = FUND_N_STORE / f"{code}.parquet"
        if pq.exists() and not full_history:
            continue
        try:
            _throttle(0.5)
            df = api_.fund_nav(ts_code=code)
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
                print(f"  [fund_nav] {code}: {len(df)} rows")
        except Exception as e:
            print(f"  [fund_nav] {code}: {e}")
    print(f"  [fund_nav] done: {fetched} funds")
    return fetched


# ═══════════════════════════════════════
# 8. futures_daily — 期货日线
# ═══════════════════════════════════════
def fetch_futures_daily(full_history=False):
    api_ = api()
    fetched = 0
    for ct in tushare_futures_ts_codes():
        pq = FUT_STORE / f"{ct}.parquet"
        if pq.exists() and not full_history:
            continue
        try:
            _throttle(0.5)
            df = api_.fut_daily(ts_code=ct)
            if df is not None and len(df) > 0:
                HUB.write_parquet(df, pq)
                fetched += 1
                print(f"  [futures] {ct}: {len(df)} rows")
        except Exception as e:
            print(f"  [futures] {ct}: {e}")
    print(f"  [futures] done: {fetched} contracts")
    return fetched


# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Tushare Free extra data dimensions")
    parser.add_argument("--full-history", action="store_true", help="Full historical fetch")
    parser.add_argument("--skip-slow", action="store_true", help="Skip rate-limited fetchers (limit_list/top_list)")
    parser.add_argument("--slow-only", action="store_true", help="ONLY fetch rate-limited slow dimensions (cron_accumulate)")
    args = parser.parse_args()

    full = args.full_history
    print(f"Cron fetch extra data — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Full history: {full}, slow-only: {args.slow_only}")
    print("=" * 55)

    results = {}

    if args.slow_only:
        # Only the slow, rate-limited dimensions (daily cron accumulation)
        results["limit_list"] = fetch_limit_list(full)
        results["top_list"] = fetch_top_list(full)
    else:
        results["dividend"] = fetch_dividend(full)
        results["research_report"] = fetch_research_report(full)
        results["fund_daily"] = fetch_fund_daily(full)
        results["fund_portfolio"] = fetch_fund_portfolio(full)
        results["fund_nav"] = fetch_fund_nav(full)
        results["futures_daily"] = fetch_futures_daily(full)

        if not args.skip_slow:
            results["limit_list"] = fetch_limit_list(full)
            results["top_list"] = fetch_top_list(full)

    total = sum(v for v in results.values() if isinstance(v, int))
    print(f"\nDone: {total} new data points fetched")
