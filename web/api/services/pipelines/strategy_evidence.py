"""Strategy Evidence pipeline payload builder."""

from __future__ import annotations

from research.strategy_evaluation import list_evidence_artifacts
from web.api.services.pipelines.common import edge, metric, node, updated_timestamp


def build_strategy_evidence_pipeline() -> dict[str, object]:
    """Build Strategy Evidence pipeline payload."""
    artifacts = list_evidence_artifacts()
    total = len(artifacts)
    promoted = sum(1 for a in artifacts if a.get("promotion_decision") == "passed")
    blocked = sum(1 for a in artifacts if a.get("promotion_decision") == "blocked")
    missing = sum(1 for a in artifacts if not a.get("exists"))

    warnings = []
    if missing > 0:
        warnings.append(f"{missing} strategies have no evidence artifact")

    nodes = [
        node(
            "catalog",
            "Strategy Catalog",
            f"{total} strategies registered",
            metrics=[metric("Total", total, "accent")],
            inputs=["config/settings.yaml → strategies"],
            outputs=["Strategy list"],
        ),
        node(
            "scan",
            "Research Scan",
            "Candidate strategy evaluation",
            metrics=[metric("With evidence", total - missing)],
            inputs=["Strategy list"],
            outputs=["Evidence artifacts"],
        ),
        node(
            "tournament",
            "Backtest Tournament",
            "Multi-strategy comparison",
            metrics=[metric("Promoted", promoted, "positive"), metric("Blocked", blocked, "negative")],
            inputs=["Evidence artifacts"],
            outputs=["Tournament results"],
        ),
        node(
            "baseline",
            "Baseline Comparison",
            "vs buy_and_hold, fixed_weight, etc.",
            metrics=[metric("Baselines", 6)],
            inputs=["Tournament results"],
            outputs=["Baseline win rates"],
        ),
        node(
            "oos",
            "OOS & Cost Diagnostics",
            "Out-of-sample validation + cost model",
            metrics=[metric("OOS months", "varies")],
            inputs=["Tournament results"],
            outputs=["OOS metrics", "Cost-adjusted returns"],
        ),
        node(
            "promotion",
            "Promotion Decision",
            "Governance gate evaluation",
            metrics=[metric("Ready", promoted, "positive"), metric("Blocked", blocked, "negative")],
            inputs=["Baseline win rates", "OOS metrics"],
            outputs=["Promotion decision"],
        ),
    ]
    edges = [
        edge("catalog", "scan"),
        edge("scan", "tournament"),
        edge("tournament", "baseline"),
        edge("tournament", "oos"),
        edge("baseline", "promotion"),
        edge("oos", "promotion"),
    ]
    return {
        "pipeline_key": "strategy_evidence",
        "updated": updated_timestamp(),
        "summary": {"total": total, "promoted": promoted, "blocked": blocked, "missing": missing},
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }
