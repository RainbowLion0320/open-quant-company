"""Profit-oriented regime candidate evaluation."""
from __future__ import annotations

import math
from typing import Sequence

import pandas as pd

from research.performance import portfolio_metrics
from research.regime.evaluation import _policy_by_id, _public_row, _score_1_100
from research.regime.policies import (
    BASELINE_IDS,
    CHAMPION_POLICY,
    TREND_BREADTH_POLICY,
    TREND_ONLY_POLICY,
    apply_policy,
    walk_forward_splits,
)
from research.regime_types import PromotionGateResult, RegimePolicy

DEFAULT_EXPOSURE_MAP = {
    "risk_on": {"equity": 0.80, "defensive": 0.20},
    "neutral": {"equity": 0.40, "defensive": 0.60},
    "risk_off": {"equity": 0.10, "defensive": 0.90},
}

PROFIT_REQUIRED_BASELINES = {
    "buy_and_hold_equity",
    "fixed_60_40",
    "ma_20_60_timing",
}

PROFIT_BASELINE_NAMES = [
    "buy_and_hold_equity",
    "fixed_80_20",
    "fixed_60_40",
    "fixed_40_60",
    "cash_only",
    "ma_20_60_timing",
    "ma_60_120_timing",
    "trend_only_regime",
    "trend_breadth_regime",
    "current_champion_formula",
    "best_challenger",
]

def _profit_regime_series(regimes: pd.Series) -> pd.Series:
    mapping = {"bull": "risk_on", "sideways": "neutral", "bear": "risk_off"}
    return regimes.map(lambda value: mapping.get(str(value), str(value)))


def simulate_tradable_exposure(
    asset_panel: pd.DataFrame,
    regime_series: pd.Series,
    exposure_map: dict[str, dict[str, float]] | None = None,
) -> dict[str, float | pd.Series]:
    """Convert risk-on/neutral/risk-off states into tradable daily returns."""
    exposure_map = exposure_map or DEFAULT_EXPOSURE_MAP
    panel = asset_panel.sort_index().copy()
    regimes = _profit_regime_series(regime_series).reindex(panel.index).ffill().fillna("neutral")
    equity_weight = regimes.map(lambda regime: exposure_map.get(str(regime), exposure_map["neutral"])["equity"]).astype(float)
    defensive_weight = regimes.map(lambda regime: exposure_map.get(str(regime), exposure_map["neutral"])["defensive"]).astype(float)

    tradable_equity = equity_weight.shift(1).fillna(exposure_map["neutral"]["equity"])
    tradable_defensive = defensive_weight.shift(1).fillna(exposure_map["neutral"]["defensive"])
    daily_return = tradable_equity * panel["equity_return"].astype(float) + tradable_defensive * panel["defensive_return"].astype(float)
    metrics = portfolio_metrics(daily_return)
    stats = regimes.value_counts(normalize=True)
    metrics.update(
        {
            "turnover_proxy": round(float(equity_weight.diff().abs().sum()), 6),
            "risk_on_ratio": round(float(stats.get("risk_on", 0.0)), 6),
            "neutral_ratio": round(float(stats.get("neutral", 0.0)), 6),
            "risk_off_ratio": round(float(stats.get("risk_off", 0.0)), 6),
        }
    )
    return metrics


def _scalar_metrics(metrics: dict) -> dict:
    return {key: value for key, value in metrics.items() if not isinstance(value, pd.Series)}


def _max_single_profit_regime(metrics: dict) -> float:
    return max(
        float(metrics.get("risk_on_ratio", 0.0)),
        float(metrics.get("neutral_ratio", 0.0)),
        float(metrics.get("risk_off_ratio", 0.0)),
    )


def profit_score_candidate(
    metrics: dict,
    baselines: Sequence[dict] | None = None,
    regime_distribution: dict[str, float] | None = None,
    *,
    complexity: int = 1,
) -> dict[str, float]:
    """Score a candidate by tradable OOS-style portfolio quality."""
    baselines = list(baselines or [])
    regime_distribution = regime_distribution or {
        "risk_on_ratio": float(metrics.get("risk_on_ratio", 0.0)),
        "neutral_ratio": float(metrics.get("neutral_ratio", 0.0)),
        "risk_off_ratio": float(metrics.get("risk_off_ratio", 0.0)),
    }
    calmar = float(metrics.get("calmar", 0.0))
    sharpe = float(metrics.get("sharpe", 0.0))
    cagr = float(metrics.get("cagr", 0.0))
    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    turnover = float(metrics.get("turnover_proxy", 0.0))
    max_single = max(float(regime_distribution.get(key, 0.0)) for key in ("risk_on_ratio", "neutral_ratio", "risk_off_ratio"))
    collapse_penalty = max(0.0, max_single - 0.85) * 120.0
    collapse_penalty += max(0.0, 0.10 - float(regime_distribution.get("risk_on_ratio", 0.0))) * 100.0
    collapse_penalty += max(0.0, float(regime_distribution.get("risk_off_ratio", 0.0)) - 0.70) * 100.0

    baseline_bonus = 0.0
    for row in baselines:
        if calmar > float(row.get("calmar", 0.0)):
            baseline_bonus += 2.0
        if sharpe > float(row.get("sharpe", 0.0)):
            baseline_bonus += 1.0
    raw = (
        50.0
        + calmar * 8.0
        + sharpe * 10.0
        + cagr * 120.0
        + max_drawdown * 80.0
        + baseline_bonus
        - turnover * 0.15
        - complexity * 1.25
        - collapse_penalty
    )
    score = _score_1_100(raw)
    return {
        "profit_score": round(score, 4),
        "collapse_penalty": round(float(collapse_penalty), 4),
        "baseline_bonus": round(float(baseline_bonus), 4),
    }


def _fixed_allocation_metrics(asset_panel: pd.DataFrame, equity_weight: float) -> dict:
    panel = asset_panel.sort_index()
    daily = equity_weight * panel["equity_return"].astype(float) + (1.0 - equity_weight) * panel["defensive_return"].astype(float)
    metrics = portfolio_metrics(daily)
    metrics["turnover_proxy"] = 0.0
    metrics["risk_on_ratio"] = 1.0 if equity_weight >= 0.8 else 0.0
    metrics["neutral_ratio"] = 1.0 if 0.2 < equity_weight < 0.8 else 0.0
    metrics["risk_off_ratio"] = 1.0 if equity_weight <= 0.2 else 0.0
    return metrics


def _ma_timing_regime(asset_panel: pd.DataFrame, fast: int, slow: int) -> pd.Series:
    close = asset_panel["equity_close"].astype(float)
    ma_fast = close.rolling(fast, min_periods=max(5, fast // 2)).mean()
    ma_slow = close.rolling(slow, min_periods=max(10, slow // 2)).mean()
    values = []
    for idx in close.index:
        if pd.notna(ma_fast.loc[idx]) and pd.notna(ma_slow.loc[idx]) and close.loc[idx] > ma_fast.loc[idx] > ma_slow.loc[idx]:
            values.append("risk_on")
        elif pd.notna(ma_slow.loc[idx]) and close.loc[idx] < ma_slow.loc[idx]:
            values.append("risk_off")
        else:
            values.append("neutral")
    return pd.Series(values, index=close.index)


def _policy_profit_metrics(features: pd.DataFrame, asset_panel: pd.DataFrame, policy: RegimePolicy) -> dict:
    applied = apply_policy(features, policy)
    regimes = _profit_regime_series(applied["regime"])
    metrics = simulate_tradable_exposure(asset_panel, regimes, DEFAULT_EXPOSURE_MAP)
    score = profit_score_candidate(metrics, complexity=policy.complexity)
    out = {**_scalar_metrics(metrics), **score}
    out["candidate_id"] = policy.candidate_id
    out["policy"] = policy
    return out


def _profit_candidate_rows(features: pd.DataFrame, asset_panel: pd.DataFrame, policies: Sequence[RegimePolicy]) -> list[dict]:
    rows = [_policy_profit_metrics(features, asset_panel, policy) for policy in policies]
    return sorted(rows, key=lambda row: (float(row.get("profit_score", 0.0)), float(row.get("calmar", 0.0))), reverse=True)


def _baseline_row(strategy: str, metrics: dict, candidate_id: str | None = None) -> dict:
    row = {"strategy": strategy, **_scalar_metrics(metrics)}
    if candidate_id:
        row["candidate_id"] = candidate_id
    score = profit_score_candidate(row, complexity=1)
    row.update(score)
    return row


def build_profit_baseline_rows(features: pd.DataFrame, asset_panel: pd.DataFrame, best_policy: RegimePolicy) -> list[dict]:
    """Return strong profit baselines and current/best regime A/B rows."""
    rows = [
        _baseline_row("buy_and_hold_equity", _fixed_allocation_metrics(asset_panel, 1.0)),
        _baseline_row("fixed_80_20", _fixed_allocation_metrics(asset_panel, 0.80)),
        _baseline_row("fixed_60_40", _fixed_allocation_metrics(asset_panel, 0.60)),
        _baseline_row("fixed_40_60", _fixed_allocation_metrics(asset_panel, 0.40)),
        _baseline_row("cash_only", _fixed_allocation_metrics(asset_panel, 0.0)),
        _baseline_row("ma_20_60_timing", simulate_tradable_exposure(asset_panel, _ma_timing_regime(asset_panel, 20, 60), DEFAULT_EXPOSURE_MAP)),
        _baseline_row("ma_60_120_timing", simulate_tradable_exposure(asset_panel, _ma_timing_regime(asset_panel, 60, 120), DEFAULT_EXPOSURE_MAP)),
        _baseline_row(
            "trend_only_regime",
            simulate_tradable_exposure(asset_panel, _profit_regime_series(apply_policy(features, TREND_ONLY_POLICY)["regime"]), DEFAULT_EXPOSURE_MAP),
            TREND_ONLY_POLICY.candidate_id,
        ),
        _baseline_row(
            "trend_breadth_regime",
            simulate_tradable_exposure(asset_panel, _profit_regime_series(apply_policy(features, TREND_BREADTH_POLICY)["regime"]), DEFAULT_EXPOSURE_MAP),
            TREND_BREADTH_POLICY.candidate_id,
        ),
        _baseline_row(
            "current_champion_formula",
            simulate_tradable_exposure(asset_panel, _profit_regime_series(apply_policy(features, CHAMPION_POLICY)["regime"]), DEFAULT_EXPOSURE_MAP),
            CHAMPION_POLICY.candidate_id,
        ),
        _baseline_row(
            "best_challenger",
            simulate_tradable_exposure(asset_panel, _profit_regime_series(apply_policy(features, best_policy)["regime"]), DEFAULT_EXPOSURE_MAP),
            best_policy.candidate_id,
        ),
    ]
    by_name = {row["strategy"]: row for row in rows}
    return [by_name[name] for name in PROFIT_BASELINE_NAMES if name in by_name]


def _profit_walk_forward_rows(
    features: pd.DataFrame,
    asset_panel: pd.DataFrame,
    policies: Sequence[RegimePolicy],
) -> list[dict]:
    rows: list[dict] = []
    index = pd.DatetimeIndex(features.index)
    for train_idx, validate_idx in walk_forward_splits(index):
        train_features = features.loc[train_idx]
        train_panel = asset_panel.loc[asset_panel.index.intersection(train_idx)]
        validate_features = features.loc[validate_idx]
        validate_panel = asset_panel.loc[asset_panel.index.intersection(validate_idx)]
        if len(train_features) < 252 or len(validate_features) < 60 or len(train_panel) < 252 or len(validate_panel) < 60:
            continue
        ranked = _profit_candidate_rows(train_features, train_panel, policies)
        ranked = [row for row in ranked if row["candidate_id"] not in BASELINE_IDS]
        if not ranked:
            continue
        selected_policy = ranked[0]["policy"]
        champion = _policy_profit_metrics(validate_features, validate_panel, CHAMPION_POLICY)
        challenger = _policy_profit_metrics(validate_features, validate_panel, selected_policy)
        rows.append(
            {
                "train_start": str(train_idx.min().date()),
                "train_end": str(train_idx.max().date()),
                "validate_start": str(validate_idx.min().date()),
                "validate_end": str(validate_idx.max().date()),
                "selected_candidate": selected_policy.candidate_id,
                "champion_profit_score": champion["profit_score"],
                "challenger_profit_score": challenger["profit_score"],
                "profit_score_delta": round(float(challenger["profit_score"]) - float(champion["profit_score"]), 4),
                "champion_calmar": champion["calmar"],
                "challenger_calmar": challenger["calmar"],
                "champion_sharpe": champion["sharpe"],
                "challenger_sharpe": challenger["sharpe"],
                "champion_cagr": champion["cagr"],
                "challenger_cagr": challenger["cagr"],
                "winner": "challenger" if float(challenger["profit_score"]) > float(champion["profit_score"]) else "champion",
            }
        )
    return rows


def _beats_required_profit_baselines(challenger_metrics: dict, baseline_rows: Sequence[dict]) -> bool:
    by_name = {row.get("strategy"): row for row in baseline_rows}
    for name in PROFIT_REQUIRED_BASELINES:
        baseline = by_name.get(name)
        if not baseline:
            return False
        challenger_calmar = float(challenger_metrics.get("calmar", 0.0))
        challenger_sharpe = float(challenger_metrics.get("sharpe", 0.0))
        challenger_cagr = float(challenger_metrics.get("cagr", 0.0))
        baseline_calmar = float(baseline.get("calmar", 0.0))
        baseline_sharpe = float(baseline.get("sharpe", 0.0))
        baseline_cagr = float(baseline.get("cagr", 0.0))
        if challenger_calmar <= baseline_calmar and challenger_sharpe <= baseline_sharpe:
            return False
        if challenger_cagr < baseline_cagr - 0.02:
            return False
    return True


def _as_reason_text(values: Sequence[str]) -> str:
    return "|".join(values)


def _finite_metric_set(row: dict, keys: Sequence[str]) -> bool:
    for key in keys:
        try:
            value = float(row.get(key, 0.0))
        except (TypeError, ValueError):
            return False
        if not math.isfinite(value):
            return False
    return True


def _validation_summary_by_id(validation_rows: Sequence[dict]) -> dict[str, dict]:
    return {str(row.get("candidate_id", "")): dict(row) for row in validation_rows}


def build_profit_gate_diagnostics(
    candidate_rows: Sequence[dict],
    champion_metrics: dict,
    baseline_rows: Sequence[dict],
    validation_summary_rows: Sequence[dict] | None = None,
    *,
    min_oos_windows: int = 3,
    min_oos_win_rate: float = 0.50,
    max_single_regime_ratio: float = 0.90,
    max_risk_off_ratio: float = 0.85,
    min_abs_risk_on_ratio: float = 0.01,
) -> list[dict]:
    """Evaluate champion and candidate formulas under the same V3 diagnostics."""
    validation_by_id = _validation_summary_by_id(validation_summary_rows or [])
    champion_turnover = float(champion_metrics.get("turnover_proxy", 0.0))
    turnover_limit = max(80.0, champion_turnover * 1.25)
    champion_risk_on = float(champion_metrics.get("risk_on_ratio", 0.0))
    rows: list[dict] = []

    for row in candidate_rows:
        candidate_id = str(row.get("candidate_id", ""))
        role = "champion" if candidate_id == CHAMPION_POLICY.candidate_id else "candidate"
        failed: list[str] = []
        warnings: list[str] = []
        metrics_finite = _finite_metric_set(row, ["cagr", "sharpe", "calmar", "max_drawdown", "turnover_proxy"])
        if not metrics_finite:
            failed.append("nonfinite_metrics")

        risk_on = float(row.get("risk_on_ratio", 0.0))
        neutral = float(row.get("neutral_ratio", 0.0))
        risk_off = float(row.get("risk_off_ratio", 0.0))
        max_single = max(risk_on, neutral, risk_off)
        turnover = float(row.get("turnover_proxy", 0.0))

        if max_single > max_single_regime_ratio:
            failed.append("permanent_regime_collapse")
        if risk_on <= min_abs_risk_on_ratio:
            failed.append("no_risk_on_participation")
        elif champion_risk_on > 0 and risk_on < champion_risk_on * 0.50:
            warnings.append("low_risk_on_participation")
        if risk_off > max_risk_off_ratio:
            failed.append("excessive_risk_off_dominance")
        if role != "champion" and turnover > turnover_limit:
            failed.append("excessive_turnover_vs_champion")

        if role != "champion" and not _beats_required_profit_baselines(row, baseline_rows):
            failed.append("fails_required_baselines")

        validation = validation_by_id.get(candidate_id, {})
        oos_windows = int(validation.get("oos_windows", 0))
        oos_win_rate = float(validation.get("oos_win_rate_vs_champion", 0.0))
        oos_delta = float(validation.get("oos_profit_score_delta_mean", 0.0))
        if role != "champion":
            if oos_windows < min_oos_windows:
                failed.append("insufficient_oos_evidence")
            if oos_windows >= min_oos_windows and oos_win_rate < min_oos_win_rate and oos_delta <= 0:
                failed.append("weak_oos_vs_champion")

        rows.append(
            {
                "candidate_id": candidate_id,
                "role": role,
                "passes_validation": len(failed) == 0,
                "failed_gates": _as_reason_text(failed),
                "warnings": _as_reason_text(warnings),
                "turnover_limit": round(turnover_limit, 6),
                "risk_on_ratio": round(risk_on, 6),
                "neutral_ratio": round(neutral, 6),
                "risk_off_ratio": round(risk_off, 6),
                "max_single_regime_ratio": round(max_single, 6),
                "oos_windows": oos_windows,
                "oos_win_rate_vs_champion": round(oos_win_rate, 6),
                "oos_profit_score_delta_mean": round(oos_delta, 6),
            }
        )
    return rows


def select_best_validated_formula(
    candidate_rows: Sequence[dict],
    gate_rows: Sequence[dict],
    validation_summary_rows: Sequence[dict] | None = None,
) -> dict:
    """Select the highest ranked formula that passed V3 validation gates."""
    gate_by_id = {str(row.get("candidate_id", "")): row for row in gate_rows}
    validation_by_id = _validation_summary_by_id(validation_summary_rows or [])

    def sort_key(row: dict) -> tuple[float, float, float, float, float]:
        candidate_id = str(row.get("candidate_id", ""))
        validation = validation_by_id.get(candidate_id, {})
        return (
            float(validation.get("oos_profit_score_delta_mean", 0.0)),
            float(validation.get("oos_calmar_mean", 0.0)),
            float(validation.get("oos_sharpe_mean", 0.0)),
            float(row.get("profit_score", 0.0)),
            float(row.get("calmar", 0.0)),
        )

    ranked = sorted(
        [dict(row) for row in candidate_rows],
        key=sort_key if validation_by_id else lambda row: (float(row.get("profit_score", 0.0)), float(row.get("calmar", 0.0)), float(row.get("sharpe", 0.0))),
        reverse=True,
    )
    for row in ranked:
        gate = gate_by_id.get(str(row.get("candidate_id", "")), {})
        if bool(gate.get("passes_validation", False)):
            return row
    return {}


def _profit_candidate_validation_summary_rows(
    features: pd.DataFrame,
    asset_panel: pd.DataFrame,
    policies: Sequence[RegimePolicy],
) -> list[dict]:
    """Evaluate every formula across validation windows against the champion."""
    rows: list[dict] = []
    index = pd.DatetimeIndex(features.index)
    for _train_idx, validate_idx in walk_forward_splits(index):
        validate_features = features.loc[validate_idx]
        validate_panel = asset_panel.loc[asset_panel.index.intersection(validate_idx)]
        if len(validate_features) < 60 or len(validate_panel) < 60:
            continue
        champion = _policy_profit_metrics(validate_features, validate_panel, CHAMPION_POLICY)
        for policy in policies:
            metrics = _policy_profit_metrics(validate_features, validate_panel, policy)
            rows.append(
                {
                    "candidate_id": policy.candidate_id,
                    "oos_window_start": str(validate_idx.min().date()),
                    "oos_window_end": str(validate_idx.max().date()),
                    "oos_profit_score": metrics["profit_score"],
                    "oos_profit_score_delta": round(float(metrics["profit_score"]) - float(champion["profit_score"]), 6),
                    "oos_calmar": metrics["calmar"],
                    "oos_sharpe": metrics["sharpe"],
                    "oos_cagr": metrics["cagr"],
                    "oos_max_drawdown": metrics["max_drawdown"],
                    "winner_vs_champion": "candidate" if float(metrics["profit_score"]) > float(champion["profit_score"]) else "champion",
                }
            )

    if not rows:
        return []
    frame = pd.DataFrame(rows)
    summary = []
    for candidate_id, group in frame.groupby("candidate_id", sort=False):
        summary.append(
            {
                "candidate_id": str(candidate_id),
                "oos_windows": int(len(group)),
                "oos_win_rate_vs_champion": round(float((group["winner_vs_champion"] == "candidate").mean()), 6),
                "oos_profit_score_mean": round(float(group["oos_profit_score"].mean()), 6),
                "oos_profit_score_delta_mean": round(float(group["oos_profit_score_delta"].mean()), 6),
                "oos_calmar_mean": round(float(group["oos_calmar"].mean()), 6),
                "oos_sharpe_mean": round(float(group["oos_sharpe"].mean()), 6),
                "oos_cagr_mean": round(float(group["oos_cagr"].mean()), 6),
                "oos_max_drawdown_mean": round(float(group["oos_max_drawdown"].mean()), 6),
            }
        )
    return sorted(summary, key=lambda row: (float(row["oos_profit_score_delta_mean"]), float(row["oos_calmar_mean"])), reverse=True)


def _profit_decision_v3(best_validated: dict, champion_metrics: dict, walk_rows: Sequence[dict]) -> tuple[PromotionGateResult, str]:
    if not walk_rows:
        return PromotionGateResult.INSUFFICIENT_DATA, "insufficient_oos_windows"
    if not best_validated:
        return PromotionGateResult.KEEP_CHAMPION, "no_validated_formula_keep_current_temporarily"
    if str(best_validated.get("candidate_id")) == CHAMPION_POLICY.candidate_id:
        return PromotionGateResult.KEEP_CHAMPION, "champion_is_best_validated_formula"
    calmar_delta = float(best_validated.get("calmar", 0.0)) - float(champion_metrics.get("calmar", 0.0))
    sharpe_delta = float(best_validated.get("sharpe", 0.0)) - float(champion_metrics.get("sharpe", 0.0))
    cagr_delta = float(best_validated.get("cagr", 0.0)) - float(champion_metrics.get("cagr", 0.0))
    maxdd_delta = float(best_validated.get("max_drawdown", 0.0)) - float(champion_metrics.get("max_drawdown", 0.0))
    if calmar_delta >= 0.05 and sharpe_delta >= 0.02 and cagr_delta >= -0.005 and maxdd_delta >= -0.02:
        return PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW, "validated_challenger_beats_champion"
    return PromotionGateResult.KEEP_CHAMPION, "validated_candidate_does_not_clear_replacement_margin"


def decide_profit_promotion(
    *,
    champion_metrics: dict,
    challenger_metrics: dict,
    baseline_rows: Sequence[dict],
    walk_forward_rows: Sequence[dict],
    min_risk_on_ratio: float = 0.10,
    max_risk_off_ratio: float = 0.70,
    max_single_regime_ratio: float = 0.85,
    max_turnover_proxy: float = 80.0,
    min_validation_win_rate: float = 0.60,
) -> PromotionGateResult:
    if not walk_forward_rows:
        return PromotionGateResult.INSUFFICIENT_DATA
    if float(challenger_metrics.get("risk_on_ratio", 0.0)) < min_risk_on_ratio:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("risk_off_ratio", 0.0)) > max_risk_off_ratio:
        return PromotionGateResult.KEEP_CHAMPION
    if _max_single_profit_regime(challenger_metrics) > max_single_regime_ratio:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("turnover_proxy", 0.0)) > max_turnover_proxy:
        return PromotionGateResult.KEEP_CHAMPION
    wins = sum(row.get("winner") == "challenger" for row in walk_forward_rows)
    win_rate = wins / len(walk_forward_rows)
    if win_rate < min_validation_win_rate:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("calmar", 0.0)) <= float(champion_metrics.get("calmar", 0.0)) + 0.05:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("sharpe", 0.0)) <= float(champion_metrics.get("sharpe", 0.0)) + 0.02:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("cagr", 0.0)) < float(champion_metrics.get("cagr", 0.0)) - 0.01:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("max_drawdown", 0.0)) < float(champion_metrics.get("max_drawdown", 0.0)) - 0.02:
        return PromotionGateResult.KEEP_CHAMPION
    if not _beats_required_profit_baselines(challenger_metrics, baseline_rows):
        return PromotionGateResult.KEEP_CHAMPION
    return PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW


def _select_oos_best_policy(walk_rows: Sequence[dict], policies: Sequence[RegimePolicy], fallback: RegimePolicy) -> RegimePolicy:
    if not walk_rows:
        return fallback
    scores = pd.DataFrame(list(walk_rows))
    if scores.empty or "selected_candidate" not in scores:
        return fallback
    grouped = scores.groupby("selected_candidate")["challenger_profit_score"].mean().sort_values(ascending=False)
    for candidate_id in grouped.index:
        policy = _policy_by_id(policies, str(candidate_id))
        if policy is not None:
            return policy
    return fallback


def _profit_regime_distribution_rows(features: pd.DataFrame, policies: Sequence[RegimePolicy]) -> list[dict]:
    rows = []
    for policy in policies:
        regimes = _profit_regime_series(apply_policy(features, policy)["regime"])
        stats = regimes.value_counts(normalize=True)
        rows.append(
            {
                "candidate_id": policy.candidate_id,
                "risk_on_ratio": round(float(stats.get("risk_on", 0.0)), 6),
                "neutral_ratio": round(float(stats.get("neutral", 0.0)), 6),
                "risk_off_ratio": round(float(stats.get("risk_off", 0.0)), 6),
                "max_single_regime_ratio": round(float(stats.max()) if len(stats) else 0.0, 6),
            }
        )
    return rows


def _profit_event_study_rows(labels: pd.DataFrame, policies: Sequence[RegimePolicy], features: pd.DataFrame) -> list[dict]:
    rows = []
    for policy in policies:
        regimes = _profit_regime_series(apply_policy(features, policy)["regime"])
        data = labels.join(regimes.rename("regime"), how="inner")
        for regime in ("risk_on", "neutral", "risk_off"):
            subset = data[data["regime"] == regime]
            rows.append(
                {
                    "candidate_id": policy.candidate_id,
                    "regime": regime,
                    "observations": int(len(subset)),
                    "future_20d_equity_return": round(float(subset["future_20d_equity_return"].mean()), 6) if "future_20d_equity_return" in subset and len(subset) else 0.0,
                    "future_20d_equity_max_drawdown": round(float(subset["future_20d_equity_max_drawdown"].mean()), 6) if "future_20d_equity_max_drawdown" in subset and len(subset) else 0.0,
                    "risk_on_profitable_rate": round(float(subset["risk_on_profitable_next_20d"].mean()), 6) if "risk_on_profitable_next_20d" in subset and len(subset) else 0.0,
                    "risk_off_preferred_rate": round(float(subset["risk_off_preferred_next_20d"].mean()), 6) if "risk_off_preferred_next_20d" in subset and len(subset) else 0.0,
                }
            )
    return rows
