#!/usr/bin/env python3
"""
策略锦标赛: 自动对比所有注册策略 (手调 + ML)

运行:
  python scripts/strategy_tournament.py
  python scripts/strategy_tournament.py --pool-size 50  # 小规模快速测试
"""
import os, sys, json, time
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd
import numpy as np

from data.symbols import CIRCLE_STOCKS
from data.fetcher import get_stock_daily, get_index_daily
from data.datahub import get_datahub
from backtest.strategies.base import BaseStrategy, StrategyRegistry
from backtest.strategies.ml_strategy import MLStrategy
from broker.exchange import AShareExchange, OrderSide
from backtest.analytics import RiskAnalytics, FullReport

HUB = get_datahub()


# ══════════════════════════════════════════════════════════
# 锦标赛配置
# ══════════════════════════════════════════════════════════

TOURNAMENT_DIR = Path(__file__).resolve().parent.parent / "data" / "tournament"
TOURNAMENT_DIR.mkdir(parents=True, exist_ok=True)


def register_all_strategies() -> StrategyRegistry:
    """注册所有可用策略"""
    reg = StrategyRegistry()

    # 手调策略 (内联 scorer, 简化版)
    from backtest.run_all_strategies import buffett_scorer, multifactor_scorer, cybernetic_scorer

    class BuffettStrategy(BaseStrategy):
        name = "buffett"; label = "巴菲特价值精选"
        def score(self, sym, prices, idx, regime, **kw):
            return buffett_scorer(sym, prices, idx, regime)
    reg.register(BuffettStrategy())

    class MultifactorStrategy(BaseStrategy):
        name = "multifactor"; label = "多因子月度调仓"
        def score(self, sym, prices, idx, regime, **kw):
            return multifactor_scorer(sym, prices, idx, regime)
    reg.register(MultifactorStrategy())

    class CyberneticStrategy(BaseStrategy):
        name = "cybernetic"; label = "控制论自适应"
        def score(self, sym, prices, idx, regime, **kw):
            return cybernetic_scorer(sym, prices, idx, regime)
    reg.register(CyberneticStrategy())

    # ML 策略 (如果模型可用)
    try:
        ml = MLStrategy("best")
        if ml.is_ready:
            reg.register(ml)
            print(f"  ✅ ML策略已加载: {ml.name}")
        else:
            print(f"  ⚠️ ML策略模型未训练, 跳过")
    except Exception as e:
        print(f"  ⚠️ ML策略加载失败: {e}")

    return reg


def run_tournament(pool_size: int = 50, start: str = "2020-01-01", end: str = "2026-05-10"):
    """运行锦标赛: 所有策略统一回测对比"""
    print(f"\n{'='*60}")
    print(f"策略锦标赛: {pool_size} stocks, {start} → {end}")
    print(f"{'='*60}")

    # 注册策略
    reg = register_all_strategies()
    print(f"\n已注册 {len(reg.list_names())} 策略: {reg.list_names()}")

    # 数据 — 按市值排序选股（避免前200只=纯深市小票，巴菲特0交易）
    symbols_raw = list(CIRCLE_STOCKS)
    # 优先用已有 Parquet 缓存中的最新 total_mv 排序
    try:
        feat_dir = HUB.features_dir()
        latest_pq = sorted(feat_dir.glob("*.parquet"))[-1] if list(feat_dir.glob("*.parquet")) else None
        if latest_pq:
            df_latest = HUB.read_parquet(latest_pq)
            if "val_total_mv" in df_latest.columns and "symbol" in df_latest.columns:
                mv_map = dict(zip(df_latest["symbol"], df_latest["val_total_mv"]))
                symbols_raw.sort(key=lambda s: mv_map.get(s, 0), reverse=True)
    except Exception:
        pass  # fallback: 均匀采样
    if len(symbols_raw) <= pool_size:
        symbols = symbols_raw
    else:
        symbols = symbols_raw[:pool_size]
    exchange = AShareExchange()

    # 加载基准 (用上证综指日线, get_stock_daily兼容指数代码)
    print("\n加载数据...")
    try:
        bench = get_index_daily("sh000001")
    except Exception:
        bench = get_stock_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    bench = bench.set_index("date").sort_index()
    bench = bench.loc[pd.Timestamp(start):pd.Timestamp(end)]

    # 加载股票日线
    print(f"  加载 {len(symbols)} 只日线...")
    prices_dict = {}
    t_load = time.monotonic()
    for i, sym in enumerate(symbols):
        try:
            df = get_stock_daily(sym)
            if df is not None and len(df) > 60:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                prices_dict[sym] = df
        except Exception:
            pass
        if (i+1) % 1000 == 0:
            print(f"    {i+1}/{len(symbols)} ({len(prices_dict)} valid, {time.monotonic()-t_load:.1f}s)")
    print(f"  有效股票: {len(prices_dict)}/{pool_size} ({time.monotonic()-t_load:.1f}s)")

    # 检测 regime (月线)
    from backtest.run_all_strategies import build_monthly_regime
    monthly_regime = build_monthly_regime(bench["close"])

    # ══════════════════════════════════════════════════════
    # 锦标赛回测 (每个策略独立跑)
    # ══════════════════════════════════════════════════════

    results = {}
    dates = bench.index
    bench_ret_total = bench["close"].iloc[-1] / bench["close"].iloc[0] - 1

    for strategy in reg.get_enabled():
        t_s0 = time.monotonic()
        print(f"\n── {strategy.label} ──")
        cash = 1_000_000
        holdings = {}
        portfolio_values = []
        trade_count = 0
        last_regime = None

        for day_idx, dt in enumerate(dates):
            regime = monthly_regime.get(dt.strftime("%Y-%m"), "sideways")

            # 调仓决策
            do_rebal = strategy.should_rebalance(dt, regime, last_regime)

            if do_rebal:
                trade_count += 1
                last_regime = regime
                # 评分
                scores = {}
                for sym, df in prices_dict.items():
                    if dt not in df.index:
                        continue
                    idx = df.index.get_loc(dt)
                    # 只传 close Series (兼容旧 scorer)
                    close_only = df["close"] if isinstance(df, pd.DataFrame) else df
                    sc = strategy.score(sym, close_only, idx, regime)
                    if sc > 0:
                        scores[sym] = sc

                # 调仓
                if scores:
                    holdings, cash = strategy.get_positions(
                        scores, holdings,
                        pd.Series({s: df.loc[dt, "close"] for s, df in prices_dict.items() if dt in df.index}),
                        cash,
                    )
                if trade_count % 20 == 0:
                    print(f"  调仓 #{trade_count} ({dt.strftime('%Y-%m-%d')}), 候选 {len(scores)} 只, 持仓 {sum(holdings.values())} 股, {time.monotonic()-t_s0:.0f}s")

            # 计算当日净值
            mv = cash
            for sym, shares in holdings.items():
                if sym in prices_dict and dt in prices_dict[sym].index:
                    mv += shares * prices_dict[sym].loc[dt, "close"]
            portfolio_values.append(mv)

        # 绩效
        values = pd.Series(portfolio_values, index=dates)
        returns = values.pct_change().dropna()
        bench_ret = bench["close"].pct_change().dropna()
        aligned = pd.concat([returns, bench_ret], axis=1, join="inner").dropna()

        if len(aligned) > 0:
            report = RiskAnalytics.compute(aligned.iloc[:, 0], aligned.iloc[:, 1])
        else:
            report = FullReport()

        total_ret = values.iloc[-1] / values.iloc[0] - 1 if len(values) > 0 else 0
        t_elapsed = time.monotonic() - t_s0

        results[strategy.name] = {
            "label": strategy.label,
            "total_return": round(total_ret * 100, 2),
            "sharpe": round(report.sharpe, 2),
            "max_drawdown": round(report.max_drawdown * 100, 1),
            "win_rate": round(report.win_rate * 100, 1),
            "trades": trade_count,
            "bench_return": round(bench_ret_total * 100, 2),
        }

        print(f"  {strategy.label}: {total_ret*100:+.2f}% | Sharpe {report.sharpe:.2f} | MaxDD {report.max_drawdown*100:.1f}% ({t_elapsed:.0f}s)")

    # ══════════════════════════════════════════════════════
    # 排名 + 保存
    # ══════════════════════════════════════════════════════

    ranked = sorted(results.items(), key=lambda x: -x[1]["total_return"])
    print(f"\n{'='*60}")
    print(f"🏆 锦标赛排名")
    print(f"{'='*60}")
    for rank, (name, r) in enumerate(ranked, 1):
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"  {rank}."
        print(f"  {medal} {r['label']}: {r['total_return']:+.2f}% | MaxDD {r['max_drawdown']}% | {r['trades']}笔")

    # 保存
    report = {
        "timestamp": datetime.now().isoformat(),
        "pool_size": pool_size,
        "period": f"{start} → {end}",
        "bench_return": round(bench_ret_total * 100, 2),
        "results": results,
        "rankings": [name for name, _ in ranked],
    }
    report_path = TOURNAMENT_DIR / f"tournament_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    json.dump(report, report_path.open("w"), indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {report_path}")

    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool-size", type=int, default=50)
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-05-10")
    args = ap.parse_args()
    run_tournament(pool_size=args.pool_size, start=args.start, end=args.end)
