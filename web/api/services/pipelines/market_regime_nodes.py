"""Node builders for the Market Regime pipeline graph."""

from __future__ import annotations

from web.api.serializers import safe_float
from web.api.services.pipelines.common import metric, node, pct, score, value
from web.api.services.pipelines.market_regime_config import (
    component_with_weight,
    fmt_percent_points,
    fmt_ratio,
    fmt_scalar,
)
from web.api.services.pipelines.market_regime_context import MarketRegimePipelineContext


def build_market_regime_nodes(ctx: MarketRegimePipelineContext) -> list[dict[str, object]]:
    snapshot = ctx.snapshot
    score_components = ctx.score_components
    breadth_detail = ctx.breadth_detail
    summary = ctx.summary
    stability = ctx.stability
    adaptive_params = ctx.adaptive_params
    detection = ctx.detection
    breadth_weights = ctx.breadth_weights
    risk_weights = ctx.risk_weights
    score_weights = ctx.score_weights
    regime_probs = ctx.regime_probs
    model_meta = ctx.model_meta
    hmm_cfg = ctx.hmm_cfg

    return [
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
                metric("Adv W", fmt_percent_points(breadth_weights["advance_ratio"] * 100)),
                metric("MA20 W", fmt_percent_points(breadth_weights["above_ma20"] * 100)),
                metric("MA60 W", fmt_percent_points(breadth_weights["above_ma60"] * 100)),
                metric("MA120 W", fmt_percent_points(breadth_weights["above_ma120"] * 100)),
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
                metric("Adv W", fmt_percent_points(breadth_weights["advance_ratio"] * 100)),
                metric("MA20 W", fmt_percent_points(breadth_weights["above_ma20"] * 100)),
                metric("MA60 W", fmt_percent_points(breadth_weights["above_ma60"] * 100)),
                metric("MA120 W", fmt_percent_points(breadth_weights["above_ma120"] * 100)),
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
                metric("DD W", fmt_percent_points(risk_weights["drawdown"] * 100)),
                metric("Vol W", fmt_percent_points(risk_weights["volatility"] * 100)),
                metric("Pressure W", fmt_percent_points(risk_weights["pressure"] * 100)),
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
                metric("Expand", f"> {fmt_ratio(detection['volume_expansion'])}"),
                metric("Contract", f"< {fmt_ratio(detection['volume_contraction'])}"),
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
            (
                f"Weighted sum: trend {score_weights['trend']:.0f}% + breadth {score_weights['breadth']:.0f}% "
                f"+ risk {score_weights['risk']:.0f}% + volume {score_weights['volume']:.0f}%"
            ),
            metrics=[
                metric("Score", score(getattr(snapshot, "regime_score", 0.0)), "accent"),
                metric("Trend", component_with_weight(score_components.get("trend"), score_weights["trend"])),
                metric("Breadth", component_with_weight(score_components.get("breadth"), score_weights["breadth"])),
                metric("Risk", component_with_weight(score_components.get("risk"), score_weights["risk"])),
                metric("Volume", component_with_weight(score_components.get("volume"), score_weights["volume"])),
                metric("Bull gate", f"≥ {fmt_scalar(detection['regime_bull_threshold'])}"),
                metric("Bear gate", f"≤ {fmt_scalar(detection['regime_bear_threshold'])}"),
            ],
            inputs=["Trend raw", "Breadth raw", "Risk raw", "Volume raw"],
            outputs=[f"Rule raw: {value(ctx.raw_regime)}", f"Score: {score(getattr(snapshot, 'regime_score', 0.0))}"],
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
            inputs=["HMM observation vector", f"Model: {ctx.model_path}"],
            outputs=["Regime probability vector", f"Confidence {summary['confidence']:.2f}"],
        ),
        node(
            "engine_route",
            "Engine Route?",
            "Choose rule, HMM, or hybrid decision branch",
            kind="decision",
            metrics=[
                metric("Engine", ctx.engine.upper(), "accent"),
                metric("Method", str(ctx.detection_method).upper(), "accent"),
            ],
            inputs=["Rule raw regime", "Configured engine"],
            outputs=["Rule branch", "HMM availability check"],
        ),
        node(
            "hmm_availability",
            "HMM Available?",
            "Check model inference and probability vector",
            kind="decision",
            status="ready" if ctx.hmm_available else "fallback",
            metrics=[
                metric("Available", "yes" if ctx.hmm_available else "no", "positive" if ctx.hmm_available else "negative"),
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
            status="fallback" if ctx.is_fallback else "ready",
            metrics=[
                metric("Reason", "fallback" if ctx.is_fallback else "rule_only", "warning" if ctx.is_fallback else "accent"),
                metric("Raw", value(ctx.raw_regime)),
            ],
            inputs=["Rule score", "Engine route"],
            outputs=["Raw regime candidate"],
        ),
        node(
            "mode_hmm_only",
            "HMM-Only Path",
            "Use HMM argmax when engine is HMM",
            kind="path",
            metrics=[metric("Reason", "hmm_only"), metric("Raw", summary["raw_regime"], "accent")],
            inputs=["HMM probability vector"],
            outputs=["Raw regime candidate"],
        ),
        node(
            "hybrid_compare",
            "Rule == HMM?",
            "Hybrid consensus check before confidence override",
            kind="decision",
            metrics=[metric("Reason", ctx.decision_reason or "rule_only"), metric("Consensus", "yes" if ctx.is_consensus else "no")],
            inputs=["Rule raw regime", "HMM raw regime"],
            outputs=["Consensus path", "Disagreement path"],
        ),
        node(
            "path_consensus",
            "Consensus Path",
            "Rule and HMM agree; use HMM probabilities",
            kind="path",
            metrics=[metric("Reason", "hmm_rule_consensus"), metric("Raw", summary["raw_regime"], "accent")],
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
                metric("Threshold", f"{ctx.override_threshold:.2f}"),
                metric("Trend gate", f"≥ {fmt_ratio(detection['regime_trend_confirm'])}"),
                metric("Breadth gate", f"≥ {fmt_ratio(detection['breadth_bull_threshold'])}"),
            ],
            inputs=["Disagreement result", "HMM confidence"],
            outputs=["Override path", "Blend path"],
        ),
        node(
            "path_override",
            "Override Path",
            "High-confidence HMM overrides rule regime",
            kind="path",
            metrics=[metric("Reason", "hmm_high_confidence_override"), metric("Raw", summary["raw_regime"], "accent")],
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
                metric("Rule W", fmt_percent_points(ctx.blend_rule_weight * 100)),
                metric("HMM W", fmt_percent_points(ctx.blend_hmm_weight * 100)),
            ],
            inputs=["Rule vote", "HMM probabilities"],
            outputs=["Raw regime candidate"],
        ),
        node(
            "raw_regime",
            "Raw Regime",
            "Resolved pre-dwell market regime",
            metrics=[metric("Raw", summary["raw_regime"], "accent"), metric("Reason", ctx.decision_reason or "rule_only")],
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
                metric("Min dwell", str(int(detection["regime_min_dwell"]))),
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
                metric("Dwell", f"{ctx.dwell_count}/{ctx.min_dwell}"),
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
                metric("Conf th", pct(adaptive_params.get("confidence_threshold"))),
                metric("Max positions", adaptive_params.get("max_positions", "—")),
                metric("Stop loss", pct(adaptive_params.get("stop_loss"))),
            ],
            inputs=["Confirmed regime", "Probability vector"],
            outputs=["Strategy risk overlay", "Asset allocator", "Web telemetry"],
        ),
    ]
