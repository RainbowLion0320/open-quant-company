"""Calculation pipeline transparency routes."""

from fastapi import APIRouter, HTTPException

from web.api.models import PipelineDetailResponse, PipelineRegistryResponse
from web.api.services import pipeline as pipeline_service

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])


@router.get("", response_model=PipelineRegistryResponse)
async def list_pipelines():
    """List all available pipelines."""
    items = pipeline_service.list_pipelines()
    return {"items": items, "total": len(items)}


@router.get("/market-regime", response_model=PipelineDetailResponse)
async def market_regime_pipeline():
    """Market Regime calculation flow for Web Pipeline page."""
    return pipeline_service.build_market_regime_pipeline()


@router.get("/{pipeline_key}", response_model=PipelineDetailResponse)
async def get_pipeline(pipeline_key: str):
    """Return a specific pipeline by key."""
    result = pipeline_service.build_pipeline(pipeline_key)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline: {pipeline_key}")
    return result
