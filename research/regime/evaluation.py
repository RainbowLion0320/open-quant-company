"""Champion/challenger regime policy evaluation."""
from __future__ import annotations

import math
from typing import Sequence

import pandas as pd

from research.performance import portfolio_metrics
from research.regime.features import build_forward_labels, build_regime_feature_history, load_full_market_breadth_history
from research.regime.policies import (
    BASELINE_IDS,
    CHAMPION_POLICY,
    TREND_BREADTH_POLICY,
    TREND_ONLY_POLICY,
    apply_policy,
    generate_candidate_policies,
    stability_stats,
    walk_forward_splits,
)
from research.regime_types import PromotionGateResult, RegimePolicy

def decide_promotion(
    *,
    champion_score: float,
    challenger_score: float,
    challenger_maxdd_delta: float,
    challenger_turnover_delta: float,
    beats_baselines: bool,
    valid_year_win_rate: float,
    regime_diversified: bool = True,
) -> PromotionGateResult:
    if champion_score <= 0 or challenger_score <= 0:
        return PromotionGateResult.INSUFFICIENT_DATA
    if not regime_diversified:
        return PromotionGateResult.KEEP_CHAMPION
    if challenger_score < champion_score + 2.0:
        return PromotionGateResult.KEEP_CHAMPION
    if challenger_maxdd_delta < -0.02:
        return PromotionGateResult.KEEP_CHAMPION
    if challenger_turnover_delta > 0.20:
        return PromotionGateResult.KEEP_CHAMPION
    if valid_year_win_rate < 0.60:
        return PromotionGateResult.KEEP_CHAMPION
    if not beats_baselines:
        return PromotionGateResult.KEEP_CHAMPION
    return PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW


def _group_mean(data: pd.DataFrame, regime: str, column: str) -> float:
    subset = data.loc[data["regime"] == regime, column].dropna()
    return float(subset.mean()) if len(subset) else 0.0


def _safe_corr(left: pd.Series, right: pd.Series) -> float:
    pair = pd.concat([left, right], axis=1).dropna()
    if len(pair) < 10:
        return 0.0
    if pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
        return 0.0
    value = pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman")
    return float(value) if pd.notna(value) else 0.0


def _score_1_100(value: float) -> float:
    if not math.isfinite(value):
        return 1.0
    return max(1.0, min(100.0, value))


def evaluate_policy(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    close: pd.Series,
    policy: RegimePolicy,
) -> dict[str, float | str]:
    applied = apply_policy(features, policy)
    data = applied.join(labels, how="inner")
    stats = stability_stats(data["regime"])
    return20 = "future_20d_return"
    drawdown20 = "future_20d_max_drawdown"

    bull_ret = _group_mean(data, "bull", return20)
    sideways_ret = _group_mean(data, "sideways", return20)
    bear_ret = _group_mean(data, "bear", return20)
    bear_dd = _group_mean(data, "bear", drawdown20)
    nonbear_dd = data.loc[data["regime"] != "bear", drawdown20].dropna().mean()
    nonbear_dd = float(nonbear_dd) if pd.notna(nonbear_dd) else 0.0
    ret_separation = (bull_ret - bear_ret) * 100.0
    order_bonus = 10.0 if bull_ret >= sideways_ret >= bear_ret else 0.0
    risk_separation = max(0.0, (nonbear_dd - bear_dd) * 100.0)
    score_ic = _safe_corr(data["score"], data[return20])
    predictive_score = _score_1_100(50.0 + ret_separation * 3.0 + risk_separation * 2.0 + order_bonus + score_ic * 10.0)

    sim = simulate_regime_allocation(close, data["regime"])
    max_regime_ratio = max(stats["bull_ratio"], stats["bear_ratio"], stats["sideways_ratio"])
    collapse_penalty = max(0.0, max_regime_ratio - 0.85) * 80.0
    composite = (
        0.45 * predictive_score
        + 0.35 * sim["strategy_score"]
        + 0.10 * max(0.0, min(100.0, stats["avg_dwell"]))
        - 0.15 * stats["turnovers"]
        - 1.50 * policy.complexity
        - collapse_penalty
    )
    composite = _score_1_100(composite)
    return {
        "candidate_id": policy.candidate_id,
        "predictive_score": round(float(predictive_score), 4),
        "strategy_score": round(float(sim["strategy_score"]), 4),
        "composite_score": round(float(composite), 4),
        "bull_future_20d_return": round(bull_ret, 6),
        "sideways_future_20d_return": round(sideways_ret, 6),
        "bear_future_20d_return": round(bear_ret, 6),
        "bear_future_20d_drawdown": round(bear_dd, 6),
        "score_ic_20d": round(score_ic, 6),
        "turnovers": round(stats["turnovers"], 4),
        "avg_dwell": round(stats["avg_dwell"], 4),
        "bull_ratio": round(stats["bull_ratio"], 6),
        "bear_ratio": round(stats["bear_ratio"], 6),
        "sideways_ratio": round(stats["sideways_ratio"], 6),
        "max_regime_ratio": round(max_regime_ratio, 6),
        "collapse_penalty": round(collapse_penalty, 4),
        "complexity": float(policy.complexity),
        "cagr": sim["cagr"],
        "sharpe": sim["sharpe"],
        "max_drawdown": sim["max_drawdown"],
        "calmar": sim["calmar"],
        "turnover_proxy": sim["turnover_proxy"],
        "policy": policy,
    }


def rank_candidate_rows(rows: Sequence[dict]) -> list[dict]:
    ranked = []
    for row in rows:
        enriched = dict(row)
        if "composite_score" not in enriched:
            max_regime_ratio = max(
                float(enriched.get("bull_ratio", 0.0)),
                float(enriched.get("bear_ratio", 0.0)),
                float(enriched.get("sideways_ratio", 0.0)),
            )
            collapse_penalty = max(0.0, max_regime_ratio - 0.85) * 80.0
            enriched["composite_score"] = _score_1_100(
                0.45 * float(enriched.get("predictive_score", 0.0))
                + 0.35 * float(enriched.get("strategy_score", 0.0))
                - 0.15 * float(enriched.get("turnovers", 0.0))
                - 1.50 * float(enriched.get("complexity", 1.0))
                - collapse_penalty
            )
        ranked.append(enriched)
    return sorted(ranked, key=lambda r: (float(r.get("composite_score", 0.0)), float(r.get("predictive_score", 0.0))), reverse=True)


def simulate_regime_allocation(close: pd.Series, regimes: pd.Series | None = None, fixed_exposure: float | None = None) -> dict[str, float]:
    close = close.sort_index().astype(float)
    returns = close.pct_change().fillna(0.0)
    if fixed_exposure is not None:
        exposure = pd.Series(float(fixed_exposure), index=returns.index)
    else:
        aligned = regimes.reindex(returns.index).ffill().fillna("sideways") if regimes is not None else pd.Series("sideways", index=returns.index)
        exposure = aligned.map({"bull": 0.60, "sideways": 0.35, "bear": 0.10}).fillna(0.35)
        exposure = exposure.shift(1).fillna(0.35)
    strategy_returns = returns * exposure
    turnover_proxy = float(exposure.diff().abs().sum())
    metrics = portfolio_metrics(strategy_returns, turnover_proxy=turnover_proxy, include_series=False)
    strategy_score = _score_1_100(
        50.0
        + float(metrics["sharpe"]) * 10.0
        + float(metrics["calmar"]) * 3.0
        + float(metrics["max_drawdown"]) * 100.0
        - turnover_proxy * 0.2
    )
    return {
        "cagr": metrics["cagr"],
        "sharpe": metrics["sharpe"],
        "max_drawdown": metrics["max_drawdown"],
        "calmar": metrics["calmar"],
        "turnover_proxy": metrics["turnover_proxy"],
        "strategy_score": round(strategy_score, 4),
    }


def _public_row(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "policy"}


def _policy_by_id(policies: Sequence[RegimePolicy], candidate_id: str) -> RegimePolicy | None:
    for policy in policies:
        if policy.candidate_id == candidate_id:
            return policy
    return None


def _evaluate_many(features: pd.DataFrame, labels: pd.DataFrame, close: pd.Series, policies: Sequence[RegimePolicy]) -> list[dict]:
    return [evaluate_policy(features, labels, close, policy) for policy in policies]


def _walk_forward_rows(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    close: pd.Series,
    policies: Sequence[RegimePolicy],
) -> list[dict]:
    rows = []
    index = pd.DatetimeIndex(features.index)
    for train_idx, validate_idx in walk_forward_splits(index):
        train_features = features.loc[train_idx]
        train_labels = labels.loc[labels.index.intersection(train_idx)]
        train_close = close.loc[close.index.intersection(train_idx)]
        validate_features = features.loc[validate_idx]
        validate_labels = labels.loc[labels.index.intersection(validate_idx)]
        validate_close = close.loc[close.index.intersection(validate_idx)]
        if len(train_features) < 120 or len(validate_features) < 40:
            continue
        train_ranked = rank_candidate_rows(_evaluate_many(train_features, train_labels, train_close, policies))
        best_id = train_ranked[0]["candidate_id"] if train_ranked else ""
        best_policy = _policy_by_id(policies, best_id)
        if best_policy is None:
            continue
        champion = evaluate_policy(validate_features, validate_labels, validate_close, CHAMPION_POLICY)
        challenger = evaluate_policy(validate_features, validate_labels, validate_close, best_policy)
        rows.append(
            {
                "train_start": str(train_idx.min().date()),
                "train_end": str(train_idx.max().date()),
                "validate_start": str(validate_idx.min().date()),
                "validate_end": str(validate_idx.max().date()),
                "selected_candidate": best_id,
                "champion_score": champion["composite_score"],
                "challenger_score": challenger["composite_score"],
                "score_delta": round(float(challenger["composite_score"]) - float(champion["composite_score"]), 4),
                "winner": "challenger" if float(challenger["composite_score"]) > float(champion["composite_score"]) else "champion",
            }
        )
    return rows


def run_regime_research(
    features: pd.DataFrame,
    close: pd.Series,
    *,
    policies: Sequence[RegimePolicy] | None = None,
) -> dict:
    features = features.sort_index()
    close = close.sort_index().reindex(features.index).ffill().dropna()
    features = features.loc[features.index.intersection(close.index)]
    labels = build_forward_labels(close)
    if len(features) < 252:
        return {
            "decision": PromotionGateResult.INSUFFICIENT_DATA.value,
            "champion_score": 0.0,
            "best_challenger_score": 0.0,
            "best_challenger_id": "",
            "candidate_rows": [],
            "walk_forward_rows": [],
            "strategy_rows": [],
            "stability_rows": [],
            "component_rows": [],
            "event_rows": [],
            "notes": ["insufficient_data: need at least 252 feature rows"],
            "features": features,
            "labels": labels,
        }

    candidate_policies = list(policies) if policies is not None else generate_candidate_policies()
    policy_ids = {policy.candidate_id for policy in candidate_policies}
    for baseline in (TREND_ONLY_POLICY, TREND_BREADTH_POLICY):
        if baseline.candidate_id not in policy_ids:
            candidate_policies.insert(0, baseline)
            policy_ids.add(baseline.candidate_id)

    champion = evaluate_policy(features, labels, close, CHAMPION_POLICY)
    candidate_rows_with_policy = rank_candidate_rows(_evaluate_many(features, labels, close, candidate_policies))
    non_baseline = [row for row in candidate_rows_with_policy if row["candidate_id"] not in BASELINE_IDS]
    best = non_baseline[0] if non_baseline else (candidate_rows_with_policy[0] if candidate_rows_with_policy else champion)
    best_policy = best.get("policy", CHAMPION_POLICY)
    best_series = apply_policy(features, best_policy)["regime"] if isinstance(best_policy, RegimePolicy) else apply_policy(features, CHAMPION_POLICY)["regime"]
    champion_series = apply_policy(features, CHAMPION_POLICY)["regime"]
    trend_series = apply_policy(features, TREND_ONLY_POLICY)["regime"]
    trend_breadth_series = apply_policy(features, TREND_BREADTH_POLICY)["regime"]

    fixed = simulate_regime_allocation(close, fixed_exposure=0.35)
    strategy_rows = [
        {"strategy": "no_regime_fixed_allocation", **fixed},
        {"strategy": "champion_current_formula", **simulate_regime_allocation(close, champion_series)},
        {"strategy": "trend_only_baseline", **simulate_regime_allocation(close, trend_series)},
        {"strategy": "trend_breadth_baseline", **simulate_regime_allocation(close, trend_breadth_series)},
        {"strategy": "best_challenger", **simulate_regime_allocation(close, best_series), "candidate_id": best["candidate_id"]},
    ]

    walk_rows = _walk_forward_rows(features, labels, close, candidate_policies)
    valid_year_win_rate = (
        sum(row["winner"] == "challenger" for row in walk_rows) / len(walk_rows)
        if walk_rows
        else 0.0
    )
    baseline_scores = {
        row["strategy"]: float(row.get("strategy_score", 0.0))
        for row in strategy_rows
        if row["strategy"] in {"trend_only_baseline", "trend_breadth_baseline"}
    }
    best_strategy_score = float(strategy_rows[-1].get("strategy_score", 0.0))
    beats_baselines = best_strategy_score >= max(baseline_scores.values(), default=0.0)
    champion_strategy = strategy_rows[1]
    best_strategy = strategy_rows[-1]
    decision = decide_promotion(
        champion_score=float(champion["composite_score"]),
        challenger_score=float(best["composite_score"]),
        challenger_maxdd_delta=float(best_strategy["max_drawdown"]) - float(champion_strategy["max_drawdown"]),
        challenger_turnover_delta=float(best_strategy["turnover_proxy"]) - float(champion_strategy["turnover_proxy"]),
        beats_baselines=beats_baselines,
        valid_year_win_rate=valid_year_win_rate,
        regime_diversified=float(best.get("max_regime_ratio", 1.0)) <= 0.90,
    )

    candidate_rows = [_public_row(row) for row in candidate_rows_with_policy]
    stability_rows = [
        {"candidate_id": row["candidate_id"], **{key: row[key] for key in ("turnovers", "avg_dwell", "bull_ratio", "bear_ratio", "sideways_ratio", "max_regime_ratio")}}
        for row in candidate_rows
    ]
    component_rows = [
        row for row in candidate_rows
        if row["candidate_id"] in {TREND_ONLY_POLICY.candidate_id, TREND_BREADTH_POLICY.candidate_id, best["candidate_id"]}
    ]
    event_rows = _event_study_rows(labels, champion_series, best_series)
    notes = [
        f"rows={len(features)}",
        f"walk_forward_windows={len(walk_rows)}",
        "production_formula_not_applied",
    ]
    return {
        "decision": decision.value,
        "champion_score": round(float(champion["composite_score"]), 4),
        "best_challenger_score": round(float(best["composite_score"]), 4),
        "best_challenger_id": best["candidate_id"],
        "best_policy": best_policy if isinstance(best_policy, RegimePolicy) else None,
        "candidate_rows": candidate_rows,
        "walk_forward_rows": walk_rows,
        "strategy_rows": strategy_rows,
        "stability_rows": stability_rows,
        "component_rows": component_rows,
        "event_rows": event_rows,
        "notes": notes,
        "features": features,
        "labels": labels,
    }


def _event_study_rows(labels: pd.DataFrame, champion: pd.Series, challenger: pd.Series) -> list[dict]:
    rows = []
    for name, regimes in [("champion_current_formula", champion), ("best_challenger", challenger)]:
        data = labels.join(regimes.rename("regime"), how="inner")
        for regime in ("bull", "sideways", "bear"):
            subset = data[data["regime"] == regime]
            rows.append(
                {
                    "policy": name,
                    "regime": regime,
                    "observations": int(len(subset)),
                    "future_20d_return": round(float(subset["future_20d_return"].mean()), 6) if "future_20d_return" in subset else 0.0,
                    "future_20d_max_drawdown": round(float(subset["future_20d_max_drawdown"].mean()), 6) if "future_20d_max_drawdown" in subset else 0.0,
                }
            )
    return rows
