"""Report writers for champion/challenger regime research."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from research.regime.evaluation import run_regime_research
from research.regime.features import build_regime_feature_history, normalize_ohlcv
from research.regime.policies import generate_candidate_policies
from research.regime_types import PromotionGateResult, RegimePolicy

def _csv(path: Path, rows: Sequence[dict]) -> None:
    pd.DataFrame(list(rows)).to_csv(path, index=False)


def _to_jsonable(value):
    if isinstance(value, RegimePolicy):
        return asdict(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _recommended_config(policy: RegimePolicy | None) -> str:
    if policy is None:
        return "decision: keep_champion\nrecommended_config: null\n"
    weights = "\n".join(f"    {key}: {value}" for key, value in policy.weights.items())
    return (
        "decision: recommend_challenger_for_review\n"
        "recommended_config:\n"
        f"  candidate_id: {policy.candidate_id}\n"
        "  weights:\n"
        f"{weights}\n"
        f"  bull_threshold: {policy.bull_threshold}\n"
        f"  bear_threshold: {policy.bear_threshold}\n"
        f"  trend_confirm: {policy.trend_confirm}\n"
        f"  breadth_confirm: {policy.breadth_confirm}\n"
        f"  bear_trend_breakdown: {policy.bear_trend_breakdown}\n"
        f"  bear_breadth_breakdown: {policy.bear_breadth_breakdown}\n"
        f"  smoothing_window: {policy.smoothing_window}\n"
        f"  min_dwell: {policy.min_dwell}\n"
        "  apply: false\n"
    )


def write_regime_training_report(output_dir: str | Path, result: dict) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    candidate_rows = result.get("candidate_rows", [])
    walk_rows = result.get("walk_forward_rows", [])
    strategy_rows = result.get("strategy_rows", [])
    stability_rows = result.get("stability_rows", [])
    component_rows = result.get("component_rows", [])
    event_rows = result.get("event_rows", [])

    _csv(output / "candidate_search.csv", candidate_rows)
    _csv(output / "walk_forward_results.csv", walk_rows)
    _csv(output / "strategy_ab_test.csv", strategy_rows)
    _csv(output / "stability_stats.csv", stability_rows)
    _csv(output / "component_ablation.csv", component_rows)
    _csv(output / "event_study.csv", event_rows)

    features = result.get("features")
    labels = result.get("labels")
    if isinstance(features, pd.DataFrame) and not features.empty:
        features.to_parquet(output / "regime_feature_history.parquet")
    if isinstance(labels, pd.DataFrame) and not labels.empty:
        labels.to_parquet(output / "regime_label_history.parquet")

    best_policy = result.get("best_policy")
    if result.get("decision") == PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW.value and isinstance(best_policy, RegimePolicy):
        recommended = _recommended_config(best_policy)
    else:
        recommended = _recommended_config(None)
    (output / "recommended_config.yaml").write_text(recommended, encoding="utf-8")

    markdown = _champion_markdown(result)
    (output / "champion_vs_challenger.md").write_text(markdown, encoding="utf-8")

    report_files = [
        "summary.json",
        "champion_vs_challenger.md",
        "candidate_search.csv",
        "walk_forward_results.csv",
        "component_ablation.csv",
        "strategy_ab_test.csv",
        "stability_stats.csv",
        "event_study.csv",
        "recommended_config.yaml",
    ]
    if (output / "regime_feature_history.parquet").exists():
        report_files.append("regime_feature_history.parquet")
    if (output / "regime_label_history.parquet").exists():
        report_files.append("regime_label_history.parquet")

    summary = {
        "status": "ok",
        "decision": str(result.get("decision", PromotionGateResult.KEEP_CHAMPION.value)),
        "champion_score": float(result.get("champion_score", 0.0)),
        "best_challenger_score": float(result.get("best_challenger_score", 0.0)),
        "best_challenger_id": str(result.get("best_challenger_id", "")),
        "report_files": report_files,
        "notes": list(result.get("notes", [])),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_to_jsonable), encoding="utf-8")
    return summary


def _champion_markdown(result: dict) -> str:
    decision = result.get("decision", PromotionGateResult.KEEP_CHAMPION.value)
    lines = [
        "# Market Regime Champion vs Challenger",
        "",
        f"- Decision: `{decision}`",
        f"- Champion score: `{float(result.get('champion_score', 0.0)):.4f}`",
        f"- Best challenger: `{result.get('best_challenger_id', '')}`",
        f"- Best challenger score: `{float(result.get('best_challenger_score', 0.0)):.4f}`",
        "- Production formula applied: `false`",
        "",
        "## Notes",
    ]
    for note in result.get("notes", []):
        lines.append(f"- {note}")
    lines.extend(["", "## Strategy A/B"])
    for row in result.get("strategy_rows", []):
        lines.append(
            f"- `{row.get('strategy')}`: Sharpe={float(row.get('sharpe', 0.0)):.2f}, "
            f"MaxDD={float(row.get('max_drawdown', 0.0)):.2%}, "
            f"Calmar={float(row.get('calmar', 0.0)):.2f}, "
            f"TurnoverProxy={float(row.get('turnover_proxy', 0.0)):.2f}"
        )
    return "\n".join(lines) + "\n"


def run_and_write_report(
    *,
    index_df: pd.DataFrame,
    output_dir: str | Path,
    start: str | None = None,
    end: str | None = None,
    max_candidates: int = 500,
    breadth_history: pd.DataFrame | None = None,
) -> dict:
    features = build_regime_feature_history(index_df, breadth_history, start=start, end=end)
    close = normalize_ohlcv(index_df)["close"]
    if start:
        close = close[close.index >= pd.Timestamp(start)]
    if end and end != "auto":
        close = close[close.index <= pd.Timestamp(end)]
    policies = generate_candidate_policies(max_candidates=max_candidates)
    result = run_regime_research(features, close, policies=policies)
    return write_regime_training_report(output_dir, result)
