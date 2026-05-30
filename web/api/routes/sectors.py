"""Sector / Industry API — radar overview, detail and exposure."""

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException

from web.api.models import SectorOverviewResponse
from web.api.services import sectors as sector_service

router = APIRouter(prefix="/api/sectors", tags=["Sectors"])

@router.get("/overview", response_model=SectorOverviewResponse)
def sector_overview():
    """Return sector performance ranking + signal summary."""
    return sector_service.build_sector_overview()


@router.get("/exposure")
def sector_exposure():
    """Return portfolio exposure by sector."""
    return sector_service.build_sector_exposure()


@router.get("/{industry:path}/stocks")
def sector_stocks_retired(industry: str):
    """Retired: sector radar no longer exposes member stock lists."""
    raise HTTPException(status_code=410, detail="Sector member stock list is retired")


@router.get("/{industry:path}")
def sector_detail(industry: str):
    """Return detail for a single sector."""
    return sector_service.build_sector_detail(unquote(industry))
