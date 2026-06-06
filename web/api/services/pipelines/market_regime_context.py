"""Context builder for Market Regime pipeline payloads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from web.api.serializers import safe_float
from web.api.services.pipelines.common import value
from web.api.services.pipelines.market_regime_config import (
    DEFAULT_BREADTH_WEIGHTS,
    DEFAULT_DETECTION,
    DEFAULT_RISK_WEIGHTS,
    DEFAULT_SCORE_WEIGHTS,
    configured_numbers,
    read_model_meta,
    resolve_model_path,
)


@dataclass(frozen=True)
class MarketRegimePipelineContext:
    cfg: dict[str, Any]
    hmm_cfg: dict[str, Any]
    score_weights: dict[str, float]
    breadth_weights: dict[str, float]
    risk_weights: dict[str, float]
    detection: dict[str, float]
    engine: str
    model_path: Path
    model_meta: dict[str, Any]
    snapshot: Any
    raw_regime: Any
    score_components: dict[str, Any]
    breadth_detail: dict[str, Any]
    stability: dict[str, Any]
    regime_probs: dict[str, Any]
    detection_method: str
    decision_reason: str
    adaptive_params: dict[str, Any]
    warnings: list[str]
    summary: dict[str, Any]
    is_consensus: bool
    is_override: bool
    is_blend: bool
    is_hmm_only: bool
    is_rule_only: bool
    is_fallback: bool
    is_hmm_candidate: bool
    is_hybrid_path: bool
    hmm_available: bool
    override_threshold: float
    blend_rule_weight: float
    blend_hmm_weight: float
    dwell_count: Any
    min_dwell: Any
    is_confirmed: bool
    is_pending: bool


def build_market_regime_context(
    get_section_fn: Callable[[str, object], object],
    orchestrator_cls: type,
) -> MarketRegimePipelineContext:
    cfg = get_section_fn("cybernetics", {}) or {}
    hmm_cfg = cfg.get("hmm", {}) or {}
    detection_cfg = ((cfg.get("adaptive", {}) or {}).get("detection", {}) or {})
    score_weights = configured_numbers(cfg.get("score_weights"), DEFAULT_SCORE_WEIGHTS)
    breadth_weights = configured_numbers(cfg.get("breadth_weights"), DEFAULT_BREADTH_WEIGHTS)
    risk_weights = configured_numbers(cfg.get("risk_strength_weights"), DEFAULT_RISK_WEIGHTS)
    detection = configured_numbers(detection_cfg, DEFAULT_DETECTION)
    engine = str(cfg.get("regime_engine", "rule_based"))
    model_path = resolve_model_path(hmm_cfg.get("model_path", "data/reference/models/regime_hmm"))
    model_meta = read_model_meta(model_path)

    orchestrator = orchestrator_cls()
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
    blend_rule_weight = min(0.50, max(0.20, 1.0 - summary["confidence"]))
    blend_hmm_weight = 1.0 - blend_rule_weight

    pending_value = stability.get("pending_value")
    dwell_count = stability.get("pending_count", 0)
    min_dwell = stability.get("min_dwell", 3)
    is_confirmed = pending_value is None or pending_value == ""
    is_pending = not is_confirmed and dwell_count < min_dwell

    return MarketRegimePipelineContext(
        cfg=cfg,
        hmm_cfg=hmm_cfg,
        score_weights=score_weights,
        breadth_weights=breadth_weights,
        risk_weights=risk_weights,
        detection=detection,
        engine=engine,
        model_path=model_path,
        model_meta=model_meta,
        snapshot=snapshot,
        raw_regime=raw_regime,
        score_components=score_components,
        breadth_detail=breadth_detail,
        stability=stability,
        regime_probs=regime_probs,
        detection_method=detection_method,
        decision_reason=decision_reason,
        adaptive_params=adaptive_params,
        warnings=warnings,
        summary=summary,
        is_consensus=is_consensus,
        is_override=is_override,
        is_blend=is_blend,
        is_hmm_only=is_hmm_only,
        is_rule_only=is_rule_only,
        is_fallback=is_fallback,
        is_hmm_candidate=is_hmm_candidate,
        is_hybrid_path=is_hybrid_path,
        hmm_available=hmm_available,
        override_threshold=override_threshold,
        blend_rule_weight=blend_rule_weight,
        blend_hmm_weight=blend_hmm_weight,
        dwell_count=dwell_count,
        min_dwell=min_dwell,
        is_confirmed=is_confirmed,
        is_pending=is_pending,
    )
