#!/usr/bin/env python3
"""
Pandas 月度调仓回测 — 多因子打分 + 控制论仓位管理

避开 Backtrader 多 feed 对齐问题
每月末: 计算所有股票因子得分 → 选 Top-N → 调仓
"""
import os, sys
sys.path.insert(0, os.path.expanduser("~/quant-agent"))
for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

import pandas as pd
import numpy as np
from datetime import datetime

from data.fetcher import get_stock_daily, get_index_daily


def load_all_stocks(symbols, start, end):
    """加载所有股票，对齐到统一日期索引"""
    dfs = {}
    for sym in symbols:
        try:
            df = get_stock_daily(sym)
        except Exception:
            continue
        if df is None or len(df) < 200:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if len(df) < 200:
            continue
        dfs[sym] = df["close"].rename(sym)
    if not dfs:
        return None
    return pd.concat(dfs.values(), axis=1, keys=dfs.keys())


def detect_regime(benchmark_close, i, window=60):
    """检测第 i 天的市场状态"""
    if i < window:
        return 0
    c = benchmark_close[i]
    ma5 = np.mean(benchmark_close[i-5:i])
    ma20 = np.mean(benchmark_close[i-20:i])
    ma60 = np.mean(benchmark_close[i-60:i])
    if c > ma5 > ma20 > ma60:
        return 1
    elif c < ma5 < ma20 < ma60:
        return -1
    return 0


def multi_factor_score(stock_series, i, lookback=60):
    """单只股票在第 i 天的多因子得分"""
    close = stock_series[:i+1].values
    if len(close) < lookback:
        return 0

    current = close[-1]
    # 1月动量
    mom_1m = (current / close[-21] - 1) if len(close) >= 21 else 0
    # 3月动量
    mom_3m = (current / close[-min(lookback, len(close))] - 1)
    # 波动率 (20日)
    rets = np.diff(close[-21:]) / close[-21:-1]
    vol = np.std(rets) * np.sqrt(252) if len(rets) > 0 else 0.3

    # 综合: 正动量 + 低波动 = 高分
    score = 50 + mom_1m * 100 + mom_3m * 50 - vol * 30
    return max(0, min(100, score))


def backtest(pool, start="2015-01-01", end="2026-05-10", cash=1_000_000):
    """月度调仓回测"""
    print(f"加载数据 {start} ~ {end}...")
    prices = load_all_stocks(pool, start, end)
    if prices is None:
        print("无数据")
        return

    # 基准
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    bench = bench.set_index("date").sort_index()
    bc = bench["close"].loc[pd.Timestamp(start):pd.Timestamp(end)]

    # 月初调仓日
    prices_monthly = prices.resample("MS").last()
    n_months = len(prices_monthly)

    # 回测状态
    portfolio_value = cash
    holdings = {}  # {symbol: shares}
    trade_log = []

    print(f"月度调仓 {n_months} 期...")
    for m in range(n_months):
        month_dt = prices_monthly.index[m]
        # 在原始日频数据中找到这个月的位置
        try:
            i = prices.index.get_indexer([month_dt], method="pad")[0]
            if i < 0:
                continue
        except Exception:
            continue

        # 市场状态
        if m > 0:
            ri = bc.index.get_indexer([month_dt], method="pad")[0]
            regime = detect_regime(bc.values, ri) if ri >= 0 else 0
        else:
            regime = 0

        # 仓位参数
        if regime > 0:
            pos_pct, max_pos = 0.30, 8
        elif regime < 0:
            pos_pct, max_pos = 0.05, 2
        else:
            pos_pct, max_pos = 0.15, 5

        # 计算所有股票得分
        scores = {}
        for sym in pool:
            if sym not in prices.columns:
                continue
            s = prices[sym]
            try:
                idx = s.index.get_indexer([month_dt], method="pad")[0]
                if idx < 0:
                    continue
            except Exception:
                continue
            score = multi_factor_score(s, idx)
            if score > 0:
                scores[sym] = score

        if not scores:
            continue

        # 选 Top-N
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        target = {s for s, _ in ranked[:max_pos]}

        # 卖出
        current_price = prices.iloc[i]
        for sym in list(holdings.keys()):
            if sym not in target:
                if sym in current_price and not pd.isna(current_price[sym]):
                    p = current_price[sym]
                    portfolio_value += holdings[sym] * p
                    trade_log.append((month_dt, "SELL", sym, holdings[sym], p))
                    del holdings[sym]

        # 买入
        value_per_stock = portfolio_value * pos_pct / max(1, len(target) + len(holdings))
        for sym in target:
            if sym not in holdings and sym in current_price and not pd.isna(current_price[sym]):
                p = current_price[sym]
                shares = int(value_per_stock / p // 100) * 100
                if shares >= 100:
                    cost = shares * p * 1.0003
                    if cost <= portfolio_value:
                        holdings[sym] = shares
                        portfolio_value -= cost
                        trade_log.append((month_dt, "BUY", sym, shares, p))

    # 期末清算
    final_prices = prices.iloc[-1]
    for sym, shares in holdings.items():
        if sym in final_prices and not pd.isna(final_prices[sym]):
            portfolio_value += shares * final_prices[sym]

    total_ret = (portfolio_value / cash - 1) * 100
    bench_ret = (bc.iloc[-1] / bc.iloc[0] - 1) * 100

    print(f"\n{'='*60}")
    print(f"多因子月度调仓 {start[:4]}-{end[:4]}")
    print(f"{'='*60}")
    print(f"  策略: {total_ret:+.2f}%  基准: {bench_ret:+.2f}%  α: {total_ret-bench_ret:+.2f}%")
    print(f"  交易: {len(trade_log)} 笔")
    print(f"  期末持仓: {len(holdings)} 只")
    if holdings:
        print(f"  持仓: {list(holdings.keys())[:5]}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default="2026-05-10")
    args = p.parse_args()

    pool = ["601225","603288","600938","002415","601838","002555","600989","600036",
            "002142","600926","600919","601009","601128","601939","601665","600999",
            "601288","601577","002736","600030","601066","601688","601601","601318","601878"]
    backtest(pool, args.start, args.end)
