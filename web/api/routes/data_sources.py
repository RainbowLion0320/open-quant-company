"""Data source capability routes."""

from fastapi import APIRouter

from web.api.services.data_sources import data_source_capabilities_payload

router = APIRouter(prefix="/api/data-sources", tags=["Data Sources"])


@router.get("/capabilities")
async def data_source_capabilities():
    """Return the latest read-only source capability artifact."""
    return data_source_capabilities_payload()
