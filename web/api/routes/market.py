"""市场数据路由"""

from fastapi import APIRouter, Query

from web.api.services import market as market_service

router = APIRouter(prefix="/api/market", tags=["Market"])

# Backward-compatible private aliases for older tests/imports.
_load_index = market_service.load_index
_position_capacity = market_service.position_capacity
_multi_asset_cards = market_service.multi_asset_cards


@router.get("/regime")
async def market_regime():
    """轻量端点: 仅返回顶栏遥测所需数据。"""
    return market_service.build_market_regime()


@router.get("")
async def market_overview(range: str = Query(default="6M", pattern="^(1D|1M|6M|YTD)$")):
    """市场总览: regime + K线 + 核心指数 + 宏观。"""
    return market_service.build_market_overview(range)
