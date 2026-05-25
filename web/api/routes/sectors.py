"""Sector / Industry API — radar overview, detail, stocks, exposure."""

from urllib.parse import unquote

from fastapi import APIRouter

from web.api.services import sectors as sector_service

router = APIRouter(prefix="/api/sectors", tags=["Sectors"])

# Backward-compatible private aliases for older tests/imports.
_sector_store = sector_service.sector_store
_latest_snapshot = sector_service.latest_snapshot
_source_summary = sector_service.source_summary


@router.get("/overview")
def sector_overview():
    """Return sector performance ranking + signal summary."""
    return sector_service.build_sector_overview()


@router.get("/exposure")
def sector_exposure():
    """Return portfolio exposure by sector."""
    return sector_service.build_sector_exposure()


@router.get("/{industry:path}/stocks")
def sector_stocks(industry: str):
    """Return member stocks for a sector with signal status."""
    return sector_service.build_sector_stocks(unquote(industry))


@router.get("/{industry:path}")
def sector_detail(industry: str):
    """Return detail for a single sector."""
    return sector_service.build_sector_detail(unquote(industry))
