"""Data Quality pipeline payload builder."""

from __future__ import annotations

from data.data_registry import get_registry
from web.api.services.pipelines.common import edge, metric, node, updated_timestamp
from web.api.services.system_data_health import freshness_gate_from_health_check


def build_data_quality_pipeline() -> dict[str, object]:
    """Build Data Quality pipeline payload."""
    reg = get_registry()
    dims = reg.get_enabled() if hasattr(reg, "get_enabled") else []
    dim_count = len(dims) if dims else 0

    gate_ok = True
    stale_count = 0
    missing_count = 0
    try:
        gate, _rows = freshness_gate_from_health_check()
        gate_ok = gate.get("ok", True)
        stale_count = len(gate.get("stale", []))
        missing_count = len(gate.get("missing", []))
    except Exception:
        pass

    warnings = []
    if stale_count > 0:
        warnings.append(f"{stale_count} dimensions have stale data")
    if missing_count > 0:
        warnings.append(f"{missing_count} dimensions are missing")
    if dim_count == 0:
        warnings.append("No enabled dimensions found in registry")

    nodes = [
        node(
            "registry",
            "Registry Dimensions",
            f"{dim_count} enabled dimensions",
            metrics=[metric("Dimensions", dim_count, "accent")],
            inputs=["settings.yaml → data_registry"],
            outputs=["Dimension list"],
        ),
        node(
            "cache",
            "Cache Discovery",
            "Parquet files on disk",
            metrics=[metric("Status", "ready" if dim_count > 0 else "empty")],
            inputs=["Dimension list"],
            outputs=["Cache paths", "File sizes"],
        ),
        node(
            "manifest",
            "Manifest Audit",
            "Per-dimension freshness timestamps",
            metrics=[metric("Audited", dim_count)],
            inputs=["Cache paths"],
            outputs=["Freshness timestamps"],
        ),
        node(
            "freshness",
            "Freshness Gate",
            "Stale/missing detection",
            status="ok" if gate_ok else "warning",
            metrics=[
                metric("Gate", "PASS" if gate_ok else "FAIL", "positive" if gate_ok else "negative"),
                metric("Stale", stale_count, "negative" if stale_count > 0 else "neutral"),
                metric("Missing", missing_count, "negative" if missing_count > 0 else "neutral"),
            ],
            inputs=["Freshness timestamps"],
            outputs=["Gate result"],
        ),
        node(
            "repair",
            "Repair Actions",
            "Auto/manual repair dispatch",
            metrics=[metric("Auto-repairable", "per policy")],
            inputs=["Gate result"],
            outputs=["Repair actions"],
        ),
        node(
            "downstream",
            "Downstream Readiness",
            "Consumer availability",
            metrics=[metric("Ready", "signals, backtest, web")],
            inputs=["Gate result", "Repair actions"],
            outputs=["Readiness report"],
        ),
    ]
    edges = [
        edge("registry", "cache"),
        edge("cache", "manifest"),
        edge("manifest", "freshness"),
        edge("freshness", "repair"),
        edge("freshness", "downstream"),
        edge("repair", "downstream"),
    ]
    return {
        "pipeline_key": "data_quality",
        "updated": updated_timestamp(),
        "summary": {"dimensions": dim_count, "gate_ok": gate_ok, "stale_count": stale_count, "missing_count": missing_count},
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }
