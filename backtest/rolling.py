"""
滚动窗口回测 — 消除前视偏差

每年用当时已有的财务数据重跑巴菲特过滤器，动态调整精选池，
然后在后续期间回测。模拟真实投资决策流程。
"""
import os, sys, time
sys.path.insert(0, os.path.expanduser("~/quant-agent"))

for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from data.fetcher import get_stock_daily, get_index_daily
from data.financials import (
    get_financial_summary, extract_roe_history, extract_gross_margin_history,
    extract_net_margin_history, extract_debt_equity_ratio, extract_latest_net_profit,
)
from data.symbols import SYMBOL_SECTOR, FALLBACK_SECTOR, CIRCLE_STOCKS, SYMBOL_NAME, SYMBOL_INDUSTRY
from buffett.filters import buffett_filter, Verdict
from backtest.strategies.cybernetic import CyberneticStrategy, make_regime_data


def filter_as_of(universal_pool, as_of_year):
    """
    用 'as_of_year' 年前的财务数据跑巴菲特过滤器
    例: as_of_year=2015 → 只用 2010-2014 的年报数据
    """
    results = []
    for symbol in universal_pool:
        try:
            df = get_financial_summary(symbol)
            if df is None or len(df) == 0:
                continue

            # 只保留 as_of_year 之前的年报
            report_col = "报告期"
            df[report_col] = pd.to_datetime(df[report_col])
            cutoff = pd.Timestamp(f"{as_of_year-1}-12-31")
            historical = df[df[report_col] <= cutoff].copy()

            if len(historical) < 5:
                continue  # 至少5年数据

            roe = extract_roe_history(historical)
            gm = extract_gross_margin_history(historical)
            nm = extract_net_margin_history(historical)
            debt = extract_debt_equity_ratio(historical)
            net_profit = extract_latest_net_profit(historical)

            if not roe:
                continue

            industry = SYMBOL_INDUSTRY.get(symbol, "待分类")
            sector = SYMBOL_SECTOR.get(symbol, FALLBACK_SECTOR)
            name = SYMBOL_NAME.get(symbol, symbol)

            result = buffett_filter(
                symbol=symbol, name=name, industry=industry, sector=sector,
                fcf=net_profit * 0.7, roe_history=roe,
                gross_margin_history=gm, net_margin_history=nm,
                debt_equity=debt, current_price=0,
            )
            results.append(result)
        except Exception:
            pass
    return results


def rolling_backtest(start_year=2015, end_year=2026, cash=1_000_000):
    """滚动窗口回测"""
    universal = CIRCLE_STOCKS  # Top500

    # 逐年的过滤结果
    yearly_pools = {}
    print("逐年巴菲特过滤 (消除前视偏差):")
    print("=" * 60)
    for year in range(start_year, end_year):
        results = filter_as_of(universal, year)
        passed = [r for r in results if r.verdict == Verdict.PASS]
        yearly_pools[year] = passed
        print(f"  {year}年(用{year-5}~{year-1}财报): "
              f"{len(passed)}/{len(results)}只通过  "
              f"例: {passed[0].symbol} {passed[0].name}" if passed
              else f"  {year}年(用{year-5}~{year-1}财报): 0只通过 ⚠️")

    # 汇总：每年池子中出现的所有股票
    all_stocks = set()
    for pool in yearly_pools.values():
        for r in pool:
            all_stocks.add(r.symbol)

    print(f"\n滚动筛选覆盖: {len(all_stocks)} 只不同股票")
    print(f"{'='*60}")

    # 按年份加载价格数据并回测
    print("\n滚动窗口回测...")
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(0.0003)

    # 加载基准 + 生成 regime
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    bench = bench.set_index("date").sort_index()
    b = bench.loc[f"{start_year}-01-01":f"{end_year-1}-12-31"]
    regime_df = make_regime_data(b)
    rdata = bt.feeds.PandasData(dataname=regime_df, name="REGIME")

    # 加载所有出现过股票的完整数据
    loaded = 0
    for symbol in sorted(all_stocks):
        try:
            df = get_stock_daily(symbol)
        except Exception:
            print(f"  ⚠️ {symbol} 数据拉取失败, 跳过")
            continue
        if df is None or len(df) < 200:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.loc[f"{start_year}-01-01":f"{end_year-1}-12-31"]
        if len(df) < 200:
            continue
        name = SYMBOL_NAME.get(symbol, symbol)
        data = bt.feeds.PandasData(dataname=df, name=f"{symbol}_{name}")
        cerebro.adddata(data)
        loaded += 1

    # 加 regime 在最后
    regime_idx = loaded
    cerebro.adddata(rdata)

    cerebro.addstrategy(CyberneticStrategy, regime_data_idx=regime_idx, score_weight=True)
    sv = cerebro.broker.getvalue()
    results = cerebro.run()
    ev = cerebro.broker.getvalue()
    strat = results[0]

    # 基准收益
    bench_ret = (b["close"].iloc[-1] / b["close"].iloc[0] - 1) * 100 if len(b) > 0 else 0

    total_ret = (ev / sv - 1) * 100
    print(f"\n滚动回测 {start_year}-{end_year}:")
    print(f"  策略: {total_ret:+.2f}%  基准: {bench_ret:+.2f}%  α: {total_ret-bench_ret:+.2f}%")
    print(f"  交易: {strat.trades}  加载: {loaded}只")

    return yearly_pools, total_ret, bench_ret


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2015)
    p.add_argument("--end", type=int, default=2026)
    args = p.parse_args()
    rolling_backtest(args.start, args.end)
