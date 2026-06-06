"""回测分析路由 — 多策略对比"""

from fastapi import APIRouter
from web.api.services.backtest import backtest_overview_payload, strategy_detail_payload

router = APIRouter(prefix="/api/backtest", tags=["Backtest"])


@router.get("")
async def backtest_overview():
    """三策略对比概览"""
    return backtest_overview_payload()


@router.get("/{strategy}")
async def strategy_detail(strategy: str):
    """单个策略详细数据（净值曲线）"""
    return strategy_detail_payload(strategy)
