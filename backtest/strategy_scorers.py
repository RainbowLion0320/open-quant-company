"""Production strategy scorers used by the multi-strategy backtest entrypoint."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from backtest.buffett_real_scorer import build_pit_financial_inputs
from core.settings import get_settings
from data.market.symbols import FALLBACK_SECTOR, SYMBOL_INDUSTRY, SYMBOL_SECTOR
from signals.scoring import estimate_buffett_score, score_cybernetic_from_factors
from signals.technical import technical_factors_from_series


def settings() -> dict:
    return get_settings()


def buffett_scorer(sym, series, idx, regime):
    """Buffett score with yearly PIT financial inputs."""
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


def _buffett_rebal(dt, regime, last_regime, holdings, current_price):
    if dt.month in (4, 5) and dt.year != getattr(buffett_scorer, "_last_year", 0):
        buffett_scorer._last_year = dt.year
        return True
    return False


buffett_scorer.should_rebalance = _buffett_rebal
buffett_scorer._last_year = 0


def overlap_ratio(target_set: set, holdings: dict) -> float:
    held = set(holdings.keys())
    if not held:
        return 0.0
    return len(target_set & held) / len(held)


def position_drift(holdings: dict, current_price, target_pct: float = 0.125) -> float:
    if len(holdings) < 3:
        return 0.0
    total = 0.0
    values = {}
    for sym, shares in holdings.items():
        try:
            price = float(current_price[sym])
        except Exception:
            continue
        value = shares * price
        values[sym] = value
        total += value
    if total <= 0:
        return 0.0
    dynamic_target = 1.0 / len(values) if values else target_pct
    max_drift = 0.0
    for value in values.values():
        actual = value / total
        drift = abs(actual - dynamic_target) / dynamic_target if dynamic_target > 0 else 0.0
        max_drift = max(max_drift, drift)
    return max_drift


_multifactor_fin_cache = {}


def _get_multifactor_fin_inputs(sym, year):
    if year not in _multifactor_fin_cache:
        pool_ref = getattr(multifactor_scorer, "_pool", [])
        _multifactor_fin_cache[year] = build_pit_financial_inputs(
            year,
            pool_ref,
            log_label="多因子",
        )
    return _multifactor_fin_cache.get(year, {}).get(sym)


def multifactor_scorer(sym, series, idx, regime):
    """Multi-factor score with PIT financial data and settings-driven weights."""
    from signals.multifactor import MultiFactorScorer

    sector = SYMBOL_SECTOR.get(sym, FALLBACK_SECTOR)
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

    inputs = _get_multifactor_fin_inputs(sym, year)
    buffett_score = 40
    safety_margin = 0.0
    if inputs and current_price > 0:
        try:
            from signals.buffett import buffett_filter

            result = buffett_filter(current_price=current_price, **inputs)
            buffett_score = result.score if result.score > 0 else estimate_buffett_score(inputs)
            safety_margin = result.safety_margin_pct
        except Exception:
            buffett_score = estimate_buffett_score(inputs)
    roe_history = inputs.get("roe_history", [0.08])[-5:] if inputs else [0.08]
    roe_5y = sum(roe_history) / max(1, len(roe_history))

    scorer = MultiFactorScorer(regime=regime)
    return scorer.score({
        "buffett_score": buffett_score,
        "safety_margin": safety_margin,
        "roe_5y": roe_5y,
        "momentum_1m": tech["momentum_1m"],
        "momentum_3m": tech["momentum_3m"],
        "momentum_3m_skip_1m": tech["momentum_3m_skip_1m"],
        "momentum_6m_skip_1m": tech["momentum_6m_skip_1m"],
        "trend_strength": tech["trend_strength"],
        "volatility": tech["volatility"],
        "sector": sector,
    })


def _multifactor_rebal(dt, regime, last_regime, holdings, current_price):
    last_target = getattr(multifactor_scorer, "_last_target", set())
    last_rebal = getattr(multifactor_scorer, "_last_rebalance_date", None)
    if last_rebal is None:
        multifactor_scorer._last_rebalance_date = dt
        return True
    if regime != last_regime:
        multifactor_scorer._last_rebalance_date = dt
        return True
    if position_drift(holdings, current_price) > 0.75:
        multifactor_scorer._last_rebalance_date = dt
        return True
    if last_target and overlap_ratio(last_target, holdings) < 0.5:
        multifactor_scorer._last_rebalance_date = dt
        return True
    if (dt - last_rebal).days >= 28 and dt.month != last_rebal.month:
        multifactor_scorer._last_rebalance_date = dt
        return True
    if not holdings:
        multifactor_scorer._last_rebalance_date = dt
        return True
    return False


multifactor_scorer.should_rebalance = _multifactor_rebal
multifactor_scorer.max_positions = lambda regime: int(settings().get("backtest", {}).get("strategy", {}).get("multifactor", {}).get("top_n", 10))
multifactor_scorer.record_target = lambda target: setattr(multifactor_scorer, "_last_target", set(target))
multifactor_scorer._last_target = set()
multifactor_scorer._last_rebalance_date = None
multifactor_scorer._pool = []


def cybernetic_scorer(sym, series, idx, regime):
    """Cybernetic score: regime + sector rotation + stock trend confirmation."""
    industry = SYMBOL_INDUSTRY.get(sym, "")
    try:
        tech = technical_factors_from_series(series, idx)
        return score_cybernetic_from_factors(industry, regime, tech)
    except Exception:
        return score_cybernetic_from_factors(industry, regime, None)


def _cybernetic_rebal(dt, regime, last_regime, holdings, current_price):
    if regime != last_regime:
        return True
    if position_drift(holdings, current_price) > 0.75:
        return True
    return not holdings


cybernetic_scorer.should_rebalance = _cybernetic_rebal
cybernetic_scorer.max_positions = lambda regime: int(
    settings().get("cybernetics", {}).get("adaptive", {}).get(regime, {}).get("max_positions", 5)
)


_ml_strategy = None


def ml_lgbm_scorer(sym, series, idx, regime):
    """LightGBM score. Missing runtime models simply produce no alpha."""
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
    if position_drift(holdings, current_price) > 0.75:
        ml_lgbm_scorer._last_rebalance_date = dt
        return True
    if not holdings:
        ml_lgbm_scorer._last_rebalance_date = dt
        return True
    return False


ml_lgbm_scorer.should_rebalance = _ml_rebal
ml_lgbm_scorer.max_positions = lambda regime: 8
ml_lgbm_scorer._last_rebalance_date = None


BASE_STRATEGY_SCORERS = {
    "buffett": buffett_scorer,
    "multifactor": multifactor_scorer,
    "cybernetic": cybernetic_scorer,
    "ml_lgbm": ml_lgbm_scorer,
}
