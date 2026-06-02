"""Portfolio, stock, and asset response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from web.api.schemas.market import KLineItem
from web.api.schemas.strategy import StrategySignal


class StockDetail(BaseModel):
    symbol: str
    name: str
    industry: str
    sector: str


class FinancialData(BaseModel):
    period: str
    roe: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    debt_equity: float | None = None
    net_profit: float | None = None
    revenue: float | None = None
    profit_growth: float | None = None


class DCFParams(BaseModel):
    fcf: float = Field(..., description="自由现金流(亿)")
    growth_rate: float = Field(default=0.05, description="增长率")
    terminal_growth: float = Field(default=0.03)
    discount_rate: float = Field(default=0.08)
    shares: float = Field(..., description="总股本(亿)")


class DCFResult(BaseModel):
    intrinsic_value: float
    current_price: float
    safety_margin: float
    verdict: str


class StockResponse(BaseModel):
    basic: StockDetail
    financials: list[FinancialData]
    buffett_result: dict[str, Any] | None = None
    signals: list[StrategySignal]
    kline: list[KLineItem]
    dcf: DCFResult | None = None


class StockListItem(BaseModel):
    symbol: str
    name: str = ""
    industry: str = ""
    sector: str = ""
    price: float | None = None
    change_pct: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    total_mv: float | None = None
    buffett_score: float | None = None
    roe: float | None = None
    gross_margin: float | None = None
    signal_score: float | None = None
    signal: str = "hold"
    buy_signals: int = 0
    signal_count: int = 0
    top_strategy: str = ""
    updated_at: str = ""


class StockListResponse(BaseModel):
    stocks: list[StockListItem]
    total: int
    limit: int
    updated_at: str = ""


class PositionItem(BaseModel):
    code: str
    name: str = ""
    volume: int
    avg_cost: float
    current_price: float
    market_value: float
    pnl: float
    pnl_pct: float


class AccountInfo(BaseModel):
    total_asset: float
    cash: float
    frozen_cash: float
    market_value: float


class OrderRequest(BaseModel):
    code: str
    price: float
    volume: int
    side: str = Field(..., description="buy/sell")


class OrderItem(BaseModel):
    order_id: str
    code: str
    side: str
    price: float
    volume: int
    filled_volume: int
    status: str
    created_at: str


class AssetOverviewItem(BaseModel):
    asset_type: str
    label: str
    enabled: bool = True
    data_source: str = "unknown"
    data_source_detail: str = ""
    research_ready: bool = False
    tradable: bool = False
    universe_size: int = 0
    error: str = ""


class AssetOverviewResponse(BaseModel):
    items: list[AssetOverviewItem] = []
    total: int = 0
