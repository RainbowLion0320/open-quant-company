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
    has_evidence = total > missing
    has_promoted = promoted > 0
    has_blocked = blocked > 0

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
            "artifact_gate",
            "Evidence Exists?",
            "Branch missing artifacts before expensive evaluation",
            kind="decision",
            status="warning" if missing else "ok",
            metrics=[
                metric("Present", total - missing, "positive" if has_evidence else "negative"),
                metric("Missing", missing, "negative" if missing else "positive"),
            ],
            inputs=["Strategy list"],
            outputs=["Evidence scan path", "Missing evidence path"],
        ),
        node(
            "scan",
            "Research Scan",
            "Load candidate strategy evaluation artifacts",
            metrics=[metric("With evidence", total - missing)],
            inputs=["Evidence scan path"],
            outputs=["Evidence artifacts"],
        ),
        node(
            "walk_forward",
            "Walk-Forward Split",
            "Separate train/validation periods for robustness",
            metrics=[metric("Mode", "rolling")],
            inputs=["Evidence artifacts"],
            outputs=["Walk-forward folds"],
        ),
        node(
            "tournament",
            "Backtest Tournament",
            "Multi-strategy comparison",
            metrics=[metric("Promoted", promoted, "positive"), metric("Blocked", blocked, "negative")],
            inputs=["Walk-forward folds"],
            outputs=["Tournament results"],
        ),
        node(
            "baseline_compare",
            "Baseline Comparison",
            "vs buy_and_hold, fixed_weight, etc.",
            metrics=[metric("Baselines", 6)],
            inputs=["Tournament results"],
            outputs=["Baseline win rates"],
        ),
        node(
            "oos",
            "OOS & Cost Diagnostics",
            "Out-of-sample validation window",
            metrics=[metric("OOS months", "varies")],
            inputs=["Tournament results"],
            outputs=["OOS metrics"],
        ),
        node(
            "cost_model",
            "Cost Model",
            "Slippage, commission, and turnover drag",
            metrics=[metric("Costs", "slippage + fee")],
            inputs=["Tournament results", "OOS metrics"],
            outputs=["Cost-adjusted returns"],
        ),
        node(
            "promotion_gate",
            "Promotion Gate?",
            "Governance gate evaluation",
            kind="decision",
            metrics=[metric("Ready", promoted, "positive"), metric("Blocked", blocked, "negative")],
            inputs=["Baseline win rates", "OOS metrics", "Cost-adjusted returns"],
            outputs=["Promote path", "Block path", "Review artifact"],
        ),
        node(
            "evidence_export",
            "Evidence Export",
            "Persist promotion decision and diagnostics for Web/API",
            metrics=[
                metric("Promoted", promoted, "positive" if has_promoted else "neutral"),
                metric("Blocked", blocked, "negative" if has_blocked else "neutral"),
            ],
            inputs=["Promotion decision", "Missing evidence path"],
            outputs=["Evidence summary", "Warnings"],
        ),
    ]
    edges = [
        edge("catalog", "artifact_gate"),
        edge("artifact_gate", "scan",
             label="present", condition="exists == true", active=has_evidence),
        edge("artifact_gate", "evidence_export",
             label="missing", condition="exists == false", active=missing > 0),
        edge("scan", "walk_forward"),
        edge("walk_forward", "tournament"),
        edge("tournament", "baseline_compare"),
        edge("tournament", "oos"),
        edge("tournament", "cost_model"),
        edge("oos", "cost_model"),
        edge("baseline_compare", "promotion_gate"),
        edge("oos", "promotion_gate"),
        edge("cost_model", "promotion_gate"),
        edge("promotion_gate", "evidence_export",
             label="promote", condition="promotion_decision == passed", active=has_promoted),
        edge("promotion_gate", "evidence_export",
             label="block", condition="promotion_decision == blocked", active=has_blocked),
    ]
    return {
        "pipeline_key": "strategy_evidence",
        "updated": updated_timestamp(),
        "summary": {"total": total, "promoted": promoted, "blocked": blocked, "missing": missing},
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }
