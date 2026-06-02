"""Profit-oriented Market Regime training and report writing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from research.regime.evaluation import _policy_by_id, _public_row
from research.regime.features import build_profit_labels, build_regime_feature_history
from research.regime.policies import CHAMPION_POLICY, TREND_BREADTH_POLICY, TREND_ONLY_POLICY, generate_candidate_policies
from research.regime.profit_evaluation import (
    _profit_candidate_rows,
    _profit_candidate_validation_summary_rows,
    _profit_decision_v3,
    _profit_event_study_rows,
    _profit_regime_distribution_rows,
    _profit_walk_forward_rows,
    _policy_profit_metrics,
    build_profit_baseline_rows,
    build_profit_gate_diagnostics,
    select_best_validated_formula,
)
from research.regime.reports import _csv, _to_jsonable
from research.regime_types import PromotionGateResult, RegimePolicy

def run_regime_profit_training(
    features: pd.DataFrame,
    asset_panel: pd.DataFrame,
    *,
    policies: Sequence[RegimePolicy] | None = None,
) -> dict:
    """Run profit-oriented Market Regime champion/challenger training."""
    features = features.sort_index().replace([np.inf, -np.inf], np.nan).dropna(subset=["trend_raw", "breadth_raw", "risk_raw", "volume_raw"])
    panel = asset_panel.sort_index().copy()
    common_index = features.index.intersection(panel.index)
    features = features.loc[common_index]
    panel = panel.loc[common_index]
    labels = build_profit_labels(panel)
    notes = list(panel.attrs.get("notes", []))
    if len(features) < 504 or len(panel) < 504:
        return {
            "decision": PromotionGateResult.INSUFFICIENT_DATA.value,
            "best_challenger_id": "",
            "champion_metrics": {},
            "best_challenger_metrics": {},
            "candidate_rows": [],
            "walk_forward_rows": [],
            "baseline_rows": [],
            "regime_exposure_rows": [],
            "regime_distribution_rows": [],
            "event_rows": [],
            "features": features,
            "labels": labels,
            "asset_panel": panel,
            "notes": notes + ["insufficient_data: need at least 504 aligned rows"],
        }

    candidate_policies = list(policies) if policies is not None else generate_candidate_policies()
    policy_ids = {policy.candidate_id for policy in candidate_policies}
    for required in (CHAMPION_POLICY, TREND_ONLY_POLICY, TREND_BREADTH_POLICY):
        if required.candidate_id not in policy_ids:
            candidate_policies.insert(0, required)
            policy_ids.add(required.candidate_id)

    full_rows_with_policy = _profit_candidate_rows(features, panel, candidate_policies)
    full_best = full_rows_with_policy[0] if full_rows_with_policy else {}
    full_best_policy = full_best.get("policy", CHAMPION_POLICY) if full_best else CHAMPION_POLICY
    walk_rows = _profit_walk_forward_rows(features, panel, candidate_policies)
    champion_metrics = _policy_profit_metrics(features, panel, CHAMPION_POLICY)
    preliminary_baseline_rows = build_profit_baseline_rows(features, panel, full_best_policy)
    validation_summary_rows = _profit_candidate_validation_summary_rows(features, panel, candidate_policies)
    candidate_rows = [_public_row(row) for row in full_rows_with_policy]
    gate_rows = build_profit_gate_diagnostics(candidate_rows, champion_metrics, preliminary_baseline_rows, validation_summary_rows)
    best_validated = select_best_validated_formula(candidate_rows, gate_rows, validation_summary_rows)
    best_validated_policy = _policy_by_id(candidate_policies, str(best_validated.get("candidate_id", ""))) if best_validated else None
    if best_validated_policy is None:
        best_validated_policy = CHAMPION_POLICY
        best_validated = _public_row(champion_metrics)
    best_metrics = _policy_profit_metrics(features, panel, best_validated_policy)
    baseline_rows = build_profit_baseline_rows(features, panel, best_validated_policy)

    decision, decision_reason = _profit_decision_v3(best_validated, champion_metrics, walk_rows)
    if not walk_rows:
        notes.append("insufficient_data: no valid walk-forward windows")
    notes.extend(
        [
            f"rows={len(features)}",
            f"walk_forward_windows={len(walk_rows)}",
            "objective=profit_oriented_tradable_beta_exposure",
            "selection=v3_best_validated_formula",
            f"decision_reason={decision_reason}",
            "production_formula_not_applied",
        ]
    )

    best_unconstrained_id = str(full_best.get("candidate_id", "")) if full_best else ""
    best_validated_id = str(best_validated.get("candidate_id", best_validated_policy.candidate_id))
    champion_gate = next((row for row in gate_rows if row["candidate_id"] == CHAMPION_POLICY.candidate_id), {})
    distribution_policies = [CHAMPION_POLICY, TREND_ONLY_POLICY, TREND_BREADTH_POLICY, full_best_policy, best_validated_policy]
    seen: set[str] = set()
    distribution_policies = [policy for policy in distribution_policies if not (policy.candidate_id in seen or seen.add(policy.candidate_id))]
    event_rows = _profit_event_study_rows(labels, distribution_policies, features)
    distribution_rows = _profit_regime_distribution_rows(features, distribution_policies)
    return {
        "decision": decision.value,
        "decision_reason": decision_reason,
        "best_challenger_id": best_validated_id,
        "best_unconstrained_id": best_unconstrained_id,
        "best_validated_id": best_validated_id,
        "best_policy": best_validated_policy,
        "best_validated_policy": best_validated_policy,
        "champion_metrics": _public_row(champion_metrics),
        "best_unconstrained_metrics": _public_row(full_best) if full_best else {},
        "best_challenger_metrics": _public_row(best_metrics),
        "best_validated_metrics": _public_row(best_metrics),
        "champion_gate_diagnostics": champion_gate,
        "candidate_rows": candidate_rows,
        "walk_forward_rows": walk_rows,
        "candidate_validation_summary_rows": validation_summary_rows,
        "candidate_gate_rows": gate_rows,
        "baseline_rows": baseline_rows,
        "regime_exposure_rows": baseline_rows,
        "regime_distribution_rows": distribution_rows,
        "event_rows": event_rows,
        "features": features,
        "labels": labels,
        "asset_panel": panel,
        "asset_sources": dict(panel.attrs.get("asset_sources", {})),
        "notes": notes,
    }


def _recommended_profit_config(result: dict) -> str:
    policy = result.get("best_validated_policy") or result.get("best_policy")
    decision = str(result.get("decision", PromotionGateResult.KEEP_CHAMPION.value))
    lines = [
        f"decision: {decision}",
        f"decision_reason: {result.get('decision_reason', '')}",
        "apply: false",
        "objective: profit_oriented_tradable_beta_exposure",
        f"best_unconstrained_id: {result.get('best_unconstrained_id', '')}",
        f"best_validated_id: {result.get('best_validated_id', '')}",
    ]
    if (
        decision == PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW.value
        and isinstance(policy, RegimePolicy)
        and policy.candidate_id != CHAMPION_POLICY.candidate_id
    ):
        lines.extend(
            [
                "recommended_config:",
                f"  candidate_id: {policy.candidate_id}",
                "  validated: true",
                "  weights:",
            ]
        )
        for key, value in policy.weights.items():
            lines.append(f"    {key}: {value}")
        lines.extend(
            [
                f"  bull_threshold: {policy.bull_threshold}",
                f"  bear_threshold: {policy.bear_threshold}",
                f"  trend_confirm: {policy.trend_confirm}",
                f"  breadth_confirm: {policy.breadth_confirm}",
                f"  bear_trend_breakdown: {policy.bear_trend_breakdown}",
                f"  bear_breadth_breakdown: {policy.bear_breadth_breakdown}",
                f"  smoothing_window: {policy.smoothing_window}",
                f"  min_dwell: {policy.min_dwell}",
            ]
        )
    else:
        lines.append("recommended_config: null")
    return "\n".join(lines) + "\n"


def _profit_markdown(result: dict) -> str:
    champion = result.get("champion_metrics", {})
    validated = result.get("best_validated_metrics") or result.get("best_challenger_metrics", {})
    unconstrained = result.get("best_unconstrained_metrics", {})
    champion_gate = result.get("champion_gate_diagnostics", {})
    lines = [
        "# Market Regime Profit Champion vs Challenger",
        "",
        f"- Decision: `{result.get('decision', PromotionGateResult.KEEP_CHAMPION.value)}`",
        f"- Decision reason: `{result.get('decision_reason', '')}`",
        f"- Best unconstrained: `{result.get('best_unconstrained_id', '')}`",
        f"- Best validated: `{result.get('best_validated_id', '')}`",
        "- Objective: `profit_oriented_tradable_beta_exposure`",
        "- Production formula applied: `false`",
        "",
        "## Metrics",
        (
            f"- Champion: CAGR={float(champion.get('cagr', 0.0)):.2%}, "
            f"Sharpe={float(champion.get('sharpe', 0.0)):.2f}, "
            f"Calmar={float(champion.get('calmar', 0.0)):.2f}, "
            f"MaxDD={float(champion.get('max_drawdown', 0.0)):.2%}"
        ),
        (
            f"- Best unconstrained: CAGR={float(unconstrained.get('cagr', 0.0)):.2%}, "
            f"Sharpe={float(unconstrained.get('sharpe', 0.0)):.2f}, "
            f"Calmar={float(unconstrained.get('calmar', 0.0)):.2f}, "
            f"MaxDD={float(unconstrained.get('max_drawdown', 0.0)):.2%}"
        ),
        (
            f"- Best validated: CAGR={float(validated.get('cagr', 0.0)):.2%}, "
            f"Sharpe={float(validated.get('sharpe', 0.0)):.2f}, "
            f"Calmar={float(validated.get('calmar', 0.0)):.2f}, "
            f"MaxDD={float(validated.get('max_drawdown', 0.0)):.2%}"
        ),
        "",
        "## Champion Gate Diagnostics",
        f"- Passes validation: `{champion_gate.get('passes_validation', '')}`",
        f"- Failed gates: `{champion_gate.get('failed_gates', '')}`",
        f"- Warnings: `{champion_gate.get('warnings', '')}`",
        "",
        "## Baselines",
    ]
    for row in result.get("baseline_rows", []):
        lines.append(
            f"- `{row.get('strategy')}`: CAGR={float(row.get('cagr', 0.0)):.2%}, "
            f"Sharpe={float(row.get('sharpe', 0.0)):.2f}, "
            f"Calmar={float(row.get('calmar', 0.0)):.2f}, "
            f"MaxDD={float(row.get('max_drawdown', 0.0)):.2%}"
        )
    lines.extend(["", "## Notes"])
    for note in result.get("notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def write_regime_profit_report(output_dir: str | Path, result: dict) -> dict:
    """Write the v2 profit-oriented regime research report."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    _csv(output / "candidate_profit_search.csv", result.get("candidate_rows", []))
    _csv(output / "walk_forward_profit_results.csv", result.get("walk_forward_rows", []))
    _csv(output / "baseline_comparison.csv", result.get("baseline_rows", []))
    _csv(output / "regime_exposure_ab_test.csv", result.get("regime_exposure_rows", []))
    _csv(output / "regime_distribution.csv", result.get("regime_distribution_rows", []))
    _csv(output / "candidate_gate_diagnostics.csv", result.get("candidate_gate_rows", []))
    _csv(output / "candidate_validation_summary.csv", result.get("candidate_validation_summary_rows", []))
    _csv(output / "event_study.csv", result.get("event_rows", []))

    asset_panel = result.get("asset_panel")
    features = result.get("features")
    labels = result.get("labels")
    if isinstance(asset_panel, pd.DataFrame):
        asset_panel.to_parquet(output / "tradable_asset_panel.parquet")
    if isinstance(features, pd.DataFrame):
        features.to_parquet(output / "regime_feature_history.parquet")
    if isinstance(labels, pd.DataFrame):
        labels.to_parquet(output / "regime_label_history.parquet")

    (output / "recommended_profit_config.yaml").write_text(_recommended_profit_config(result), encoding="utf-8")
    (output / "profit_champion_vs_challenger.md").write_text(_profit_markdown(result), encoding="utf-8")
    run_log = output / "run.log"
    if not run_log.exists():
        run_log.write_text("market_regime_profit_training_report_written=true\n", encoding="utf-8")

    report_files = [
        "summary.json",
        "profit_champion_vs_challenger.md",
        "tradable_asset_panel.parquet",
        "regime_feature_history.parquet",
        "regime_label_history.parquet",
        "candidate_profit_search.csv",
        "walk_forward_profit_results.csv",
        "baseline_comparison.csv",
        "regime_exposure_ab_test.csv",
        "regime_distribution.csv",
        "candidate_gate_diagnostics.csv",
        "candidate_validation_summary.csv",
        "event_study.csv",
        "recommended_profit_config.yaml",
        "run.log",
    ]
    champion = result.get("champion_metrics", {})
    challenger = result.get("best_challenger_metrics", {})
    summary = {
        "status": "ok",
        "decision": str(result.get("decision", PromotionGateResult.KEEP_CHAMPION.value)),
        "decision_reason": str(result.get("decision_reason", "")),
        "best_challenger_id": str(result.get("best_challenger_id", "")),
        "best_unconstrained_id": str(result.get("best_unconstrained_id", "")),
        "best_validated_id": str(result.get("best_validated_id", "")),
        "champion_metrics": champion,
        "best_challenger_metrics": challenger,
        "best_unconstrained_metrics": result.get("best_unconstrained_metrics", {}),
        "best_validated_metrics": result.get("best_validated_metrics", {}),
        "champion_gate_diagnostics": result.get("champion_gate_diagnostics", {}),
        "oos_walk_forward_windows": len(result.get("walk_forward_rows", [])),
        "asset_sources": result.get("asset_sources", {}),
        "report_files": report_files,
        "notes": list(result.get("notes", [])),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_to_jsonable), encoding="utf-8")
    return summary


def run_and_write_profit_report(
    *,
    index_df: pd.DataFrame,
    asset_panel: pd.DataFrame,
    output_dir: str | Path,
    start: str | None = None,
    end: str | None = None,
    max_candidates: int = 1000,
    breadth_history: pd.DataFrame | None = None,
) -> dict:
    features = build_regime_feature_history(index_df, breadth_history, start=start, end=end)
    policies = generate_candidate_policies(max_candidates=max_candidates)
    result = run_regime_profit_training(features, asset_panel, policies=policies)
    return write_regime_profit_report(output_dir, result)
