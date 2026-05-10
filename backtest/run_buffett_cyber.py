#!/usr/bin/env python3
"""
巴菲特+控制论综合策略回测

用法:
  python backtest/run_buffett_cyber.py              # 默认参数
  python backtest/run_buffett_cyber.py --optimize    # 网格搜索最优参数
"""
import os, sys, time, itertools
sys.path.insert(0, os.path.expanduser("~/quant-agent"))

for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

import argparse
import backtrader as bt
import pandas as pd

from data.fetcher import get_stock_daily, get_index_daily
from backtest.strategies.buffett_cyber import BuffettCyberStrategy, make_data_name


# ============================================================
# 巴菲特精选池 (最新扫描结果, Top500, 25只)
# ============================================================
BUFFETT_POOL = [
    ("601225", "陕西煤业", 91), ("603288", "海天味业", 91),
    ("600938", "中国海油", 90), ("002415", "海康威视", 88),
    ("601838", "成都银行", 88), ("002555", "三七互娱", 87),
    ("600989", "宝丰能源", 85), ("600036", "招商银行", 82),
    ("002142", "宁波银行", 81), ("600926", "杭州银行", 80),
    ("600919", "江苏银行", 79), ("601009", "南京银行", 79),
    ("601128", "常熟银行", 77), ("601939", "建设银行", 77),
    ("601665", "齐鲁银行", 76), ("600999", "招商证券", 75),
    ("601288", "农业银行", 75), ("601577", "长沙银行", 75),
    ("002736", "国信证券", 74), ("600030", "中信证券", 73),
    ("601066", "中信建投", 73), ("601688", "华泰证券", 73),
    ("601601", "中国太保", 69), ("601318", "中国平安", 68),
    ("601878", "浙商证券", 64),
]


def load_data(symbols_with_scores, start, end):
    """加载股票数据"""
    feeds = {}
    for sym, name, score in symbols_with_scores:
        df = get_stock_daily(sym)
        if df is None or len(df) < 200:
            continue
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        df = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if len(df) < 200:
            continue
        data_name = make_data_name(sym, name, score)
        feeds[data_name] = bt.feeds.PandasData(dataname=df, name=data_name)
    return feeds


def get_benchmark_return(start, end):
    """获取基准收益"""
    bench = get_index_daily("sh000001")
    if bench is None:
        return 0
    bench.columns = [c.lower() for c in bench.columns]
    bench["date"] = pd.to_datetime(bench["date"])
    bench = bench.set_index("date").sort_index()
    bench = bench.loc[pd.Timestamp(start):pd.Timestamp(end)]
    if len(bench) == 0:
        return 0
    return (bench["close"].iloc[-1] / bench["close"].iloc[0] - 1) * 100


def run_once(params, start, end, cash=1_000_000):
    """单次回测"""
    cerebro = bt.Cerebro()
    feeds = load_data(BUFFETT_POOL, start, end)
    if not feeds:
        return None

    loaded = 0
    for name, data in feeds.items():
        cerebro.adddata(data)
        loaded += 1

    if loaded == 0:
        return None

    cerebro.addstrategy(BuffettCyberStrategy, **params)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.0003)

    start_val = cerebro.broker.getvalue()
    results = cerebro.run()
    end_val = cerebro.broker.getvalue()

    strategy = results[0]
    total_return = (end_val / start_val - 1) * 100
    bench_ret = get_benchmark_return(start, end)

    return {
        "return": total_return, "benchmark": bench_ret,
        "alpha": total_return - bench_ret, "trades": strategy.trade_count,
        "loaded": loaded,
    }


def grid_search():
    """网格搜索最优参数"""
    param_grid = {
        "ma_short": [5, 10],
        "ma_long": [20, 30, 60],
        "stop_loss": [-0.05, -0.08],
        "position_pct": [0.15, 0.30],
        "max_positions": [5, 8],
    }

    keys = list(param_grid.keys())
    combinations = list(itertools.product(*param_grid.values()))

    print(f"网格搜索: {len(combinations)} 组参数")
    print(f"{'='*60}")

    best = None
    best_alpha = -999

    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        result = run_once(params, "2020-01-01", "2023-12-31")

        if result is None:
            continue

        alpha = result["alpha"]
        if alpha > best_alpha:
            best_alpha = alpha
            best = {**params, **result}

        if (i + 1) % 10 == 0:
            print(f"  [{i+1:3d}/{len(combinations)}] best α={best_alpha:+.2f}%")

    print(f"\n最优参数 (训练期 2020-2023):")
    for k, v in best.items():
        print(f"  {k}: {v}")


def run_test():
    """用最优参数跑训练期+测试期"""
    opt_params = dict(ma_short=10, ma_long=20, stop_loss=-0.05,
                      position_pct=0.30, max_positions=5, score_weight=True)
    
    # 测试期
    print(f"\n{'='*60}")
    print("测试期回测 (2024-2026) — 最优参数")
    print(f"{'='*60}")
    result = run_once(opt_params, "2024-01-01", "2026-05-10")
    if result:
        print(f"  策略回报:  {result['return']:+.2f}%")
        print(f"  基准收益:  {result['benchmark']:+.2f}%")
        print(f"  超额收益α:  {result['alpha']:+.2f}%")
        print(f"  交易次数:  {result['trades']}")
        print(f"  加载股票:  {result['loaded']} 只")

    # 全期
    print(f"\n{'='*60}")
    print("全期回测 (2020-2026) — 最优参数")
    print(f"{'='*60}")
    result2 = run_once(opt_params, "2020-01-01", "2026-05-10")
    if result2:
        print(f"  策略回报:  {result2['return']:+.2f}%")
        print(f"  基准收益:  {result2['benchmark']:+.2f}%")
        print(f"  超额收益α:  {result2['alpha']:+.2f}%")
        print(f"  交易次数:  {result2['trades']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimize", action="store_true", help="网格搜索最优参数")
    parser.add_argument("--test", action="store_true", help="用最优参数跑测试期+全期")
    args = parser.parse_args()

    if args.optimize:
        grid_search()
        return

    # 默认: 训练期跑
    params = dict(ma_short=5, ma_long=20, score_weight=True)
    print("训练期回测 (2020-2023)")
    print("=" * 60)
    result = run_once(params, "2020-01-01", "2023-12-31")
    if result:
        for k, v in result.items():
            print(f"  {k}: {v:+.2f}" if isinstance(v, float) else f"  {k}: {v}")

    if args.test:
        run_test()


if __name__ == "__main__":
    main()
