"""Asset overview route — exposes multi-asset provenance and readiness."""
from fastapi import APIRouter
from web.api.models import AssetOverviewItem, AssetOverviewResponse

router = APIRouter(prefix="/api/assets", tags=["Assets"])


@router.get("/overview", response_model=AssetOverviewResponse)
async def assets_overview():
    """Return asset type coverage, provenance, and readiness."""
    from data.assets.overview import asset_overview_items

    items = [AssetOverviewItem(**item) for item in asset_overview_items()]
    return {"items": items, "total": len(items)}
