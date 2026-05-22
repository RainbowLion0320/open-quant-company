"""Pydantic 类型定义 — 所有API出入参类型化"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ── 市场 ──

class MarketSnapshot(BaseModel):
    regime: str = Field(..., description="市场状态: bull/bear/sideways")
    ma_trend: str = Field(..., description="均线趋势描述")
    volume_trend: str = Field(..., description="成交量趋势")
    breadth: float = Field(..., description="市场涨跌比")
    confidence: float = Field(..., description="置信度 0-1")

class KLineItem(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int

class MarketResponse(BaseModel):
    regime: MarketSnapshot
    kline: List[KLineItem]
    config: Dict[str, Any]
    updated: str

# ── 策略 ──

class StrategyInfo(BaseModel):
    name: str
    label: str
    total: int = 0
    buys: int = 0
    last_computed: str = ""

class StrategySignal(BaseModel):
    strategy: str = ""
    symbol: str
    name: str
    industry: str = ""
    score: float = 0
    signal: str = "hold"
    detail: Optional[Dict[str, Any]] = None
    computed_at: str = ""

class StrategyRunRequest(BaseModel):
    strategy: str = Field(..., description="buffett/multifactor/cybernetic/all")
    limit: int = Field(default=0, description="限制股票数, 0=全部")
    params: Optional[Dict[str, Any]] = Field(default=None, description="覆盖默认参数")

class StrategyRunResponse(BaseModel):
    job_id: str
    status: str = "started"

class JobStatus(BaseModel):
    job_id: str
    status: str  # pending/running/done/error
    progress: int = 0  # 0-100
    message: str = ""
    result: Optional[Dict[str, Any]] = None

# ── 个股 ──

class StockDetail(BaseModel):
    symbol: str
    name: str
    industry: str
    sector: str

class FinancialData(BaseModel):
    period: str
    roe: Optional[float] = None
    gross_margin: Optional[float] = None
    net_margin: Optional[float] = None
    debt_equity: Optional[float] = None
    net_profit: Optional[float] = None
    revenue: Optional[float] = None
    profit_growth: Optional[float] = None

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
    financials: List[FinancialData]
    buffett_result: Optional[Dict[str, Any]] = None
    signals: List[StrategySignal]
    kline: List[KLineItem]
    dcf: Optional[DCFResult] = None

# ── 模拟交易 ──

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

# ── 信号历史 ──

class SignalChange(BaseModel):
    date: str
    strategy: str
    symbol: str
    name: str
    from_signal: str
    to_signal: str
    score: Optional[float] = None

# ── Multi-Asset (P2-13) ──

class MultiAssetCard(BaseModel):
    key: str
    label: str
    symbol: str
    value: Optional[float] = None
    change: float = 0.0
    change_pct: float = 0.0
    unit: str = ""
    series: List[Dict[str, Any]] = []
    data_source: str = Field(default="real", description="real | proxy | placeholder | cached | missing")
    source_detail: str = Field(default="", description="Human-readable detail about the data origin")

# ── Regime ──

class RegimeSnapshot(BaseModel):
    regime: str = "unknown"
    regime_score: float = 50.0
    multi_asset: List[MultiAssetCard] = []
    freshness: Dict[str, Any] = {}
    updated: str = ""

# ── 回测 ──

class BacktestOverview(BaseModel):
    strategies: Dict[str, Dict[str, Any]] = {}
    bench_return: float = 0.0
    start: str = ""
    end: str = ""

class BacktestDetail(BaseModel):
    total_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    equity_curve: List[Dict[str, Any]] = []
    bench_curve: List[Dict[str, Any]] = []

# ── 策略列表 ──

class StrategyListResponse(BaseModel):
    strategies: List[Dict[str, Any]] = []
    registry: List[Dict[str, Any]] = []
    total: int = 0

class StrategySignalsResponse(BaseModel):
    strategy: str = ""
    total: int = 0
    buys: int = 0
    signals: List[Dict[str, Any]] = []

# ── 通用 ──

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: str = ""

class HealthResponse(BaseModel):
    status: str = "ok"
    backend: str = "duckdb"
    data_updated: str = ""
    stocks_scanned: int = 0
    strategies: int = 0
    version: str = "2.0.0"
