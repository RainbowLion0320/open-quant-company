"""Asset overview route — exposes multi-asset provenance and readiness."""
from fastapi import APIRouter
from web.api.schemas.portfolio import AssetOverviewItem, AssetOverviewResponse
from web.api.services.assets import asset_overview_payload

router = APIRouter(prefix="/api/assets", tags=["Assets"])


@router.get("/overview", response_model=AssetOverviewResponse)
async def assets_overview():
    """Return asset type coverage, provenance, and readiness."""
    payload = asset_overview_payload()
    return {
        "items": [AssetOverviewItem(**item) for item in payload["items"]],
        "total": payload["total"],
    }
