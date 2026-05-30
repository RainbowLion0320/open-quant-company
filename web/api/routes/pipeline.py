"""Calculation pipeline transparency routes."""

from fastapi import APIRouter

from web.api.services import pipeline as pipeline_service

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])


@router.get("/market-regime")
async def market_regime_pipeline():
    """Market Regime calculation flow for Web Pipeline page."""
    return pipeline_service.build_market_regime_pipeline()
