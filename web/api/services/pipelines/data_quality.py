"""Data Quality pipeline payload builder."""

from __future__ import annotations

from data.storage.dimensions import get_registry
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
    has_stale = stale_count > 0
    has_missing = missing_count > 0
    repair_needed = has_stale or has_missing or not gate_ok

    nodes = [
        node(
            "registry",
            "Registry Dimensions",
            f"{dim_count} enabled dimensions",
            metrics=[metric("Dimensions", dim_count, "accent")],
            inputs=["settings.yaml → data_registry"],
            outputs=["Enabled + disabled dimensions"],
        ),
        node(
            "dimension_filter",
            "Dimension Filter",
            "Keep enabled dimensions for health scanning",
            metrics=[metric("Enabled", dim_count, "accent")],
            inputs=["Enabled + disabled dimensions"],
            outputs=["Enabled dimension list"],
        ),
        node(
            "cache",
            "Cache Discovery",
            "Parquet files on disk",
            metrics=[metric("Status", "ready" if dim_count > 0 else "empty")],
            inputs=["Enabled dimension list"],
            outputs=["Cache paths", "File sizes"],
        ),
        node(
            "schema_probe",
            "Schema Probe",
            "Read date columns and basic file shape",
            metrics=[metric("Probe", "date/schema")],
            inputs=["Cache paths"],
            outputs=["Schema summaries", "Date coverage"],
        ),
        node(
            "manifest",
            "Manifest Audit",
            "Per-dimension freshness timestamps",
            metrics=[metric("Audited", dim_count)],
            inputs=["Schema summaries", "Date coverage"],
            outputs=["Freshness timestamps"],
        ),
        node(
            "freshness_calc",
            "Freshness Calculation",
            "Compare latest timestamp against SLA",
            metrics=[metric("Dimensions", dim_count)],
            inputs=["Freshness timestamps"],
            outputs=["Freshness report"],
        ),
        node(
            "stale_gate",
            "Stale Data?",
            "Branch when data exists but exceeds freshness SLA",
            kind="decision",
            status="warning" if has_stale else "ok",
            metrics=[metric("Stale", stale_count, "negative" if has_stale else "positive")],
            inputs=["Freshness report"],
            outputs=["Stale repair path", "Readiness path"],
        ),
        node(
            "missing_gate",
            "Missing Data?",
            "Branch when an enabled dimension has no cache",
            kind="decision",
            status="warning" if has_missing else "ok",
            metrics=[metric("Missing", missing_count, "negative" if has_missing else "positive")],
            inputs=["Freshness report"],
            outputs=["Missing repair path", "Readiness path"],
        ),
        node(
            "repair_policy",
            "Repair Policy",
            "Classify auto-repair versus manual intervention",
            status="ok" if gate_ok else "warning",
            metrics=[
                metric("Gate", "PASS" if gate_ok else "FAIL", "positive" if gate_ok else "negative"),
                metric("Needed", "yes" if repair_needed else "no", "warning" if repair_needed else "positive"),
            ],
            inputs=["Stale repair path", "Missing repair path"],
            outputs=["Repair plan"],
        ),
        node(
            "repair",
            "Repair Actions",
            "Auto/manual repair dispatch",
            metrics=[metric("Auto-repairable", "per policy")],
            inputs=["Repair plan"],
            outputs=["Repair actions"],
        ),
        node(
            "downstream",
            "Downstream Readiness",
            "Consumer availability",
            metrics=[metric("Ready", "signals, backtest, web")],
            inputs=["Readiness path", "Repair actions"],
            outputs=["Readiness report"],
        ),
    ]
    edges = [
        edge("registry", "dimension_filter"),
        edge("dimension_filter", "cache"),
        edge("cache", "schema_probe"),
        edge("schema_probe", "manifest"),
        edge("manifest", "freshness_calc"),
        edge("freshness_calc", "stale_gate"),
        edge("freshness_calc", "missing_gate"),
        edge("stale_gate", "repair_policy",
             label="yes", condition="stale > 0", active=has_stale),
        edge("stale_gate", "downstream",
             label="no", condition="stale == 0", active=not has_stale),
        edge("missing_gate", "repair_policy",
             label="yes", condition="missing > 0", active=has_missing),
        edge("missing_gate", "downstream",
             label="no", condition="missing == 0", active=not has_missing),
        edge("repair_policy", "repair", active=repair_needed),
        edge("repair", "downstream", active=repair_needed),
    ]
    return {
        "pipeline_key": "data_quality",
        "updated": updated_timestamp(),
        "summary": {"dimensions": dim_count, "gate_ok": gate_ok, "stale_count": stale_count, "missing_count": missing_count},
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }
