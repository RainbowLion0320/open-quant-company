"""
Pipeline data types — the shared vocabulary between Alpha, Portfolio, Risk, and Execution.

Every stage reads and writes these types.  This is the contract that lets backtest
and paper trading share the same pipeline while only the final execution layer differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class AlphaSignal:
    """Strategy output: a directional opinion with confidence — NOT a buy/sell decision."""

    symbol: str
    strategy: str
    direction: str  # "buy" | "sell" | "hold"
    confidence: float  # 0.0–1.0
    score: float  # raw score (0–100, strategy-specific scale)
    horizon_days: int = 20
    reason: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError(f"confidence must be 0–1, got {self.confidence}")


@dataclass
class PortfolioTarget:
    """Portfolio constructor output: desired allocation for a single symbol."""

    symbol: str
    strategy: str
    target_weight: float  # 0.0–1.0, fraction of total portfolio
    target_shares: int = 0
    current_weight: float = 0.0
    current_shares: int = 0
    delta_shares: int = 0  # positive=buy, negative=sell
    reason: str = ""

    @property
    def side(self) -> str:
        if self.delta_shares > 0:
            return "buy"
        if self.delta_shares < 0:
            return "sell"
        return "hold"


@dataclass
class OrderIntent:
    """Risk-adjusted execution instruction — ready to submit to a broker."""

    symbol: str
    side: str  # "buy" | "sell"
    shares: int
    price: float
    urgency: str = "market"  # "market" | "limit"
    max_slippage: float = 0.02
    strategy: str = ""
    target_ref: str = ""  # PortfolioTarget symbol for traceability
    order_id: str = ""  # assigned by broker on submission (P1-7)
    event_id: str = ""  # ledger event_id for traceability (P1-7)


@dataclass
class FillResult:
    """Execution result for a single order intent."""

    symbol: str
    side: str
    requested_shares: int
    filled_shares: int
    fill_price: float
    commission: float = 0.0
    slippage: float = 0.0
    status: str = "filled"  # "filled" | "partial" | "rejected"
    reject_reason: str = ""
    timestamp: str = ""
    # P1-7: event sourcing traceability
    order_id: str = ""
    event_id: str = ""
    parent_event_id: str = ""

    @property
    def fill_pct(self) -> float:
        return self.filled_shares / self.requested_shares if self.requested_shares > 0 else 0.0


@dataclass
class PipelineContext:
    """Mutable context carried through pipeline stages."""

    date: date | None = None
    universe: list[str] = field(default_factory=list)
    prices: dict[str, float] = field(default_factory=dict)
    price_history: "pd.DataFrame | None" = None  # full historical close DataFrame for vol/trend computation
    regime: str = "sideways"
    cash: float = 0.0
    holdings: dict[str, int] = field(default_factory=dict)  # symbol → shares
    cost_basis: dict[str, float] = field(default_factory=dict)  # symbol → avg_cost

    # stage outputs
    signals: list[AlphaSignal] = field(default_factory=list)
    targets: list[PortfolioTarget] = field(default_factory=list)
    adjusted_targets: list[PortfolioTarget] = field(default_factory=list)
    intents: list[OrderIntent] = field(default_factory=list)
    fills: list[FillResult] = field(default_factory=list)
