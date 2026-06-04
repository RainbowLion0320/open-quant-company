"""
多策略对比回测 — 逐日引擎，策略自主调仓
产量: data/backtest_<strategy>.pkl + data/backtest_comparison.pkl
"""
import hashlib
import os, pickle, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy','https_proxy','all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd
from datetime import datetime

from core.settings import get_settings
from data.fetcher import get_index_daily
from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR
from backtest.regime_replay import build_production_regime_map
from signals.scoring import estimate_buffett_score, score_cybernetic_from_factors
from signals.technical import technical_factors_from_series
from research.strategy_evaluation import write_backtest_evidence
from backtest.buffett_real_scorer import build_pit_financial_inputs
from backtest.candidate_alpha import (
    CandidateStrategyAlphaModel,
    candidate_backtest_strategy_names,
    candidate_max_positions,
    is_candidate_backtest_strategy,
    register_price_panels,
)

DATA_DIR = ROOT / "data"


def _settings() -> dict:
    return get_settings()


def load_prices(pool, start, end):
    """加载价格矩阵"""
    from core.settings import get_section
    from data.datahub import get_datahub

    hub = get_datahub()
    min_bars = int((get_section("backtest", {}) or {}).get("min_bars", 200))
    existing_paths = []
    latest_mtime = 0
    for sym in pool:
        path = hub.stock_daily_path(sym)
        if not path.exists():
            continue
        existing_paths.append((sym, path))
        latest_mtime = max(latest_mtime, path.stat().st_mtime_ns)

    cache_seed = f"{start}|{end}|{min_bars}|{len(pool)}|{len(existing_paths)}|{latest_mtime}"
    cache_key = hashlib.md5(cache_seed.encode()).hexdigest()[:12]
    cache_path = DATA_DIR / f"backtest_price_matrix_{cache_key}.pkl"
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        if isinstance(cached, dict) and "prices" in cached:
            prices = cached["prices"]
            panel_frames = cached.get("panels", {})
        else:
            prices = cached
            panel_frames = prices.attrs.get("panels", {})
        register_price_panels(prices, panel_frames)
        prices.attrs = {}
        print(f"  价格矩阵缓存命中: {len(prices.columns)}/{len(pool)} 有效")
        return prices

    dfs = {}
    panels = {"high": {}, "volume": {}, "amount": {}, "turnover": {}}
    total = len(existing_paths)
    for i, (sym, path) in enumerate(existing_paths):
        if (i+1) % max(1, total//10) == 0 or i == 0:
            print(f"  加载价格: {i+1}/{total}", end="\r", flush=True)
        try:
            df = hub.read_parquet(path)
            if df is None or len(df) < min_bars:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            df = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
            if len(df) < min_bars:
                continue
            for column, panel in panels.items():
                if column in df.columns:
                    panel[sym] = pd.to_numeric(df[column], errors="coerce").rename(sym)
                else:
                    panel[sym] = pd.to_numeric(df["close"], errors="coerce").rename(sym)
            dfs[sym] = df["close"].rename(sym)
        except Exception:
            continue
    if not dfs:
        return None
    print(f"  加载价格: {len(dfs)}/{total} 有效")  # 换行
    prices = pd.concat(dfs.values(), axis=1, keys=dfs.keys())
    panel_frames = {
        key: pd.concat(values.values(), axis=1, keys=values.keys()).reindex(prices.index)
        for key, values in panels.items()
        if values
    }
    register_price_panels(prices, panel_frames)
    prices.attrs = {}
    with open(cache_path, "wb") as f:
        pickle.dump({"prices": prices, "panels": panel_frames}, f)
    return prices


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


# ── 多因子财务缓存（按回测年份缓存PIT财务快照） ──
_multifactor_fin_cache = {}


def _get_multifactor_fin_inputs(sym, ind, year):
    """从回测年份的PIT财务快照获取输入，避免实时财务路径和前视偏差。"""
    if year not in _multifactor_fin_cache:
        pool_ref = getattr(multifactor_scorer, "_pool", [])
        _multifactor_fin_cache[year] = build_pit_financial_inputs(
            year,
            pool_ref,
            log_label="多因子",
        )
    return _multifactor_fin_cache.get(year, {}).get(sym)


def multifactor_scorer(sym, series, idx, regime):
    """多因子评分: 质量/估值/技术/市场/行业动量五维，权重来自 settings。"""
    from signals.multifactor import MultiFactorScorer
    from data.symbols import SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR

    ind = SYMBOL_INDUSTRY.get(sym, "待分类")
    sec = SYMBOL_SECTOR.get(sym, FALLBACK_SECTOR)

    try:
        history = pd.Series(series).iloc[: idx + 1].dropna()
        if len(history) < 63:
            return 0
        current_price = float(history.iloc[-1])
        tech = technical_factors_from_series(series, idx)
    except Exception:
        current_price = 0.0
        tech = technical_factors_from_series(pd.Series(dtype="float64"))

    try:
        year = pd.Timestamp(series.index[idx]).year
    except Exception:
        year = datetime.now().year

    # 财务数据从回测年份PIT缓存获取（同年首次构建，之后复用）
    inputs = _get_multifactor_fin_inputs(sym, ind, year)
    buffett_score = 40
    safety_margin = 0.0
    if inputs and current_price > 0:
        try:
            from signals.buffett import buffett_filter
            br = buffett_filter(current_price=current_price, **inputs)
            buffett_score = br.score if br.score > 0 else estimate_buffett_score(inputs)
            safety_margin = br.safety_margin_pct
        except Exception:
            buffett_score = estimate_buffett_score(inputs)
    roe_5y = (sum(inputs.get("roe_history", [0.08])[-5:]) / max(1, len(inputs.get("roe_history", [0.08])[-5:]))) if inputs else 0.08

    scorer = MultiFactorScorer(regime=regime)
    factors = {
        "buffett_score": buffett_score,
        "safety_margin": safety_margin,
        "roe_5y": roe_5y,
        "momentum_1m": tech["momentum_1m"],
        "momentum_3m": tech["momentum_3m"],
        "momentum_3m_skip_1m": tech["momentum_3m_skip_1m"],
        "momentum_6m_skip_1m": tech["momentum_6m_skip_1m"],
        "trend_strength": tech["trend_strength"],
        "volatility": tech["volatility"],
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
multifactor_scorer._pool = []


def cybernetic_scorer(sym, series, idx, regime):
    """控制论评分: regime + 板块轮动 + 个股趋势确认"""
    ind = SYMBOL_INDUSTRY.get(sym, "")
    try:
        tech = technical_factors_from_series(series, idx)
        return score_cybernetic_from_factors(ind, regime, tech)
    except Exception:
        return score_cybernetic_from_factors(ind, regime, None)


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


def backtest_strategy_names() -> list[str]:
    """Return registered strategy names with a concrete backtest adapter."""
    names = {"buffett", "multifactor", "cybernetic", "ml_lgbm"}
    names.update(candidate_backtest_strategy_names())
    return sorted(names)


def _strategy_alpha_model(name: str, label: str, scorer_fn, alpha_min_score: int):
    from pipeline.alpha import StrategyAlphaAdapter

    if is_candidate_backtest_strategy(name):
        return CandidateStrategyAlphaModel(name=name, label=label)
    return StrategyAlphaAdapter(
        name=name,
        label=name,
        scorer=scorer_fn,
        min_score=alpha_min_score,
        rebalance_trigger=_strategy_trigger(name),
    )


def _strategy_trigger(name: str):
    return {
        "buffett": (lambda d, r, h:
                    d.month in (4, 5) and getattr(run_pipeline_backtest, '_last_buffett_year', 0) != d.year
                    and not setattr(run_pipeline_backtest, '_last_buffett_year', d.year)),
    }.get(name)


# ══════════════════════════════════════════════════════════
# Pipeline-based backtest — uses the same Alpha→Portfolio→Risk→Execution
# stages as paper trading.
# ══════════════════════════════════════════════════════════

def run_pipeline_backtest(name, pool, prices, bench_close, scorer_fn, start, end,
                          cash=1_000_000, monthly_regimes=None, label=None):
    """Run backtest via the pipeline stages shared with paper trading."""
    from pipeline.portfolio import EqualWeightConstructor
    from pipeline.scheduler import RebalanceScheduler, RebalanceConfig

    # Pre-compute production policy regimes if not provided
    if monthly_regimes is None:
        monthly_regimes = build_production_regime_map(bench_close)

    from core.settings import get_section
    _bt_cfg = get_section("backtest", {}) or {}
    _rebal_cfg = _bt_cfg.get("rebalance", {}) or {}
    _max_pos_cfg = _bt_cfg.get("max_positions", {}) or {}
    _drift = float(_rebal_cfg.get("drift_threshold", 0.75))
    _overlap = float(_rebal_cfg.get("overlap_threshold", 0.50))
    _alpha_min = int(_bt_cfg.get("alpha_min_score", 30))

    _sched_configs = {
        "buffett": RebalanceConfig(schedule="drift", force_months=[4, 5], max_idle_days=365),
        "multifactor": RebalanceConfig(schedule="monthly", drift_threshold=_drift, min_overlap_pct=_overlap),
        "cybernetic": RebalanceConfig(schedule="regime_change", drift_threshold=_drift),
        "ml_lgbm": RebalanceConfig(schedule="monthly", drift_threshold=_drift),
        "trend_following": RebalanceConfig(schedule="monthly", drift_threshold=_drift, min_overlap_pct=_overlap),
        "donchian_breakout": RebalanceConfig(schedule="monthly", drift_threshold=_drift, min_overlap_pct=_overlap),
        "rps_relative_strength": RebalanceConfig(schedule="monthly", drift_threshold=_drift, min_overlap_pct=_overlap),
        "sector_rotation": RebalanceConfig(schedule="monthly", drift_threshold=_drift, min_overlap_pct=_overlap),
        "quality_value": RebalanceConfig(schedule="monthly", drift_threshold=_drift, min_overlap_pct=_overlap),
        "low_vol_defensive": RebalanceConfig(schedule="monthly", drift_threshold=_drift, min_overlap_pct=_overlap),
        "volume_confirmation": RebalanceConfig(schedule="monthly", drift_threshold=_drift, min_overlap_pct=_overlap),
        "regime_gated": RebalanceConfig(schedule="regime_change", drift_threshold=_drift, min_overlap_pct=_overlap),
    }

    _max_pos = {"buffett": 8, "multifactor": 10, "cybernetic": 5, "ml_lgbm": 8}
    for candidate_name in candidate_backtest_strategy_names():
        _max_pos[candidate_name] = candidate_max_positions(candidate_name)
    _max_pos = {k: int(_max_pos_cfg.get(k, v)) for k, v in _max_pos.items()}

    sched_cfg = _sched_configs.get(name, RebalanceConfig())

    alpha = _strategy_alpha_model(name, label or name, scorer_fn, _alpha_min)

    portfolio = EqualWeightConstructor(max_positions=_max_pos.get(name, 8))
    scheduler = RebalanceScheduler(sched_cfg)

    from backtest.pipeline_runner import PipelineBacktest
    runner = PipelineBacktest(
        alpha=alpha,
        portfolio=portfolio,
        scheduler=scheduler,
        cash=cash,
    )

    return runner.run(prices, bench_close, universe=pool, monthly_regimes=monthly_regimes)


# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse as _ap
    _parser = _ap.ArgumentParser()
    _parser.add_argument("--pipeline", action="store_true", help="Use pipeline-based backtest runner")
    _parser.add_argument("--strategy", default="", help="Run one registered strategy by name")
    _args = _parser.parse_args()

    bt_cfg = _settings().get("backtest", {})
    pool_size = bt_cfg.get("pool_size", 0)
    pool = list(CIRCLE_STOCKS)
    if pool_size > 0:
        pool = pool[:pool_size]
    start = bt_cfg.get("start_date", "2015-01-01")
    end = bt_cfg.get("end_date", "2026-05-10")
    runner_label = "pipeline"
    print(f"策略对比回测 [{runner_label}]: {len(pool)} stocks, {start} ~ {end}")

    prices = load_prices(pool, start, end)
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"]); bench = bench.set_index("date").sort_index()
    bc = bench["close"].loc[pd.Timestamp(start):pd.Timestamp(end)]
    monthly_regimes = build_production_regime_map(bc)

    print(f"基准: {bc.iloc[0]:.0f} → {bc.iloc[-1]:.0f} ({((bc.iloc[-1]/bc.iloc[0]-1)*100):+.2f}%)")

    from data.registry import get_enabled_strategies

    _scorer_map = {
        "buffett": buffett_scorer,
        "multifactor": multifactor_scorer,
        "cybernetic": cybernetic_scorer,
        "ml_lgbm": ml_lgbm_scorer,
    }
    for candidate_name in candidate_backtest_strategy_names():
        _scorer_map[candidate_name] = None

    results = {}
    enabled_strategies = get_enabled_strategies()
    if _args.strategy:
        enabled_strategies = [s for s in enabled_strategies if s["name"] == _args.strategy]
        if not enabled_strategies:
            raise SystemExit(f"Unknown or disabled strategy: {_args.strategy}")

    for s in enabled_strategies:
        name = s["name"]
        scorer = _scorer_map.get(name)
        if name not in _scorer_map:
            print(f"  跳过 {name}: 无对应评分器")
            continue
        if name == "buffett":
            scorer._pool = list(prices.columns)
        if name == "multifactor":
            scorer._pool = list(prices.columns)

        _sched_desc = {
            "buffett": "年报季+漂移", "multifactor": "月度+漂移",
            "cybernetic": "regime+漂移", "ml_lgbm": "月度+漂移",
        }
        print(f"\n  {s['label']} (调仓: {_sched_desc.get(name, 'default')})")

        results[name] = run_pipeline_backtest(
            name, pool, prices, bc, scorer, start, end,
            monthly_regimes=monthly_regimes,
            cash=float(bt_cfg.get("initial_cash", 1_000_000)),
            label=s.get("label", name),
        )
        with open(DATA_DIR / f"backtest_{name}.pkl", "wb") as f:
            pickle.dump(results[name], f)
        write_backtest_evidence(
            name,
            s.get("status", "candidate"),
            results[name],
            start=start,
            end=end,
        )

    comparison = {
        "strategies": {
            name: {"total_return": r["total_return"], "sharpe": r["sharpe"],
                    "max_drawdown": r["max_drawdown"], "win_rate": r["win_rate"],
                    "trade_count": r["trade_count"]}
            for name, r in results.items()
        },
        "bench_return": (bc.iloc[-1] / bc.iloc[0] - 1),
        "start": start, "end": end,
        "runner": runner_label,
    }
    with open(DATA_DIR / "backtest_comparison.pkl", "wb") as f:
        pickle.dump(comparison, f)

    print(f"\n{'='*60}")
    print(f"策略对比 [{runner_label}]:")
    print(f"基准: {comparison['bench_return']*100:+.2f}%")
    for name, r in comparison["strategies"].items():
        print(f"  {name}: {r['total_return']*100:+.2f}%  Sharpe {r['sharpe']:.2f}  MaxDD {r['max_drawdown']*100:.1f}%  Win {r['win_rate']*100:.0f}%  {r['trade_count']}笔")
