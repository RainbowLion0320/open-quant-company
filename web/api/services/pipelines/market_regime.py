"""Market Regime pipeline payload builder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.settings import get_section
from cybernetics.orchestrator import QuantOrchestrator
from web.api.serializers import safe_float
from web.api.services.pipelines.common import edge, metric, node, pct, score, updated_timestamp, value


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
    """Build Market Regime calculation pipeline payload."""
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
        "confirmed_regime": value(getattr(snapshot, "regime", "unknown")),
        "raw_regime": value(raw_regime),
        "score": round(safe_float(getattr(snapshot, "regime_score", 0.0), 0.0), 1),
        "engine": engine,
        "detection_method": detection_method,
        "decision_reason": decision_reason,
        "confidence": round(safe_float(getattr(snapshot, "hmm_confidence", 0.0), 0.0), 4),
        "entropy": round(safe_float(getattr(snapshot, "hmm_entropy", 0.0), 0.0), 4),
        "adaptive_params": adaptive_params,
    }

    # Determine which explicit control-flow path was taken.
    is_consensus = decision_reason == "hmm_rule_consensus"
    is_override = decision_reason == "hmm_high_confidence_override"
    is_blend = decision_reason == "hybrid_low_confidence_blend"
    is_hmm_only = decision_reason == "hmm_only"
    is_rule_only = decision_reason == "rule_only"
    is_fallback = decision_reason == "hmm_unavailable_fallback"
    is_hmm_candidate = engine in {"hmm", "hybrid"}
    is_hybrid_path = is_consensus or is_override or is_blend
    hmm_available = bool(regime_probs) and not is_fallback
    override_threshold = safe_float(cfg.get("hmm_confidence_override", 0.80), 0.80)

    # Determine stability state.
    pending_value = stability.get("pending_value")
    dwell_count = stability.get("pending_count", 0)
    min_dwell = stability.get("min_dwell", 3)
    is_confirmed = pending_value is None or pending_value == ""
    is_pending = not is_confirmed and dwell_count < min_dwell

    nodes = [
        node(
            "inputs",
            "Market Inputs",
            "Index OHLCV, breadth, and volume snapshots",
            metrics=[
                metric("Sample", int(safe_float(breadth_detail.get("sample_size"), 0))),
                metric("As of", breadth_detail.get("as_of") or getattr(snapshot, "date", "")),
            ],
            inputs=["A-share index OHLCV", "Full-market breadth", "Full-market volume"],
            outputs=["Raw index frame", "Breadth source", "Volume source"],
        ),
        node(
            "benchmark_frame",
            "Benchmark Frame",
            "Normalize index OHLCV and align latest date",
            metrics=[
                metric("As of", breadth_detail.get("as_of") or getattr(snapshot, "date", "")),
                metric("Indexes", "configured"),
            ],
            inputs=["Raw index frame"],
            outputs=["Benchmark close/volume frame"],
        ),
        node(
            "breadth_snapshot",
            "Breadth Snapshot",
            "Full-market participation and advance ratio",
            metrics=[
                metric("Sample", int(safe_float(breadth_detail.get("sample_size"), 0)), "accent"),
                metric("Advance", pct(breadth_detail.get("advance_ratio"))),
                metric("Above MA20", pct(breadth_detail.get("above_ma20"))),
            ],
            inputs=["Breadth source"],
            outputs=["Breadth snapshot"],
        ),
        node(
            "volume_snapshot",
            "Volume Snapshot",
            "Market amount and up-volume activity",
            metrics=[
                metric("Amount 5/20", pct(score_components.get("amount_ratio_5_20"))),
                metric("Up amount", pct(score_components.get("up_amount_ratio"))),
            ],
            inputs=["Volume source"],
            outputs=["Volume snapshot"],
        ),
        node(
            "trend",
            "Trend Strength",
            "Multi-index MA alignment and momentum",
            metrics=[
                metric("Trend", pct(score_components.get("trend_raw")), "accent"),
                metric("sh000001", pct(score_components.get("trend_sh000001"))),
                metric("sh000300", pct(score_components.get("trend_sh000300"))),
            ],
            inputs=["Benchmark frame", "Index OHLCV"],
            outputs=["Trend raw score"],
        ),
        node(
            "breadth",
            "Market Breadth",
            "Advance ratio, MA20/60/120 participation",
            metrics=[
                metric("Breadth", pct(score_components.get("breadth_raw")), "accent"),
                metric("Advance", pct(breadth_detail.get("advance_ratio"))),
                metric("Above MA20", pct(breadth_detail.get("above_ma20"))),
            ],
            inputs=["Breadth snapshot"],
            outputs=["Breadth raw score"],
        ),
        node(
            "risk",
            "Risk Strength",
            "Drawdown, realized volatility, selling pressure",
            metrics=[
                metric("Risk", pct(score_components.get("risk_raw")), "accent"),
                metric("Drawdown", pct(score_components.get("risk_drawdown_raw"))),
                metric("Volatility", pct(score_components.get("risk_volatility_raw"))),
            ],
            inputs=["Benchmark frame", "Breadth snapshot"],
            outputs=["Risk raw score"],
        ),
        node(
            "volume",
            "Volume Confirmation",
            "Amount ratio, up-volume, index volume activity",
            metrics=[
                metric("Volume", pct(score_components.get("volume_raw")), "accent"),
                metric("Amount 5/20", pct(score_components.get("amount_ratio_5_20"))),
                metric("Up amount", pct(score_components.get("up_amount_ratio"))),
            ],
            inputs=["Volume snapshot"],
            outputs=["Volume raw score"],
        ),
        node(
            "hmm_features",
            "HMM Feature Assembly",
            "8-dimensional observation vector for Student-t HMM",
            metrics=[
                metric("Features", int(safe_float(model_meta.get("n_features"), len(hmm_cfg.get("observation_columns", []))))),
                metric("Window", f"{hmm_cfg.get('feature_window', 252)}d"),
            ],
            inputs=["Benchmark frame", "Breadth snapshot", "Volume snapshot"],
            outputs=["HMM observation vector"],
        ),
        node(
            "rule_score",
            "Rule Score Composition",
            "Weighted sum: 30*trend + 30*breadth + 30*risk + 10*volume",
            metrics=[
                metric("Score", score(getattr(snapshot, "regime_score", 0.0)), "accent"),
                metric("Trend", score_components.get("trend", "—")),
                metric("Breadth", score_components.get("breadth", "—")),
                metric("Risk", score_components.get("risk", "—")),
                metric("Volume", score_components.get("volume", "—")),
            ],
            inputs=["Trend raw", "Breadth raw", "Risk raw", "Volume raw"],
            outputs=[f"Rule raw: {value(raw_regime)}", f"Score: {score(getattr(snapshot, 'regime_score', 0.0))}"],
        ),
        node(
            "hmm_inference",
            "HMM Inference",
            "Student-t HMM forward-backward on 8-dim observation",
            status="ready" if regime_probs else "fallback",
            metrics=[
                metric("Bull", pct(regime_probs.get("bull")), "positive"),
                metric("Sideways", pct(regime_probs.get("sideways")), "warning"),
                metric("Bear", pct(regime_probs.get("bear")), "negative"),
                metric("Samples", int(safe_float(model_meta.get("n_samples"), 0))),
            ],
            inputs=["HMM observation vector", f"Model: {model_path}"],
            outputs=["Regime probability vector", f"Confidence {summary['confidence']:.2f}"],
        ),
        node(
            "engine_route",
            "Engine Route?",
            "Choose rule, HMM, or hybrid decision branch",
            kind="decision",
            metrics=[
                metric("Engine", engine.upper(), "accent"),
                metric("Method", str(detection_method).upper(), "accent"),
            ],
            inputs=["Rule raw regime", "Configured engine"],
            outputs=["Rule branch", "HMM availability check"],
        ),
        node(
            "hmm_availability",
            "HMM Available?",
            "Check model inference and probability vector",
            kind="decision",
            status="ready" if hmm_available else "fallback",
            metrics=[
                metric("Available", "yes" if hmm_available else "no", "positive" if hmm_available else "negative"),
                metric("Confidence", f"{summary['confidence']:.2f}"),
            ],
            inputs=["HMM probability vector", "Configured engine"],
            outputs=["HMM-only branch", "Hybrid branch", "Rule fallback"],
        ),
        node(
            "mode_rule_only",
            "Rule-Only Path",
            "Use weighted rule score when rule engine or fallback wins",
            kind="path",
            status="fallback" if is_fallback else "ready",
            metrics=[
                metric("Reason", "fallback" if is_fallback else "rule_only", "warning" if is_fallback else "accent"),
                metric("Raw", value(raw_regime)),
            ],
            inputs=["Rule score", "Engine route"],
            outputs=["Raw regime candidate"],
        ),
        node(
            "mode_hmm_only",
            "HMM-Only Path",
            "Use HMM argmax when engine is HMM",
            kind="path",
            metrics=[
                metric("Reason", "hmm_only"),
                metric("Raw", summary["raw_regime"], "accent"),
            ],
            inputs=["HMM probability vector"],
            outputs=["Raw regime candidate"],
        ),
        node(
            "hybrid_compare",
            "Rule == HMM?",
            "Hybrid consensus check before confidence override",
            kind="decision",
            metrics=[
                metric("Reason", decision_reason or "rule_only"),
                metric("Consensus", "yes" if is_consensus else "no"),
            ],
            inputs=["Rule raw regime", "HMM raw regime"],
            outputs=["Consensus path", "Disagreement path"],
        ),
        node(
            "path_consensus",
            "Consensus Path",
            "Rule and HMM agree; use HMM probabilities",
            kind="path",
            metrics=[
                metric("Reason", "hmm_rule_consensus"),
                metric("Raw", summary["raw_regime"], "accent"),
            ],
            inputs=["Consensus result"],
            outputs=["Raw regime candidate"],
        ),
        node(
            "confidence_gate",
            "Confidence >= Threshold?",
            "Decide HMM override versus blended rule/HMM vote",
            kind="decision",
            metrics=[
                metric("Confidence", f"{summary['confidence']:.2f}", "accent"),
                metric("Threshold", f"{override_threshold:.2f}"),
            ],
            inputs=["Disagreement result", "HMM confidence"],
            outputs=["Override path", "Blend path"],
        ),
        node(
            "path_override",
            "Override Path",
            "High-confidence HMM overrides rule regime",
            kind="path",
            metrics=[
                metric("Reason", "hmm_high_confidence_override"),
                metric("Raw", summary["raw_regime"], "accent"),
            ],
            inputs=["HMM argmax regime"],
            outputs=["Raw regime candidate"],
        ),
        node(
            "path_blend",
            "Blend Path",
            "Low-confidence disagreement blends HMM probabilities with rule vote",
            kind="path",
            metrics=[
                metric("Reason", "hybrid_low_confidence_blend", "accent"),
                metric("Raw", summary["raw_regime"]),
            ],
            inputs=["Rule vote", "HMM probabilities"],
            outputs=["Raw regime candidate"],
        ),
        node(
            "raw_regime",
            "Raw Regime",
            "Resolved pre-dwell market regime",
            metrics=[
                metric("Raw", summary["raw_regime"], "accent"),
                metric("Reason", decision_reason or "rule_only"),
            ],
            inputs=["Active decision path"],
            outputs=[f"Raw regime: {summary['raw_regime']}"],
        ),
        node(
            "stability",
            "Dwell Gate?",
            "Minimum unique observations before confirmed switch",
            kind="decision",
            metrics=[
                metric("Confirmed", stability.get("confirmed_value", summary["confirmed_regime"]), "accent"),
                metric("Pending", stability.get("pending_value") or "idle"),
                metric("Dwell", f"{stability.get('pending_count', 0)}/{stability.get('min_dwell', 3)}"),
            ],
            inputs=["Raw regime"],
            outputs=["Confirmed branch", "Pending branch"],
        ),
        node(
            "stability_confirmed",
            "Confirmed Path",
            "No pending transition or dwell requirement satisfied",
            kind="path",
            metrics=[metric("Confirmed", summary["confirmed_regime"], "accent")],
            inputs=["Dwell gate"],
            outputs=[f"Confirmed regime: {summary['confirmed_regime']}"],
        ),
        node(
            "stability_pending",
            "Pending Hold",
            "Keep prior confirmed regime until dwell threshold is met",
            kind="path",
            metrics=[
                metric("Pending", stability.get("pending_value") or "idle", "warning"),
                metric("Dwell", f"{dwell_count}/{min_dwell}"),
            ],
            inputs=["Dwell gate"],
            outputs=[f"Confirmed regime: {summary['confirmed_regime']}"],
        ),
        node(
            "outputs",
            "Downstream Outputs",
            "Risk budget and adaptive execution parameters",
            metrics=[
                metric("Position", pct(adaptive_params.get("position_size")), "accent"),
                metric("Max positions", adaptive_params.get("max_positions", "—")),
                metric("Stop loss", pct(adaptive_params.get("stop_loss"))),
            ],
            inputs=["Confirmed regime", "Probability vector"],
            outputs=["Strategy risk overlay", "Asset allocator", "Web telemetry"],
        ),
    ]

    edges = [
        edge("inputs", "benchmark_frame"),
        edge("inputs", "breadth_snapshot"),
        edge("inputs", "volume_snapshot"),
        edge("benchmark_frame", "trend"),
        edge("benchmark_frame", "risk"),
        edge("benchmark_frame", "hmm_features"),
        edge("breadth_snapshot", "breadth"),
        edge("breadth_snapshot", "risk"),
        edge("breadth_snapshot", "hmm_features"),
        edge("volume_snapshot", "volume"),
        edge("volume_snapshot", "hmm_features"),
        edge("trend", "rule_score"),
        edge("breadth", "rule_score"),
        edge("risk", "rule_score"),
        edge("volume", "rule_score"),
        edge("hmm_features", "hmm_inference"),
        edge("rule_score", "engine_route"),
        edge("hmm_inference", "hmm_availability", active=is_hmm_candidate),
        edge("engine_route", "mode_rule_only",
             label="rule only", condition="engine == rule_based", active=is_rule_only),
        edge("engine_route", "hmm_availability",
             label="hmm/hybrid", condition="engine in {hmm, hybrid}", active=is_hmm_candidate),
        edge("hmm_availability", "mode_rule_only",
             label="fallback", condition="HMM unavailable", active=is_fallback),
        edge("hmm_availability", "mode_hmm_only",
             label="hmm only", condition="engine == HMM", active=is_hmm_only),
        edge("hmm_availability", "hybrid_compare",
             label="hybrid", condition="engine == hybrid", active=is_hybrid_path),
        edge("hybrid_compare", "path_consensus",
             label="yes", condition="rule == HMM", active=is_consensus),
        edge("hybrid_compare", "confidence_gate",
             label="no", condition="rule != HMM", active=is_override or is_blend),
        edge("confidence_gate", "path_override",
             label="override", condition=f"confidence >= {override_threshold:.2f}", active=is_override),
        edge("confidence_gate", "path_blend",
             label="blend", condition=f"confidence < {override_threshold:.2f}", active=is_blend),
        edge("mode_rule_only", "raw_regime",
             label="rule raw", active=is_rule_only or is_fallback),
        edge("mode_hmm_only", "raw_regime",
             label="hmm raw", active=is_hmm_only),
        edge("path_consensus", "raw_regime",
             label="consensus", active=is_consensus),
        edge("path_override", "raw_regime",
             label="override", active=is_override),
        edge("path_blend", "raw_regime",
             label="blend", active=is_blend),
        edge("raw_regime", "stability"),
        edge("stability", "stability_confirmed",
             label="confirmed", condition="dwell ≥ min_dwell", active=is_confirmed),
        edge("stability", "stability_pending",
             label="pending", condition=f"dwell {dwell_count}/{min_dwell}", active=is_pending),
        edge("stability_confirmed", "outputs", active=is_confirmed),
        edge("stability_pending", "outputs", active=is_pending),
    ]

    return {
        "pipeline_key": "market_regime",
        "updated": updated_timestamp(),
        "summary": summary,
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }
