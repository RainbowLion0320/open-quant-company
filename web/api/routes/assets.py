"""Asset overview route — exposes multi-asset provenance and readiness."""
from fastapi import APIRouter
from web.api.models import AssetOverviewItem, AssetOverviewResponse

router = APIRouter(prefix="/api/assets", tags=["Assets"])


@router.get("/overview", response_model=AssetOverviewResponse)
async def assets_overview():
    """Return asset type coverage, provenance, and readiness."""
    from data.assets.stock import StockAsset
    from data.assets.etf import ETFAsset
    from data.assets.bond import BondAsset
    from data.assets.futures import FuturesAsset

    items = []
    for cls in (StockAsset, ETFAsset, BondAsset, FuturesAsset):
        try:
            adapter = cls()
            universe = adapter.get_universe()
            items.append(AssetOverviewItem(
                asset_type=adapter.asset_type,
                label=adapter.label,
                enabled=True,
                data_source=adapter.DATA_SOURCE,
                data_source_detail=adapter.DATA_SOURCE_DETAIL,
                research_ready=adapter.RESEARCH_READY,
                tradable=adapter.TRADABLE,
                universe_size=len(universe),
            ))
        except Exception:
            pass

    # Crypto is disabled by default
    try:
        from data.assets.crypto import CryptoAsset
        adapter = CryptoAsset()
        items.append(AssetOverviewItem(
            asset_type=adapter.asset_type,
            label=adapter.label,
            enabled=False,
            data_source=adapter.DATA_SOURCE,
            data_source_detail=adapter.DATA_SOURCE_DETAIL,
            research_ready=adapter.RESEARCH_READY,
            tradable=adapter.TRADABLE,
            universe_size=0,
        ))
    except Exception:
        pass

    return {"items": items, "total": len(items)}
