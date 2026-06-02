"""Edge builders for the Market Regime pipeline graph."""

from __future__ import annotations

from web.api.services.pipelines.common import edge
from web.api.services.pipelines.market_regime_context import MarketRegimePipelineContext


def build_market_regime_edges(ctx: MarketRegimePipelineContext) -> list[dict[str, object]]:
    return [
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
        edge("hmm_inference", "hmm_availability", active=ctx.is_hmm_candidate),
        edge("engine_route", "mode_rule_only", label="rule only", condition="engine == rule_based", active=ctx.is_rule_only),
        edge("engine_route", "hmm_availability", label="hmm/hybrid", condition="engine in {hmm, hybrid}", active=ctx.is_hmm_candidate),
        edge("hmm_availability", "mode_rule_only", label="fallback", condition="HMM unavailable", active=ctx.is_fallback),
        edge("hmm_availability", "mode_hmm_only", label="hmm only", condition="engine == HMM", active=ctx.is_hmm_only),
        edge("hmm_availability", "hybrid_compare", label="hybrid", condition="engine == hybrid", active=ctx.is_hybrid_path),
        edge("hybrid_compare", "path_consensus", label="yes", condition="rule == HMM", active=ctx.is_consensus),
        edge("hybrid_compare", "confidence_gate", label="no", condition="rule != HMM", active=ctx.is_override or ctx.is_blend),
        edge("confidence_gate", "path_override", label="override", condition=f"confidence >= {ctx.override_threshold:.2f}", active=ctx.is_override),
        edge("confidence_gate", "path_blend", label="blend", condition=f"confidence < {ctx.override_threshold:.2f}", active=ctx.is_blend),
        edge("mode_rule_only", "raw_regime", label="rule raw", active=ctx.is_rule_only or ctx.is_fallback),
        edge("mode_hmm_only", "raw_regime", label="hmm raw", active=ctx.is_hmm_only),
        edge("path_consensus", "raw_regime", label="consensus", active=ctx.is_consensus),
        edge("path_override", "raw_regime", label="override", active=ctx.is_override),
        edge("path_blend", "raw_regime", label="blend", active=ctx.is_blend),
        edge("raw_regime", "stability"),
        edge("stability", "stability_confirmed", label="confirmed", condition="dwell ≥ min_dwell", active=ctx.is_confirmed),
        edge("stability", "stability_pending", label="pending", condition=f"dwell {ctx.dwell_count}/{ctx.min_dwell}", active=ctx.is_pending),
        edge("stability_confirmed", "outputs", active=ctx.is_confirmed),
        edge("stability_pending", "outputs", active=ctx.is_pending),
    ]
