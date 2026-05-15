"""
三策略对比回测 — 逐日引擎，策略自主调仓
产量: data/backtest_<strategy>.pkl + data/backtest_comparison.pkl
"""
import os, sys, pickle
sys.path.insert(0, os.path.expanduser("~/quant-agent"))
for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy','https_proxy','all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

from data.fetcher import get_stock_daily, get_index_daily
from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR
from backtest.analytics import RiskAnalytics, FullReport

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_prices(pool, start, end):
    """加载价格矩阵"""
    dfs = {}
    total = len(pool)
    for i, sym in enumerate(pool):
        if (i+1) % max(1, total//10) == 0 or i == 0:
            print(f"  加载价格: {i+1}/{total}", end="\r", flush=True)
        try:
            df = get_stock_daily(sym)
            if df is None or len(df) < 200:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            df = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
            if len(df) < 200:
                continue
            dfs[sym] = df["close"].rename(sym)
        except Exception:
            continue
    if not dfs:
        return None
    print(f"  加载价格: {len(dfs)}/{total} 有效")  # 换行
    return pd.concat(dfs.values(), axis=1, keys=dfs.keys())


def detect_regime(close, i):
    if i < 60: return "sideways"
    c = close[i]; ma5 = np.mean(close[i-5:i]); ma20 = np.mean(close[i-20:i]); ma60 = np.mean(close[i-60:i])
    if c > ma5 > ma20 > ma60: return "bull"
    if c < ma5 < ma20 < ma60: return "bear"
    return "sideways"


def build_monthly_regime(bench_close_series):
    """用月度K线预计算市场状态，每月一个 regime，避免日频噪声"""
    monthly = bench_close_series.resample("ME").last().dropna()
    regimes = {}
    for i in range(len(monthly)):
        key = monthly.index[i].strftime("%Y-%m")
        if i < 2:
            regimes[key] = "sideways"
            continue
        c = monthly.values[i]
        ma5 = np.mean(monthly.values[max(0, i - 5) : i])
        ma20 = np.mean(monthly.values[max(0, i - 20) : i])
        ma60 = np.mean(monthly.values[max(0, i - 60) : i])
        if c > ma5 > ma20 > ma60:
            regimes[key] = "bull"
        elif c < ma5 < ma20 < ma60:
            regimes[key] = "bear"
        else:
            regimes[key] = "sideways"
    return regimes


def run_backtest(name, pool, prices, bench_close, score_fn, start, end, cash=1_000_000):
    """通用回测引擎 — 逐日评估，策略自主决定调仓日"""
    # 策略调仓规则：默认月初，可通过 score_fn.should_rebalance 自定义
    should_rebal = getattr(score_fn, "should_rebalance", None)
    last_regime = None

    # ── 月线预计算 regime（避免日频噪声）──
    monthly_regimes = build_monthly_regime(bench_close)
    print(f"  [{name}] 月线 regime 预计算完成，{len(monthly_regimes)} 个月")

    holdings = {}
    portfolio_value = cash
    trade_log = []

    total_days = len(prices)
    rebal_count = 0
    rebal_indicator = getattr(score_fn, "rebal_indicator", lambda dt: ".")  # 显示调仓节奏
    daily_values = []
    
    for day_idx in range(total_days):
        dt = prices.index[day_idx]
        current_price = prices.iloc[day_idx]

        # ── 进度 ──
        if total_days >= 200 and day_idx % (total_days // 10) == 0:
            print(f"  [{name}] {dt.date()}  {day_idx*100//total_days}%", end="\r", flush=True)

        # ── 市场状态（从月线预计算字典查）──
        regime = monthly_regimes.get(dt.strftime("%Y-%m"), "sideways")

        # ── 调仓决策 ──
        do_rebalance = False
        if should_rebal is not None:
            do_rebalance = should_rebal(dt, regime, last_regime)
        elif dt.day <= 7 and (last_regime is None or last_regime != regime):
            # 默认：每月前7天 + regime 变化时调仓
            do_rebalance = True
        else:
            # 默认后备：每月前7天
            do_rebalance = (dt.day <= 7)

        if do_rebalance:
            rebal_count += 1
            last_regime = regime
            print(f"\n  [{name}] 调仓 #{rebal_count} @ {dt.date()} regime={regime}", flush=True)

            # ── 评分 ──
            scores = {}
            pool_total = len(pool)
            for pi, sym in enumerate(pool):
                if pool_total >= 500 and pi % (pool_total // 5) == 0:
                    print(f"    评分 {pi*100//pool_total}%", end="\r", flush=True)
                if sym not in prices.columns:
                    continue
                s = prices[sym]
                try:
                    stock_idx = s.index.get_indexer([dt], method="pad")[0]
                    if stock_idx < 0:
                        continue
                except Exception:
                    continue
                sc = score_fn(sym, s, stock_idx, regime)
                if sc > 0:
                    scores[sym] = sc

            if scores:
                ranked = sorted(scores.items(), key=lambda x: -x[1])[:8]
                target = {s for s, _ in ranked}

                # ── 卖出 ──
                for sym in list(holdings):
                    if sym not in target and sym in current_price and not pd.isna(current_price[sym]):
                        p = current_price[sym]
                        portfolio_value += holdings[sym] * p * 0.999  # 佣金
                        trade_log.append((dt, "SELL", sym, holdings[sym], p))
                        del holdings[sym]

                # ── 买入 ──
                val_per = portfolio_value * 0.30 / max(1, len(target))
                for sym in target:
                    if sym not in holdings and sym in current_price and not pd.isna(current_price[sym]):
                        p = current_price[sym]
                        shares = int(val_per / p // 100) * 100
                        if shares >= 100:
                            cost = shares * p * 1.001
                            if cost <= portfolio_value:
                                holdings[sym] = shares
                                portfolio_value -= cost
                                trade_log.append((dt, "BUY", sym, shares, p))

        # ── 日度净值: 必须用当日现金和当日持仓，不能用最终持仓回填历史。
        mv = 0
        for sym, shares in holdings.items():
            if sym in prices.columns:
                known = prices[sym].iloc[: day_idx + 1].dropna()
                if len(known):
                    mv += shares * known.iloc[-1]
        daily_values.append((dt, portfolio_value + mv))

    vdf = pd.DataFrame(daily_values, columns=["date", "value"]).set_index("date")
    daily_returns = vdf["value"].pct_change().dropna()
    bench_returns = bench_close.pct_change().dropna()

    aligned = pd.concat([daily_returns, bench_returns], axis=1, join="inner").dropna()
    report = RiskAnalytics.compute(aligned.iloc[:, 0], aligned.iloc[:, 1])

    result = {
        "daily_returns": daily_returns,
        "bench_returns": bench_returns,
        "trade_log": trade_log,
        "final_holdings": holdings,
        "total_return": report.total_return,
        "bench_return": (bench_close.iloc[-1] / bench_close.iloc[0] - 1),
        "sharpe": report.sharpe,
        "max_drawdown": report.max_drawdown,
        "win_rate": report.win_rate,
        "trade_count": len(trade_log),
    }
    with open(DATA_DIR / f"backtest_{name}.pkl", "wb") as f:
        pickle.dump(result, f)

    print(f"\n{name}: 累计{report.total_return*100:+.2f}%  Sharpe {report.sharpe:.2f}  MaxDD {report.max_drawdown*100:.1f}%  交易{len(trade_log)}笔")
    return result


# ══════════════════════════════════════════════════════════
# 策略评分器 — 每个附带 should_rebalance(date, regime, last_regime) → bool
# ══════════════════════════════════════════════════════════

def buffett_scorer(sym, series, idx, regime):
    """巴菲特评分: 真实三重过滤 (按年滚动)"""
    try:
        from backtest.buffett_real_scorer import create_buffett_real_scorer
        if buffett_scorer._scorer is None:
            pool_ref = getattr(buffett_scorer, "_pool", [])
            buffett_scorer._scorer = create_buffett_real_scorer(pool_ref)
            buffett_scorer._scorer(sym, series, idx, regime)
        return buffett_scorer._scorer(sym, series, idx, regime)
    except Exception:
        return 0

buffett_scorer._scorer = None
buffett_scorer._pool = []


def _buffett_rebal(dt, regime, last_regime):
    """巴菲特调仓: 每年第一个月"""
    return dt.month == 1 and dt.day <= 7

buffett_scorer.should_rebalance = _buffett_rebal


# ── 多因子财务缓存（避免每只股票每次调仓都拉取同花顺） ──
_multifactor_fin_cache = {}

def _get_multifactor_fin_inputs(sym, ind):
    """缓存式获取财务数据，首次拉取后复用"""
    cache_key = sym
    if cache_key in _multifactor_fin_cache:
        return _multifactor_fin_cache[cache_key]
    try:
        from data.financials import get_buffett_inputs
        inputs = get_buffett_inputs(sym, current_price=0, industry=ind)
        _multifactor_fin_cache[cache_key] = inputs
        return inputs
    except Exception:
        _multifactor_fin_cache[cache_key] = None
        return None


def multifactor_scorer(sym, series, idx, regime):
    """多因子评分: 质量(40%)+估值(30%)+技术(15%)+市场(15%)"""
    from signals.multifactor import MultiFactorScorer
    from data.symbols import SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR

    ind = SYMBOL_INDUSTRY.get(sym, "待分类")
    sec = SYMBOL_SECTOR.get(sym, FALLBACK_SECTOR)

    # 构建因子输入
    mom_1m = mom_3m = 0.0
    vol = 0.30
    close_last = 0.0
    try:
        close_vals = series[:idx+1].values
        if len(close_vals) < 63:
            return 0
        mom_1m = close_vals[-1] / close_vals[-21] - 1 if len(close_vals) >= 21 else 0
        mom_3m = close_vals[-1] / close_vals[-63] - 1 if len(close_vals) >= 63 else 0
        rets = np.diff(close_vals[-21:]) / close_vals[-21:-1]
        vol = np.std(rets) * np.sqrt(252)
    except Exception:
        mom_1m = mom_3m = 0
        vol = 0.30

    # 财务数据从缓存获取（每个symbol首次拉取，之后复用）
    inputs = _get_multifactor_fin_inputs(sym, ind)
    buffett_score = min(100, max(0, inputs.get("score", 40) if inputs else 40))
    safety_margin = max(0, inputs.get("safety_margin", 0.05) if inputs else 0.05)
    roe_5y = (sum(inputs.get("roe_history", [0.08])[-5:]) / max(1, len(inputs.get("roe_history", [0.08])[-5:]))) if inputs else 0.08

    from signals.multifactor import MultiFactorScorer
    scorer = MultiFactorScorer(regime=regime)
    factors = {
        "buffett_score": buffett_score,
        "safety_margin": safety_margin,
        "roe_5y": roe_5y,
        "momentum_1m": mom_1m,
        "momentum_3m": mom_3m,
        "volatility": vol,
        "sector": sec,
    }
    return scorer.score(factors)


def _make_monthly_rebal():
    """闭包: 每月仅调一次(月初第一个交易日)"""
    last_month = -1

    def _rebal(dt, regime, last_regime):
        nonlocal last_month
        if dt.month != last_month:
            last_month = dt.month
            return True
        return False

    return _rebal

multifactor_scorer.should_rebalance = _make_monthly_rebal()


def cybernetic_scorer(sym, series, idx, regime):
    """控制论评分: regime + 板块轮动"""
    bull_sectors = {"证券", "电子", "计算机"}
    bear_sectors = {"银行", "公用事业", "食品饮料"}
    sideways_sectors = {"银行", "煤炭", "建筑装饰"}

    ind = SYMBOL_INDUSTRY.get(sym, "")
    if regime == "bull" and ind in bull_sectors: return 80
    if regime == "bear" and ind in bear_sectors: return 70
    if regime == "sideways" and ind in sideways_sectors: return 60
    return 30


def _make_cybernetic_rebal():
    """闭包: regime切换时调, 否则每月仅调一次"""
    last_month = -1

    def _rebal(dt, regime, last_regime):
        nonlocal last_month
        if regime != last_regime:
            last_month = dt.month
            return True
        if dt.month != last_month:
            last_month = dt.month
            return True
        return False

    return _rebal

cybernetic_scorer.should_rebalance = _make_cybernetic_rebal()


# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import yaml
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    bt_cfg = cfg.get("backtest", {})
    pool_size = bt_cfg.get("pool_size", 0)
    pool = list(CIRCLE_STOCKS)
    if pool_size > 0:
        pool = pool[:pool_size]
    start, end = "2015-01-01", "2026-05-10"
    print(f"三策略对比回测: {len(pool)} stocks, {start} ~ {end}")

    prices = load_prices(pool, start, end)
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"]); bench = bench.set_index("date").sort_index()
    bc = bench["close"].loc[pd.Timestamp(start):pd.Timestamp(end)]

    print(f"基准: {bc.iloc[0]:.0f} → {bc.iloc[-1]:.0f} ({((bc.iloc[-1]/bc.iloc[0]-1)*100):+.2f}%)")

    from data.registry import get_enabled_strategies

    _scorer_map = {
        "buffett": buffett_scorer,
        "multifactor": multifactor_scorer,
        "cybernetic": cybernetic_scorer,
    }

    results = {}
    for s in get_enabled_strategies():
        name = s["name"]
        scorer = _scorer_map.get(name)
        if scorer is None:
            print(f"  跳过 {name}: 无对应评分器")
            continue
        if name == "buffett":
            scorer._pool = pool
        print(f"\n  {s['label']} (调仓: {'年' if name == 'buffett' else '周' if name == 'multifactor' else '双周/regime切换'})")
        results[name] = run_backtest(name, pool, prices, bc, scorer, start, end)

    comparison = {
        "strategies": {
            name: {"total_return": r["total_return"], "sharpe": r["sharpe"],
                    "max_drawdown": r["max_drawdown"], "win_rate": r["win_rate"],
                    "trade_count": r["trade_count"]}
            for name, r in results.items()
        },
        "bench_return": (bc.iloc[-1] / bc.iloc[0] - 1),
        "start": start, "end": end,
    }
    with open(DATA_DIR / "backtest_comparison.pkl", "wb") as f:
        pickle.dump(comparison, f)

    print(f"\n{'='*60}")
    print("三策略对比:")
    print(f"基准: {comparison['bench_return']*100:+.2f}%")
    for name, r in comparison["strategies"].items():
        print(f"  {name}: {r['total_return']*100:+.2f}%  Sharpe {r['sharpe']:.2f}  MaxDD {r['max_drawdown']*100:.1f}%  Win {r['win_rate']*100:.0f}%  {r['trade_count']}笔")
