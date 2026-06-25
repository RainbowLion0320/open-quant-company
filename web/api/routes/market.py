"""市场数据路由"""

from fastapi import APIRouter, Query

from web.api.schemas.market import MarketOverviewResponse, MarketRegimeResponse
from web.api.services import market as market_service

router = APIRouter(prefix="/api/market", tags=["Market"])


@router.get("/regime", response_model=MarketRegimeResponse)
async def market_regime():
    """轻量端点: 仅返回顶栏遥测所需数据。"""
    return market_service.build_market_regime()


@router.get("", response_model=MarketOverviewResponse)
async def market_overview(range: str = Query(default="6M", pattern="^(1D|1M|6M|YTD)$")):
    """市场总览: regime + K线 + 核心指数 + 跨资产市场动态。"""
    return market_service.build_market_overview(range)
