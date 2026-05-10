#!/usr/bin/env python3
"""
巴菲特金叉策略回测 — 真实数据版

用法:
    python backtest/run_ma_cross.py                    # 默认参数
    python backtest/run_ma_cross.py --start 2022-01-01 # 自定义起止
    python backtest/run_ma_cross.py --pool 600519,000858,600036  # 自定义股票池
"""
import os, sys, time
sys.path.insert(0, os.path.expanduser("~/quant-agent"))

# 模块级代理清理
for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

import argparse
import backtrader as bt
import pandas as pd
from datetime import datetime

from data.fetcher import get_stock_daily, get_index_daily
from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY
from data.financials import get_buffett_inputs
from buffett.filters import buffett_filter, Verdict
from cybernetics.orchestrator import QuantOrchestrator
from backtest.strategies.ma_cross import BuffettMACross


def fetch_stock_data(symbol, start="2020-01-01", end=None):
    """获取股票日线数据并转为 Backtrader feed"""
    df = get_stock_daily(symbol)
    if df is None or len(df) == 0:
        return None

    # 列名统一: date → datetime, 其余 Backtrader 标准列保留
    df = df.rename(columns={"date": "datetime"})
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()

    # 时间范围过滤
    df = df.loc[start:end] if end else df.loc[start:]
    if len(df) < 100:
        return None

    data = bt.feeds.PandasData(
        dataname=df,
        name=symbol,
        plot=False,
    )
    return data


def fetch_benchmark_data(start="2020-01-01", end=None):
    """获取上证指数作为基准"""
    df = get_index_daily("sh000001")
    if df is None or len(df) == 0:
        return None

    df = df.rename(columns={"date": "datetime"})
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    df = df.loc[start:end] if end else df.loc[start:]
    return df


def get_approved_stocks():
    """通过巴菲特过滤器的股票列表"""
    all_stocks = sorted(CIRCLE_STOCKS)
    approved = []

    print("🔍 巴菲特过滤器扫描...")
    for i, symbol in enumerate(all_stocks):
        industry = SYMBOL_INDUSTRY.get(symbol, "未知")

        try:
            inputs = get_buffett_inputs(symbol, current_price=0, industry=industry)
            if not inputs.get("roe_history"):
                continue
            result = buffett_filter(symbol=symbol, name=symbol, **inputs)
            icon = "✅" if result.verdict == Verdict.PASS else "❌"
            print(f"  [{i+1:2d}/25] {symbol} {icon} {result.verdict.value} (评分:{result.score})")
            if result.verdict == Verdict.PASS:
                approved.append(symbol)
        except Exception as e:
            print(f"  [{i+1:2d}/25] {symbol} ⚠️ 跳过: {e}")
        time.sleep(1)

    return approved


def run_backtest(stocks, start="2020-01-01", end=None, cash=1_000_000):
    """运行 Backtrader 回测"""
    cerebro = bt.Cerebro()

    # 获取市场状态 → 自适应参数
    orch = QuantOrchestrator()
    orch.set_regime()
    params = orch.get_params()
    print(f"\n📈 市场状态: {orch.regime.value}")
    print(f"   自适应参数: {params}")

    # 策略
    cerebro.addstrategy(
        BuffettMACross,
        position_pct=params.get("position_size", 0.15),
        stop_loss=params.get("stop_loss", -0.05),
        max_positions=params.get("max_positions", 5),
        print_trades=False,
    )

    # 初始资金
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.0003)  # 万三

    # 添加数据
    loaded = 0
    for symbol in stocks:
        data = fetch_stock_data(symbol, start=start, end=end)
        if data is not None:
            cerebro.adddata(data)
            loaded += 1
            # Backtrader data lengths available via other means
            print(f"  加载 {symbol}: OK")

    if loaded == 0:
        print("❌ 没有加载到任何数据")
        return

    # 基准：买入持有上证指数的回报
    bench_df = fetch_benchmark_data(start=start, end=end)
    bench_return = 0
    if bench_df is not None and len(bench_df) > 0:
        bench_return = (bench_df["close"].iloc[-1] / bench_df["close"].iloc[0] - 1) * 100
        print(f"  基准(上证):{bench_return:.2f}%")

    # 运行
    print(f"\n⚡ 运行回测: {loaded} 只股票, {cash/10000:.0f}万初始资金")
    start_val = cerebro.broker.getvalue()
    results = cerebro.run()
    end_val = cerebro.broker.getvalue()

    # 结果
    strategy = results[0]
    total_return = (end_val / start_val - 1) * 100
    alpha = total_return - bench_return

    print(f"\n{'='*60}")
    print(f"回测结果")
    print(f"{'='*60}")
    print(f"  初始资金:    {start_val:,.0f}")
    print(f"  最终资产:    {end_val:,.0f}")
    print(f"  总回报率:    {total_return:+.2f}%")
    print(f"  上证基准:    {bench_return:+.2f}%")
    print(f"  超额收益α:   {alpha:+.2f}%")
    print(f"  总交易次数:  {strategy.trade_count}")
    print(f"  策略股票数:  {loaded}")
    wdl = f"+{total_return:.1f}% vs 基准{bench_return:+.1f}% → α={alpha:+.1f}%"
    print(f"  Sharpe预估:  {'优秀' if alpha > 10 else '良好' if alpha > 0 else '不足'} ({wdl})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="巴菲特金叉策略回测")
    parser.add_argument("--start", default="2020-01-01", help="回测起始日期")
    parser.add_argument("--end", default=None, help="回测结束日期")
    parser.add_argument("--pool", default=None, help="自定义股票池 (逗号分隔)")
    parser.add_argument("--cash", type=float, default=1_000_000, help="初始资金")
    parser.add_argument("--skip-filter", action="store_true", help="跳过巴菲特过滤器，直接用全量股票池")
    args = parser.parse_args()

    if args.pool:
        stocks = [s.strip() for s in args.pool.split(",")]
        print(f"📋 自定义股票池: {stocks}")
    elif args.skip_filter:
        stocks = sorted(CIRCLE_STOCKS)
        print(f"📋 全量股票池: {len(stocks)} 只 (跳过过滤器)")
    else:
        stocks = get_approved_stocks()
        if not stocks:
            print("⚠️ 没有股票通过巴菲特过滤器，使用全量股票池回退")
            stocks = sorted(CIRCLE_STOCKS)

    print(f"\n🎯 回测股票: {stocks}")
    run_backtest(stocks, start=args.start, end=args.end, cash=args.cash)
