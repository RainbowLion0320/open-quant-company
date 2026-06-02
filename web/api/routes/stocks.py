"""个股深挖路由 — 全景视图 + DCF 估值"""

from fastapi import APIRouter, Query

from web.api.models import DCFParams, DCFResult, StockListResponse, StockResponse
from web.api.services.dcf import compute_dcf_result
from web.api.services.stocks import build_stock_detail, build_stock_list, safe_text

router = APIRouter(prefix="/api/stocks", tags=["Stocks"])


@router.get("", response_model=StockListResponse)
async def list_stocks(
    limit: int = Query(default=300, ge=1, le=1000, description="返回股票数量上限"),
    q: str = Query(default="", description="按代码/名称/行业过滤"),
):
    """股票池默认列表: 基础资料 + 估值 + 质量分 + 策略信号摘要."""
    rows, total = build_stock_list(limit=limit, q=q)
    updated = max((safe_text(row.get("updated_at")) for row in rows), default="")
    return StockListResponse(stocks=rows, total=total, limit=limit, updated_at=updated)


@router.get("/{code}", response_model=StockResponse)
async def get_stock_detail(code: str):
    """个股全景视图: 基本信息 + 财务 + 巴菲特结果 + 策略信号 + K线."""
    return build_stock_detail(code)


@router.post("/dcf", response_model=DCFResult)
async def compute_dcf(
    code: str = Query(..., description="股票代码"),
    params: DCFParams = None,
):
    """DCF 估值计算: 给定 FCF + 增长 + 折现率, 返回内在价值与安全边际."""
    return compute_dcf_result(code, params)
