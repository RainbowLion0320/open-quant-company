"""Market and sector response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MarketSnapshot(BaseModel):
    regime: str = Field(..., description="市场状态: bull/bear/sideways")
    raw_value: str = Field(default="unknown", description="未做稳定确认的原始市场状态")
    score: float = Field(default=50.0, description="Regime 评分 0-100")
    ma_trend: str = Field(..., description="均线趋势描述")
    volume_trend: str = Field(..., description="成交量趋势")
    breadth: float = Field(..., description="全市场上涨家数占比")
    breadth_detail: dict[str, Any] = Field(default_factory=dict, description="全市场宽度明细")
    score_components: dict[str, Any] = Field(default_factory=dict, description="Regime 评分分项")
    stability: dict[str, Any] = Field(default_factory=dict, description="Regime 稳定确认状态")
    confidence: float = Field(default=0.0, description="置信度 0-1")


class KLineItem(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketResponse(BaseModel):
    regime: MarketSnapshot
    kline: list[KLineItem]
    config: dict[str, Any]
    updated: str


class MultiAssetCard(BaseModel):
    key: str
    label: str
    symbol: str
    value: float | None = None
    change: float = 0.0
    change_pct: float = 0.0
    unit: str = ""
    series: list[dict[str, Any]] = []
    data_source: str = Field(default="real", description="real | proxy | placeholder | cached | missing")
    source_detail: str = Field(default="", description="Human-readable detail about the data origin")


class RegimeSnapshot(BaseModel):
    regime: str = "unknown"
    regime_score: float = 50.0
    multi_asset: list[MultiAssetCard] = []
    freshness: dict[str, Any] = {}
    updated: str = ""


class MarketRegimeResponse(BaseModel):
    regime: dict[str, Any] = {}
    multi_asset: list[dict[str, Any]] = []
    freshness: dict[str, Any] = {}
    config: dict[str, Any] = {}
    position_capacity: dict[str, Any] = {}
    updated: str = ""


class MarketOverviewResponse(BaseModel):
    regime: dict[str, Any] = {}
    kline: list[dict[str, Any]] = []
    range: str = "6M"
    multi_asset: list[dict[str, Any]] = []
    macro: list[dict[str, Any]] = []
    freshness: dict[str, Any] = {}
    pool_size: int = 0
    position_capacity: dict[str, Any] = {}
    config: dict[str, Any] = {}
    updated: str = ""


class SectorOverviewResponse(BaseModel):
    sectors: list[dict[str, Any]] = []
    total_sectors: int = 0
    top_performers: list[dict[str, Any]] = []
    bottom_performers: list[dict[str, Any]] = []
    signal_dispersion: float = 0.0
    data_source: str = ""
    capital_source: str = ""
    freshness: dict[str, Any] = {}
