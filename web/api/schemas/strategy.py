"""Strategy, signal, and backtest response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    detail: dict[str, Any] | None = None
    computed_at: str = ""


class StrategyRunRequest(BaseModel):
    strategy: str = Field(..., description="buffett/multifactor/cybernetic/all")
    limit: int = Field(default=0, description="限制股票数, 0=全部")
    params: dict[str, Any] | None = Field(default=None, description="覆盖默认参数")
    mode: str = Field(default="production", description="production/research")


class StrategyRunResponse(BaseModel):
    job_id: str
    status: str = "started"


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int = 0
    message: str = ""
    result: dict[str, Any] | None = None


class SignalChange(BaseModel):
    date: str
    strategy: str
    symbol: str
    name: str
    from_signal: str
    to_signal: str
    score: float | None = None


class BacktestOverview(BaseModel):
    strategies: dict[str, dict[str, Any]] = {}
    bench_return: float = 0.0
    start: str = ""
    end: str = ""


class BacktestDetail(BaseModel):
    total_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    equity_curve: list[dict[str, Any]] = []
    bench_curve: list[dict[str, Any]] = []


class StrategyListResponse(BaseModel):
    strategies: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []
    total: int = 0


class StrategyCatalogItemResponse(BaseModel):
    name: str
    label: str
    strategy_type: str
    layer: str
    lifecycle: str
    config_key: str
    data_requirements: list[str]
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_contract: str
    research_sources: list[str] = Field(default_factory=list)


class StrategyCatalogResponse(BaseModel):
    items: list[StrategyCatalogItemResponse]
    total: int


class StrategyEvaluationSummaryResponse(BaseModel):
    baselines: list[str]
    status: str
    note: str


class StrategySignalsResponse(BaseModel):
    strategy: str = ""
    total: int = 0
    buys: int = 0
    signals: list[dict[str, Any]] = []


class StrategyEvidenceItem(BaseModel):
    strategy: str
    path: str
    updated: str | None = None
    exists: bool = True
    promotion_decision: str | None = None
    oos_status: str | None = None
    baseline_count: int = 0
    parse_error: str | None = None


class StrategyEvidenceListResponse(BaseModel):
    items: list[StrategyEvidenceItem] = []
    total: int = 0


class StrategyEvidenceDetailResponse(BaseModel):
    strategy: str
    exists: bool = False
    path: str | None = None
    summary: dict[str, Any] = {}
    artifact: dict[str, Any] = {}
    parse_error: str | None = None
