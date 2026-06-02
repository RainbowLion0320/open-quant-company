"""Market Regime pipeline payload builder facade."""

from __future__ import annotations

from core.settings import get_section
from cybernetics.orchestrator import QuantOrchestrator
from web.api.services.pipelines.common import updated_timestamp
from web.api.services.pipelines.market_regime_context import build_market_regime_context
from web.api.services.pipelines.market_regime_edges import build_market_regime_edges
from web.api.services.pipelines.market_regime_nodes import build_market_regime_nodes


def build_market_regime_pipeline() -> dict[str, object]:
    """Build Market Regime calculation pipeline payload."""
    ctx = build_market_regime_context(get_section, QuantOrchestrator)
    return {
        "pipeline_key": "market_regime",
        "updated": updated_timestamp(),
        "summary": ctx.summary,
        "nodes": build_market_regime_nodes(ctx),
        "edges": build_market_regime_edges(ctx),
        "warnings": ctx.warnings,
    }
