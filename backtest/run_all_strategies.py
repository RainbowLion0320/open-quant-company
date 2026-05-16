"""
四策略对比回测 — 逐日引擎，策略自主调仓
产量: data/backtest_<strategy>.pkl + data/backtest_comparison.pkl
"""
import os, sys, pickle
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy','https_proxy','all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd
import numpy as np
import yaml
from datetime import datetime

from data.fetcher import get_stock_daily, get_index_daily
from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR
from backtest.analytics import RiskAnalytics, FullReport

DATA_DIR = ROOT / "data"


def _settings() -> dict:
    try:
        with open(ROOT / "config" / "settings.yaml") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


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
    # should_rebalance 签名: (dt, regime, last_regime, holdings, current_price) → bool
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

        # ── 调仓决策 (信号驱动, 非日历驱动) ──
        do_rebalance = False
        if should_rebal is not None:
            do_rebalance = should_rebal(dt, regime, last_regime, holdings, current_price)
        elif last_regime is None or last_regime != regime:
            do_rebalance = True
        else:
            do_rebalance = False

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
                max_positions = getattr(score_fn, "max_positions", 8)
                if callable(max_positions):
                    max_positions = max_positions(regime)
                ranked = sorted(scores.items(), key=lambda x: -x[1])[:int(max_positions)]
                target = {s for s, _ in ranked}

                record_target = getattr(score_fn, "record_target", None)
                if callable(record_target):
                    record_target(target)

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


# ════════════════════════════════════════════════════
# 低成本低频规则 — 信号驱动, 非日历驱动
# ════════════════════════════════════════════════════

def _overlap_ratio(target_set: set, holdings: dict) -> float:
    """当前持仓和目标持仓的重叠度 (0-1)"""
    held = set(holdings.keys())
    if not held:
        return 0.0
    return len(target_set & held) / len(held)


def _position_drift(holdings: dict, current_price, target_pct: float = 0.125) -> float:
    """最大仓位漂移 (相对目标的偏离百分比)。
    持仓<3只时不计算漂移 (集中持仓不适合漂移触发)"""
    if len(holdings) < 3:
        return 0.0
    total = 0.0
    values = {}
    for sym, shares in holdings.items():
        try:
            p = float(current_price[sym])
        except Exception:
            continue
        v = shares * p
        values[sym] = v
        total += v
    if total <= 0:
        return 0.0
    # 动态目标权重: 1/N
    n = len(values)
    dyn_target = 1.0 / n if n > 0 else target_pct
    max_drift = 0.0
    for sym, v in values.items():
        actual = v / total
        drift = abs(actual - dyn_target) / dyn_target if dyn_target > 0 else 0.0
        if drift > max_drift:
            max_drift = drift
    return max_drift


# ── 巴菲特: 年报季 (4月底至5月中) ──
_last_buffett_year = 0


def _buffett_rebal(dt, regime, last_regime, holdings, current_price):
    global _last_buffett_year
    if dt.month in (4, 5) and dt.year != _last_buffett_year:
        _last_buffett_year = dt.year
        return True
    return False


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
    try:
        close_vals = series[:idx+1].values
        if len(close_vals) < 63:
            return 0
        current_price = float(close_vals[-1])
        mom_1m = close_vals[-1] / close_vals[-22] - 1 if len(close_vals) >= 22 and close_vals[-22] else 0
        mom_3m = close_vals[-1] / close_vals[-64] - 1 if len(close_vals) >= 64 and close_vals[-64] else 0
        mom_3m_skip = close_vals[-22] / close_vals[-64] - 1 if len(close_vals) >= 64 and close_vals[-64] else 0
        mom_6m_skip = close_vals[-22] / close_vals[-127] - 1 if len(close_vals) >= 127 and close_vals[-127] else mom_3m_skip
        ma120 = np.mean(close_vals[-120:]) if len(close_vals) >= 120 else np.mean(close_vals)
        trend_strength = current_price / ma120 - 1 if ma120 else 0
        rets = np.diff(close_vals[-21:]) / close_vals[-21:-1]
        vol = np.std(rets) * np.sqrt(252)
    except Exception:
        current_price = 0.0
        mom_1m = mom_3m = mom_3m_skip = mom_6m_skip = trend_strength = 0
        vol = 0.30

    # 财务数据从缓存获取（每个symbol首次拉取，之后复用）
    inputs = _get_multifactor_fin_inputs(sym, ind)
    buffett_score = 40
    safety_margin = 0.0
    if inputs and current_price > 0:
        try:
            from signals.buffett import buffett_filter
            br = buffett_filter(current_price=current_price, **inputs)
            buffett_score = br.score if br.score > 0 else _estimate_buffett_score(inputs)
            safety_margin = br.safety_margin_pct
        except Exception:
            buffett_score = _estimate_buffett_score(inputs)
    roe_5y = (sum(inputs.get("roe_history", [0.08])[-5:]) / max(1, len(inputs.get("roe_history", [0.08])[-5:]))) if inputs else 0.08

    from signals.multifactor import MultiFactorScorer
    scorer = MultiFactorScorer(regime=regime)
    factors = {
        "buffett_score": buffett_score,
        "safety_margin": safety_margin,
        "roe_5y": roe_5y,
        "momentum_1m": mom_1m,
        "momentum_3m": mom_3m,
        "momentum_3m_skip_1m": mom_3m_skip,
        "momentum_6m_skip_1m": mom_6m_skip,
        "trend_strength": trend_strength,
        "volatility": vol,
        "sector": sec,
    }
    return scorer.score(factors)

# ── 多因子调仓: 信号重叠度 < 50% 或 仓位漂移 > 50% ──
def _multifactor_rebal(dt, regime, last_regime, holdings, current_price):
    last_target = getattr(multifactor_scorer, "_last_target", set())
    last_rebal = getattr(multifactor_scorer, "_last_rebalance_date", None)
    if last_rebal is None:
        multifactor_scorer._last_rebalance_date = dt
        return True
    if regime != last_regime:
        multifactor_scorer._last_rebalance_date = dt
        return True
    drift = _position_drift(holdings, current_price)
    if drift > 0.75:
        multifactor_scorer._last_rebalance_date = dt
        return True
    overlap = _overlap_ratio(last_target, holdings)
    if last_target and overlap < 0.5:
        multifactor_scorer._last_rebalance_date = dt
        return True
    # Signal-driven portfolios still need scheduled review; otherwise the old
    # target never refreshes and overlap can remain 100% forever.
    if (dt - last_rebal).days >= 28 and dt.month != last_rebal.month:
        multifactor_scorer._last_rebalance_date = dt
        return True
    if not holdings:
        multifactor_scorer._last_rebalance_date = dt
        return True
    return False


multifactor_scorer.should_rebalance = _multifactor_rebal
multifactor_scorer.max_positions = lambda regime: int(_settings().get("backtest", {}).get("strategy", {}).get("multifactor", {}).get("top_n", 10))
multifactor_scorer.record_target = lambda target: setattr(multifactor_scorer, "_last_target", set(target))
multifactor_scorer._last_target = set()
multifactor_scorer._last_rebalance_date = None


def cybernetic_scorer(sym, series, idx, regime):
    """控制论评分: regime + 板块轮动 + 个股趋势确认"""
    bull_sectors = {"证券", "电子", "计算机", "电力设备", "国防军工"}
    bear_sectors = {"银行", "公用事业", "交通运输", "食品饮料", "医药生物"}
    sideways_sectors = {"银行", "公用事业", "煤炭", "石油石化", "建筑装饰"}

    ind = SYMBOL_INDUSTRY.get(sym, "")
    favored = (
        ind in bull_sectors if regime == "bull"
        else ind in bear_sectors if regime == "bear"
        else ind in sideways_sectors
    )
    base = 62 if favored else (35 if regime == "bear" else 45)
    try:
        vals = series[:idx+1].values
        if len(vals) < 64:
            return base
        mom_3m_skip = vals[-22] / vals[-64] - 1 if vals[-64] else 0
        ma120 = np.mean(vals[-120:]) if len(vals) >= 120 else np.mean(vals)
        trend = vals[-1] / ma120 - 1 if ma120 else 0
        rets = np.diff(vals[-21:]) / vals[-21:-1]
        vol = np.std(rets) * np.sqrt(252)
        score = base + max(-18, min(18, trend * 100)) + max(-12, min(12, mom_3m_skip * 80))
        score -= max(0, (vol - 0.35) * 45)
        if regime == "bear" and not favored:
            score -= 8
        return max(0, min(100, score))
    except Exception:
        return base


# ── 控制论调仓: 仅 regime 切换 + 漂移 > 50% ──

def _cybernetic_rebal(dt, regime, last_regime, holdings, current_price):
    if regime != last_regime:
        return True
    drift = _position_drift(holdings, current_price)
    if drift > 0.75:
        return True
    if not holdings:
        return True
    return False


cybernetic_scorer.should_rebalance = _cybernetic_rebal
cybernetic_scorer.max_positions = lambda regime: int(
    _settings().get("cybernetics", {}).get("adaptive", {}).get(regime, {}).get("max_positions", 5)
)


_ml_strategy = None


def ml_lgbm_scorer(sym, series, idx, regime):
    """LightGBM评分: 优先使用regime-aware模型，缺模型时不入选。"""
    global _ml_strategy
    if _ml_strategy is None:
        try:
            from backtest.strategies.ml_strategy import MLStrategy
            _ml_strategy = MLStrategy("best")
        except Exception:
            _ml_strategy = False
    if not _ml_strategy or not getattr(_ml_strategy, "is_ready", False):
        return 0
    return _ml_strategy.score(sym, series, idx, regime)


def _ml_rebal(dt, regime, last_regime, holdings, current_price):
    if regime != last_regime:
        return True
    last_rebal = getattr(ml_lgbm_scorer, "_last_rebalance_date", None)
    if last_rebal is None or (dt - last_rebal).days >= 28 and dt.month != last_rebal.month:
        ml_lgbm_scorer._last_rebalance_date = dt
        return True
    drift = _position_drift(holdings, current_price)
    if drift > 0.75:
        ml_lgbm_scorer._last_rebalance_date = dt
        return True
    if not holdings:
        ml_lgbm_scorer._last_rebalance_date = dt
        return True
    return False


ml_lgbm_scorer.should_rebalance = _ml_rebal
ml_lgbm_scorer.max_positions = lambda regime: 8
ml_lgbm_scorer._last_rebalance_date = None


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
    print(f"四策略对比回测: {len(pool)} stocks, {start} ~ {end}")

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
        "ml_lgbm": ml_lgbm_scorer,
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
        print(f"\n  {s['label']} (调仓: { '年报季' if name=='buffett' else '月度复评+信号+漂移' if name=='multifactor' else 'regime+漂移' if name=='cybernetic' else '月度复评+regime' })")
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
    print("四策略对比:")
    print(f"基准: {comparison['bench_return']*100:+.2f}%")
    for name, r in comparison["strategies"].items():
        print(f"  {name}: {r['total_return']*100:+.2f}%  Sharpe {r['sharpe']:.2f}  MaxDD {r['max_drawdown']*100:.1f}%  Win {r['win_rate']*100:.0f}%  {r['trade_count']}笔")
