"""Registry for Web pipeline payload builders."""

from __future__ import annotations

from collections.abc import Callable

from web.api.services.pipelines.data_quality import build_data_quality_pipeline
from web.api.services.pipelines.market_regime import build_market_regime_pipeline
from web.api.services.pipelines.portfolio_execution import build_portfolio_execution_pipeline
from web.api.services.pipelines.strategy_evidence import build_strategy_evidence_pipeline


PipelineBuilder = Callable[[], dict[str, object]]


PIPELINE_REGISTRY: dict[str, dict[str, object]] = {
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
