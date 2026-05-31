"""Pipeline transparency payload builders."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.settings import get_section
from cybernetics.orchestrator import QuantOrchestrator
from web.api.serializers import safe_float


def _value(regime: object) -> str:
    return regime.value if hasattr(regime, "value") else str(regime or "unknown")


def _metric(label: str, value: object, tone: str = "neutral") -> dict[str, object]:
    return {"label": label, "value": value, "tone": tone}


def _node(
    node_id: str,
    title: str,
    subtitle: str,
    *,
    status: str = "ready",
    metrics: list[dict[str, object]] | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "title": title,
        "subtitle": subtitle,
        "status": status,
        "metrics": metrics or [],
        "inputs": inputs or [],
        "outputs": outputs or [],
    }


def _edge(source: str, target: str, label: str = "") -> dict[str, str]:
    return {"source": source, "target": target, "label": label}


def _pct(value: object) -> str:
    return f"{safe_float(value, 0.0) * 100:.1f}%"


def _score(value: object) -> str:
    return f"{safe_float(value, 0.0):.1f}"


def _resolve_model_path(model_path: object) -> Path:
    path = Path(str(model_path or "data/models/regime_hmm"))
    return path if path.is_absolute() else Path.cwd() / path


def _read_model_meta(model_path: Path) -> dict[str, Any]:
    meta_path = model_path / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_market_regime_pipeline() -> dict[str, object]:
    """Build Market Regime calculation pipeline payload.

    This reuses the production orchestrator snapshot and only formats the
    intermediate values already produced by the regime engine.
    """
    cfg = get_section("cybernetics", {}) or {}
    hmm_cfg = cfg.get("hmm", {}) or {}
    engine = str(cfg.get("regime_engine", "rule_based"))
    model_path = _resolve_model_path(hmm_cfg.get("model_path", "data/models/regime_hmm"))
    model_meta = _read_model_meta(model_path)

    orchestrator = QuantOrchestrator()
    snapshot = orchestrator.detect()

    raw_regime = getattr(snapshot, "raw_regime", getattr(snapshot, "regime", "unknown"))
    score_components = getattr(snapshot, "score_components", {}) or {}
    breadth_detail = getattr(snapshot, "breadth_detail", {}) or {}
    stability = getattr(snapshot, "regime_state", {}) or {}
    regime_probs = getattr(snapshot, "regime_probs", {}) or {}
    detection_method = getattr(snapshot, "detection_method", "rule_based")
    decision_reason = getattr(snapshot, "decision_reason", "")
    adaptive_params = dict(getattr(orchestrator, "params", {}) or {})

    warnings: list[str] = []
    if engine in {"hmm", "hybrid"} and not (model_path / "params.npz").exists():
        warnings.append(f"HMM model missing at {model_path}")
    if engine in {"hmm", "hybrid"} and detection_method == "rule_based":
        warnings.append("HMM inference fell back to rule-based regime detection")
    if safe_float(breadth_detail.get("sample_size"), 0) < 1000:
        warnings.append("Market breadth sample size is below production threshold")
    if engine in {"hmm", "hybrid"} and not model_meta:
        warnings.append("HMM meta.json is unavailable or unreadable")

    summary = {
        "confirmed_regime": _value(getattr(snapshot, "regime", "unknown")),
        "raw_regime": _value(raw_regime),
        "score": round(safe_float(getattr(snapshot, "regime_score", 0.0), 0.0), 1),
        "engine": engine,
        "detection_method": detection_method,
        "decision_reason": decision_reason,
        "confidence": round(safe_float(getattr(snapshot, "hmm_confidence", 0.0), 0.0), 4),
        "entropy": round(safe_float(getattr(snapshot, "hmm_entropy", 0.0), 0.0), 4),
        "adaptive_params": adaptive_params,
    }

    nodes = [
        _node(
            "inputs",
            "Market Inputs",
            "Index OHLCV, breadth, and volume snapshots",
            metrics=[
                _metric("Sample", int(safe_float(breadth_detail.get("sample_size"), 0))),
                _metric("As of", breadth_detail.get("as_of") or getattr(snapshot, "date", "")),
            ],
            inputs=["A-share index OHLCV", "Full-market breadth", "Full-market volume"],
            outputs=["Benchmark frame", "Breadth snapshot", "Volume snapshot"],
        ),
        _node(
            "features",
            "Feature Assembly",
            "Shared features for rule score and HMM observation",
            metrics=[
                _metric("Above MA20", _pct(breadth_detail.get("above_ma20"))),
                _metric("HMM features", int(safe_float(model_meta.get("n_features"), len(hmm_cfg.get("observation_columns", []))))),
            ],
            inputs=["Benchmark frame", "Breadth snapshot", "Volume snapshot"],
            outputs=["Rule components", "HMM observation vector"],
        ),
        _node(
            "rule_score",
            "Rule Score",
            "Explainable production score components",
            metrics=[
                _metric("Score", _score(getattr(snapshot, "regime_score", 0.0)), "accent"),
                _metric("Trend", _pct(score_components.get("trend_raw"))),
                _metric("Breadth", _pct(score_components.get("breadth_raw"))),
                _metric("Risk", _pct(score_components.get("risk_raw"))),
                _metric("Volume", _pct(score_components.get("volume_raw"))),
            ],
            inputs=["Rule components"],
            outputs=[f"Rule raw: {_value(raw_regime)}", "Score components"],
        ),
        _node(
            "hmm_inference",
            "HMM Inference",
            "Student-t HMM state probabilities",
            status="ready" if regime_probs else "fallback",
            metrics=[
                _metric("Bull", _pct(regime_probs.get("bull")), "positive"),
                _metric("Sideways", _pct(regime_probs.get("sideways")), "warning"),
                _metric("Bear", _pct(regime_probs.get("bear")), "negative"),
                _metric("Samples", int(safe_float(model_meta.get("n_samples"), 0))),
            ],
            inputs=["HMM observation vector", f"Model: {model_path}"],
            outputs=["Regime probability vector", f"Confidence {summary['confidence']:.2f}"],
        ),
        _node(
            "hybrid_decision",
            "Hybrid Decision",
            "Consensus, high-confidence override, or blended vote",
            metrics=[
                _metric("Engine", engine.upper(), "accent"),
                _metric("Method", str(detection_method).upper(), "accent"),
                _metric("Reason", decision_reason or "rule_only"),
            ],
            inputs=["Rule raw regime", "HMM probabilities"],
            outputs=[f"Raw regime: {summary['raw_regime']}"],
        ),
        _node(
            "stability",
            "Dwell Stability",
            "Minimum unique observations before confirmed switch",
            metrics=[
                _metric("Confirmed", stability.get("confirmed_value", summary["confirmed_regime"]), "accent"),
                _metric("Pending", stability.get("pending_value") or "idle"),
                _metric("Dwell", f"{stability.get('pending_count', 0)}/{stability.get('min_dwell', 3)}"),
            ],
            inputs=["Raw regime"],
            outputs=[f"Confirmed regime: {summary['confirmed_regime']}"],
        ),
        _node(
            "outputs",
            "Downstream Outputs",
            "Risk budget and adaptive execution parameters",
            metrics=[
                _metric("Position", _pct(adaptive_params.get("position_size")), "accent"),
                _metric("Max positions", adaptive_params.get("max_positions", "—")),
                _metric("Stop loss", _pct(adaptive_params.get("stop_loss"))),
            ],
            inputs=["Confirmed regime", "Probability vector"],
            outputs=["Strategy risk overlay", "Asset allocator", "Web telemetry"],
        ),
    ]
    edges = [
        _edge("inputs", "features"),
        _edge("features", "rule_score"),
        _edge("features", "hmm_inference"),
        _edge("rule_score", "hybrid_decision"),
        _edge("hmm_inference", "hybrid_decision"),
        _edge("hybrid_decision", "stability"),
        _edge("stability", "outputs"),
    ]

    return {
        "pipeline_key": "market_regime",
        "updated": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }


def build_data_quality_pipeline() -> dict[str, object]:
    """Build Data Quality pipeline payload."""
    from data.data_registry import get_registry
    from web.api.services.system_data_health import freshness_gate_from_health_check

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
        _node("registry", "Registry Dimensions", f"{dim_count} enabled dimensions",
              metrics=[_metric("Dimensions", dim_count, "accent")],
              inputs=["settings.yaml → data_registry"],
              outputs=["Dimension list"]),
        _node("cache", "Cache Discovery", "Parquet files on disk",
              metrics=[_metric("Status", "ready" if dim_count > 0 else "empty")],
              inputs=["Dimension list"],
              outputs=["Cache paths", "File sizes"]),
        _node("manifest", "Manifest Audit", "Per-dimension freshness timestamps",
              metrics=[_metric("Audited", dim_count)],
              inputs=["Cache paths"],
              outputs=["Freshness timestamps"]),
        _node("freshness", "Freshness Gate", "Stale/missing detection",
              status="ok" if gate_ok else "warning",
              metrics=[_metric("Gate", "PASS" if gate_ok else "FAIL", "positive" if gate_ok else "negative"),
                       _metric("Stale", stale_count, "negative" if stale_count > 0 else "neutral"),
                       _metric("Missing", missing_count, "negative" if missing_count > 0 else "neutral")],
              inputs=["Freshness timestamps"],
              outputs=["Gate result"]),
        _node("repair", "Repair Actions", "Auto/manual repair dispatch",
              metrics=[_metric("Auto-repairable", "per policy")],
              inputs=["Gate result"],
              outputs=["Repair actions"]),
        _node("downstream", "Downstream Readiness", "Consumer availability",
              metrics=[_metric("Ready", "signals, backtest, web")],
              inputs=["Gate result", "Repair actions"],
              outputs=["Readiness report"]),
    ]
    edges = [
        _edge("registry", "cache"),
        _edge("cache", "manifest"),
        _edge("manifest", "freshness"),
        _edge("freshness", "repair"),
        _edge("freshness", "downstream"),
        _edge("repair", "downstream"),
    ]
    return {
        "pipeline_key": "data_quality",
        "updated": datetime.now().isoformat(timespec="seconds"),
        "summary": {"dimensions": dim_count, "gate_ok": gate_ok, "stale_count": stale_count, "missing_count": missing_count},
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }


def build_strategy_evidence_pipeline() -> dict[str, object]:
    """Build Strategy Evidence pipeline payload."""
    from research.strategy_evaluation import list_evidence_artifacts

    artifacts = list_evidence_artifacts()
    total = len(artifacts)
    promoted = sum(1 for a in artifacts if a.get("promotion_decision") == "passed")
    blocked = sum(1 for a in artifacts if a.get("promotion_decision") == "blocked")
    missing = sum(1 for a in artifacts if not a.get("exists"))

    warnings = []
    if missing > 0:
        warnings.append(f"{missing} strategies have no evidence artifact")

    nodes = [
        _node("catalog", "Strategy Catalog", f"{total} strategies registered",
              metrics=[_metric("Total", total, "accent")],
              inputs=["config/settings.yaml → strategies"],
              outputs=["Strategy list"]),
        _node("scan", "Research Scan", "Candidate strategy evaluation",
              metrics=[_metric("With evidence", total - missing)],
              inputs=["Strategy list"],
              outputs=["Evidence artifacts"]),
        _node("tournament", "Backtest Tournament", "Multi-strategy comparison",
              metrics=[_metric("Promoted", promoted, "positive"),
                       _metric("Blocked", blocked, "negative")],
              inputs=["Evidence artifacts"],
              outputs=["Tournament results"]),
        _node("baseline", "Baseline Comparison", "vs buy_and_hold, fixed_weight, etc.",
              metrics=[_metric("Baselines", 6)],
              inputs=["Tournament results"],
              outputs=["Baseline win rates"]),
        _node("oos", "OOS & Cost Diagnostics", "Out-of-sample validation + cost model",
              metrics=[_metric("OOS months", "varies")],
              inputs=["Tournament results"],
              outputs=["OOS metrics", "Cost-adjusted returns"]),
        _node("promotion", "Promotion Decision", "Governance gate evaluation",
              metrics=[_metric("Ready", promoted, "positive"),
                       _metric("Blocked", blocked, "negative")],
              inputs=["Baseline win rates", "OOS metrics"],
              outputs=["Promotion decision"]),
    ]
    edges = [
        _edge("catalog", "scan"),
        _edge("scan", "tournament"),
        _edge("tournament", "baseline"),
        _edge("tournament", "oos"),
        _edge("baseline", "promotion"),
        _edge("oos", "promotion"),
    ]
    return {
        "pipeline_key": "strategy_evidence",
        "updated": datetime.now().isoformat(timespec="seconds"),
        "summary": {"total": total, "promoted": promoted, "blocked": blocked, "missing": missing},
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }


def build_portfolio_execution_pipeline() -> dict[str, object]:
    """Build Portfolio Execution pipeline payload."""
    warnings = []

    nodes = [
        _node("signals", "Signals", "Strategy signal aggregation",
              metrics=[_metric("Source", "compute_signals.py")],
              inputs=["Strategy signals"],
              outputs=["Buy/sell signals"]),
        _node("regime", "Regime Overlay", "Market regime risk adjustment",
              metrics=[_metric("Source", "orchestrator.detect()")],
              inputs=["Buy/sell signals", "Market regime"],
              outputs=["Risk-adjusted signals"]),
        _node("allocation", "Asset Allocation", "Multi-asset weight distribution",
              metrics=[_metric("Assets", "stock, ETF, bond, futures")],
              inputs=["Risk-adjusted signals"],
              outputs=["Target weights"]),
        _node("risk", "Risk Checks", "Position limits, concentration, drawdown",
              metrics=[_metric("Checks", "single-name cap, total exposure, stop-loss")],
              inputs=["Target weights"],
              outputs=["Approved orders", "Risk rejections"]),
        _node("paper", "Paper Order Simulation", "Simulated execution with costs",
              metrics=[_metric("Mode", "paper")],
              inputs=["Approved orders"],
              outputs=["Filled orders", "Cash impact"]),
        _node("persist", "Persistence & Audit", "Ledger + run record",
              metrics=[_metric("Store", "data/store/ledger/")],
              inputs=["Filled orders", "Cash impact"],
              outputs=["Run ledger", "Audit trail"]),
    ]
    edges = [
        _edge("signals", "regime"),
        _edge("regime", "allocation"),
        _edge("allocation", "risk"),
        _edge("risk", "paper"),
        _edge("paper", "persist"),
    ]
    return {
        "pipeline_key": "portfolio_execution",
        "updated": datetime.now().isoformat(timespec="seconds"),
        "summary": {"mode": "paper"},
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }


PIPELINE_REGISTRY = {
    "market_regime": {"label": "Market Regime", "builder": build_market_regime_pipeline},
    "data_quality": {"label": "Data Quality", "builder": build_data_quality_pipeline},
    "strategy_evidence": {"label": "Strategy Evidence", "builder": build_strategy_evidence_pipeline},
    "portfolio_execution": {"label": "Portfolio Execution", "builder": build_portfolio_execution_pipeline},
}


def list_pipelines() -> list[dict]:
    """Return the list of available pipelines."""
    return [{"key": k, "label": v["label"], "status": "available"} for k, v in PIPELINE_REGISTRY.items()]


def build_pipeline(key: str) -> dict[str, object] | None:
    """Build a pipeline by key."""
    entry = PIPELINE_REGISTRY.get(key)
    if not entry:
        return None
    return entry["builder"]()
