"""Pipeline transparency service facade."""

from __future__ import annotations

from web.api.services.pipelines import (
    PIPELINE_REGISTRY,
    build_data_quality_pipeline,
    build_market_regime_pipeline,
    build_pipeline,
    build_portfolio_execution_pipeline,
    build_strategy_evidence_pipeline,
    list_pipelines,
)

__all__ = [
    "PIPELINE_REGISTRY",
    "build_data_quality_pipeline",
    "build_market_regime_pipeline",
    "build_pipeline",
    "build_portfolio_execution_pipeline",
    "build_strategy_evidence_pipeline",
    "list_pipelines",
]
