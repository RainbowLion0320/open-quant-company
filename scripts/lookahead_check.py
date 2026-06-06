#!/usr/bin/env python3
"""
Lookahead Bias 扫描器 — 检测策略是否使用了未来数据。

方法:
  1. 构造 "未来暴涨" 样本: 已知某股票在 T+N 日大涨
  2. 用 MarketDataView(as_of=T) 限制数据视图
  3. 验证策略不会在 T 日之前基于未来信息买入

也可以在 CI 中以小样本快速运行:
  python scripts/lookahead_check.py --quick  # 10只股票, 快速扫描

原理参照 Freqtrade lookahead-analysis 和 QuantConnect PIT 原则。
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent


def _load_candidates(n: int = 20) -> list[str]:
    """加载候选股票 (优先大盘/高流动性)。"""
    from data.market.symbols import CIRCLE_STOCKS
    symbols = list(CIRCLE_STOCKS)[:n * 10]  # pool
    from data.features.feature_store import latest_feature_frame

    # 尝试按市值排序
    try:
        df = latest_feature_frame()
        if "val_total_mv" in df.columns and "symbol" in df.columns:
            mv_map = dict(zip(df["symbol"], df["val_total_mv"]))
            symbols.sort(key=lambda s: mv_map.get(s, 0), reverse=True)
    except Exception:
        pass
    return symbols[:n]


def find_surge_events(symbol: str, min_gain_pct: float = 15.0, lookback_days: int = 252) -> list[dict]:
    """Find dates where a stock surged > min_gain_pct% in a short period (potential lookahead trap)."""
    from data.ingestion.fetcher import get_stock_daily
    df = get_stock_daily(symbol)
    if df is None or len(df) < 120:
        return []

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").tail(lookback_days)
    close = df["close"].values
    dates = df["date"].values

    events = []
    for i in range(20, len(close) - 1):
        # Check if there was a sharp rise from i-20 to i (pre-surge baseline)
        pre = close[i - 10:i].mean()
        post = close[i:i + 5].mean() if i + 5 < len(close) else close[i]
        gain = (post - pre) / pre * 100
        if gain >= min_gain_pct:
            events.append({
                "symbol": symbol,
                "date": str(dates[i])[:10],
                "pre_avg": round(float(pre), 2),
                "post_price": round(float(close[i]), 2),
                "gain_pct": round(float(gain), 1),
                "pre_window_start": str(dates[i - 10])[:10],
                "pre_window_end": str(dates[i - 1])[:10],
            })
    return events


def check_single_stock_lookahead(symbol: str) -> dict:
    """
    Check whether future data can leak through the as-of view.

    The check mutates prices after the checkpoint date by a huge factor.  A
    PIT-safe calculation through MarketDataView must be identical before and
    after that mutation.  The unsafe full-tail calculation is reported only as
    a diagnostic and is expected to differ.
    Returns lookahead indicators.
    """
    from data.ingestion.fetcher import get_stock_daily
    from data.market.market_data_view import as_of_reader
    from signals.multifactor import compute_momentum

    df = get_stock_daily(symbol)
    if df is None or len(df) < 120:
        return {"symbol": symbol, "status": "skip", "reason": "insufficient data"}

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    # Pick a checkpoint date: 2/3 through the data
    mid_idx = len(df) * 2 // 3
    check_date = df.iloc[mid_idx]["date"]
    check_str = str(check_date)[:10]

    def momentum_from_view(source_df: pd.DataFrame) -> float:
        view = as_of_reader(lambda: source_df, as_of=check_date)
        close = view.close()
        if len(close) < 21:
            return float("nan")
        mom = compute_momentum(pd.DataFrame({"close": close.values}), [21])
        return round(float(mom.get(21, np.nan)), 6)

    # ---- With PIT (correct) ----
    view = as_of_reader(lambda: df, as_of=check_date)
    pit_close = view.close()
    if len(pit_close) < 21:
        return {"symbol": symbol, "status": "skip", "reason": "too few pre-checkpoint data"}

    pit_mom_val = momentum_from_view(df)

    # ---- Mutate future rows; as-of view must be unchanged ----
    mutated = df.copy()
    future_mask = mutated["date"] > check_date
    if future_mask.any():
        mutated.loc[future_mask, "close"] = mutated.loc[future_mask, "close"] * 100.0
    protected_mom_val = momentum_from_view(mutated)

    # ---- Unsafe diagnostic: full-tail calculation should now differ ----
    unsafe_mom = compute_momentum(pd.DataFrame({"close": mutated["close"].values}), [21])
    unsafe_mom_val = round(float(unsafe_mom.get(21, np.nan)), 6)

    # ---- Difference ----
    mom_diff = abs(pit_mom_val - protected_mom_val) if not (np.isnan(pit_mom_val) or np.isnan(protected_mom_val)) else 0
    unsafe_diff = abs(pit_mom_val - unsafe_mom_val) if not (np.isnan(pit_mom_val) or np.isnan(unsafe_mom_val)) else 0

    return {
        "symbol": symbol,
        "check_date": check_str,
        "status": "ok",
        "pit_momentum": pit_mom_val,
        "protected_momentum": protected_mom_val,
        "unsafe_full_momentum": unsafe_mom_val,
        "mom_diff": round(mom_diff, 6),
        "unsafe_tail_diff": round(unsafe_diff, 6),
        "lookahead_flag": mom_diff > 1e-9,
    }


def run_quick_check(n_stocks: int = 10):
    """Quick lookahead scan suitable for CI."""
    print(f"{'='*60}")
    print(f"Lookahead Bias 扫描器 — {n_stocks} 只股票快速检测")
    print(f"{'='*60}\n")

    symbols = _load_candidates(n_stocks)
    print(f"候选股票: {len(symbols)} 只")

    results = []
    flags = 0

    for i, sym in enumerate(symbols, 1):
        r = check_single_stock_lookahead(sym)
        results.append(r)
        if r.get("lookahead_flag"):
            flags += 1
            print(f"  [{i:2d}/{len(symbols)}] {sym:6s} ⚠️  PIT={r['pit_momentum']} protected={r['protected_momentum']} diff={r['mom_diff']}")
        elif r["status"] == "skip":
            print(f"  [{i:2d}/{len(symbols)}] {sym:6s} ⊘ {r['reason']}")
        else:
            print(f"  [{i:2d}/{len(symbols)}] {sym:6s} ✓  PIT={r['pit_momentum']} unsafe_tail_diff={r['unsafe_tail_diff']}")

    print(f"\n{'='*60}")
    print(f"结果: {flags}/{len(symbols)} 只有差异 (可能的前视偏差)")
    if flags > 0:
        print(f"⚠️ 请检查动量计算是否在完整历史上使用了未来数据")
    else:
        print(f"✓ 未检测到前视偏差")

    # Also find surge events for manual inspection
    print(f"\n── 未来暴涨事件扫描 (潜在 lookahead trap) ──")
    surge_count = 0
    for sym in symbols[:5]:
        events = find_surge_events(sym, min_gain_pct=20.0)
        for ev in events[:2]:
            surge_count += 1
            print(f"  {ev['symbol']} {ev['date']}: +{ev['gain_pct']}% (前{ev['pre_window_start']}~{ev['pre_window_end']}均价{ev['pre_avg']})")
    if surge_count == 0:
        print(f"  未发现显著暴涨事件")

    return results


def run_deep_check(symbol: str = "600519"):
    """Deep check: run a mini backtest with and without PIT on a single stock."""
    print(f"\n{'='*60}")
    print(f"深度 PIT 检查: {symbol}")
    print(f"{'='*60}")

    from data.ingestion.fetcher import get_stock_daily
    from data.market.market_data_view import MarketDataView

    df = get_stock_daily(symbol)
    if df is None or len(df) < 252:
        print(f"数据不足")
        return

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    # Run through all dates, check momentum with PIT vs full data
    dates = df["date"].tail(60)
    diffs = []
    for dt in dates:
        view = MarketDataView(df, as_of=dt)
        pit_close = view.close()
        if len(pit_close) < 21:
            continue
        from signals.multifactor import compute_momentum
        pit_mom = compute_momentum(pd.DataFrame({"close": pit_close.values}), [21])
        mutated = df.copy()
        mutated.loc[mutated["date"] > dt, "close"] = mutated.loc[mutated["date"] > dt, "close"] * 100.0
        protected = MarketDataView(mutated, as_of=dt).close()
        protected_mom = compute_momentum(pd.DataFrame({"close": protected.values}), [21])
        d = abs(pit_mom.get(21, 0) - protected_mom.get(21, 0)) if 21 in pit_mom else 0
        diffs.append(d)

    if diffs:
        max_diff = max(diffs)
        mean_diff = np.mean(diffs)
        print(f"  日期数: {len(diffs)}")
        print(f"  最大PIT差异: {max_diff:.6f}")
        print(f"  平均PIT差异: {mean_diff:.6f}")
        if max_diff < 0.001:
            print(f"  ✓ PIT 保护有效 (差异可忽略)")
        else:
            print(f"  ⚠️ 存在显著差异, 需排查")
            # Show the date with max diff
            max_idx = np.argmax(diffs)
            print(f"  最大差异日期: {dates.iloc[max_idx].strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Lookahead Bias Scanner")
    ap.add_argument("--quick", action="store_true", default=True, help="快速扫描 (10只)")
    ap.add_argument("--deep", type=str, default="", help="深度检查单只股票 (e.g. 600519)")
    ap.add_argument("--n", type=int, default=10, help="快速扫描股票数")
    args = ap.parse_args()

    if args.deep:
        run_deep_check(args.deep)
    else:
        run_quick_check(n_stocks=args.n)
