#!/usr/bin/env python3
"""
控制论自适应策略回测 — 市场状态切换

用法:
  python backtest/run_cybernetic.py              # 全期回测
  python backtest/run_cybernetic.py --optimize    # 网格搜索
"""
import os, sys, itertools, argparse
sys.path.insert(0, os.path.expanduser("~/quant-agent"))

for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

import backtrader as bt
import pandas as pd
from data.fetcher import get_stock_daily, get_index_daily
from backtest.strategies.cybernetic import CyberneticStrategy, make_regime_data

# 25只巴菲特精选池
BUFFETT_POOL = [
    ("601225","陕西煤业",91),("603288","海天味业",91),("600938","中国海油",90),
    ("002415","海康威视",88),("601838","成都银行",88),("002555","三七互娱",87),
    ("600989","宝丰能源",85),("600036","招商银行",82),("002142","宁波银行",81),
    ("600926","杭州银行",80),("600919","江苏银行",79),("601009","南京银行",79),
    ("601128","常熟银行",77),("601939","建设银行",77),("601665","齐鲁银行",76),
    ("600999","招商证券",75),("601288","农业银行",75),("601577","长沙银行",75),
    ("002736","国信证券",74),("600030","中信证券",73),("601066","中信建投",73),
    ("601688","华泰证券",73),("601601","中国太保",69),("601318","中国平安",68),
    ("601878","浙商证券",64),
]


def load_data(pool, start, end):
    """加载股票 + 市场状态数据"""
    # 基准上证
    bench = get_index_daily("sh000001")
    if bench is not None:
        bench["date"] = pd.to_datetime(bench["date"])
        bench = bench.set_index("date").sort_index()
        bench = bench.loc[pd.Timestamp(start):pd.Timestamp(end)]

    # 市场状态序列
    regime_df = make_regime_data(bench) if bench is not None else None

    # 股票数据
    feeds = {}
    for sym, name, score in pool:
        df = get_stock_daily(sym)
        if df is None or len(df) < 200:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if len(df) < 200:
            continue
        dname = f"{sym}_{name}_{score}"
        feeds[dname] = bt.feeds.PandasData(dataname=df, name=dname)

    return feeds, regime_df


def run(params, start, end, cash=1_000_000):
    """单次回测"""
    cerebro = bt.Cerebro()
    feeds, regime_df = load_data(BUFFETT_POOL, start, end)
    if not feeds:
        return None

    # 先加股票
    loaded = 0
    for name, data in feeds.items():
        cerebro.adddata(data)
        loaded += 1

    # 再加市场状态 (最后一条, regime_data_idx 指向总数-1)
    regime_idx = loaded  # 股票之后
    if regime_df is not None:
        rdata = bt.feeds.PandasData(dataname=regime_df, name="REGIME")
        cerebro.adddata(rdata)
        params["regime_data_idx"] = regime_idx

    cerebro.addstrategy(CyberneticStrategy, **params)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(0.0003)

    sv = cerebro.broker.getvalue()
    results = cerebro.run()
    ev = cerebro.broker.getvalue()

    # 基准收益
    bench_ret = 0
    bench = get_index_daily("sh000001")
    if bench is not None:
        bench["date"] = pd.to_datetime(bench["date"])
        bench = bench.set_index("date").sort_index()
        b = bench.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if len(b) > 0:
            bench_ret = (b["close"].iloc[-1] / b["close"].iloc[0] - 1) * 100

    strat = results[0]
    return {
        "return": (ev / sv - 1) * 100,
        "benchmark": bench_ret,
        "alpha": (ev / sv - 1) * 100 - bench_ret,
        "trades": strat.trades,
        "loaded": loaded,
    }


def grid_search():
    """网格搜索最优参数"""
    grid = {
        "ma_short": [5, 10],
        "ma_long": [20, 30],
        "stop_loss_bull": [-0.08, -0.10],
        "stop_loss_side": [-0.05, -0.08],
        "stop_loss_bear": [-0.03, -0.05],
    }
    keys = list(grid.keys())
    combos = list(itertools.product(*grid.values()))
    print(f"网格搜索: {len(combos)} 组")
    print("=" * 60)

    best = None
    best_a = -999
    for i, combo in enumerate(combos):
        p = dict(zip(keys, combo))
        r = run(p, "2020-01-01", "2023-12-31")
        if r and r["alpha"] > best_a:
            best_a = r["alpha"]
            best = {**p, **r}
        if (i+1) % 5 == 0:
            print(f"  [{i+1:3d}/{len(combos)}] best α={best_a:+.2f}%")

    print(f"\n最优参数 (训练期 2020-2023):")
    for k, v in best.items():
        print(f"  {k}: {v}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--optimize", action="store_true")
    args = p.parse_args()

    if args.optimize:
        grid_search()
        return

    # 全期回测
    params = dict(ma_short=10, ma_long=20,
                  stop_loss_bull=-0.08, stop_loss_side=-0.05, stop_loss_bear=-0.03,
                  position_bull=0.30, position_side=0.15, position_bear=0.05,
                  max_pos_bull=8, max_pos_side=5, max_pos_bear=2,
                  score_weight=True)

    for label, s, e in [("训练期 2020-2023", "2020-01-01", "2023-12-31"),
                         ("测试期 2024-2026", "2024-01-01", "2026-05-10"),
                         ("全期 2020-2026",   "2020-01-01", "2026-05-10")]:
        print(f"\n{'='*60}")
        print(f"{label}")
        print(f"{'='*60}")
        r = run(params, s, e)
        if r:
            print(f"  策略: {r['return']:+.2f}%  基准: {r['benchmark']:+.2f}%  α: {r['alpha']:+.2f}%  交易: {r['trades']}")


if __name__ == "__main__":
    main()
