"""
Pipeline data types — the shared vocabulary between Alpha, Portfolio, Risk, and Execution.

Every stage reads and writes these types.  This is the contract that lets backtest
and paper trading share the same pipeline while only the final execution layer differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from data.market.assets.contracts import instrument_key, normalize_asset_type, split_instrument_key

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
    asset_type: str = "stock"

    def __post_init__(self):
        self.asset_type = normalize_asset_type(self.asset_type)
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError(f"confidence must be 0–1, got {self.confidence}")

    @property
    def key(self) -> str:
        return instrument_key(self.asset_type, self.symbol)


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
    asset_type: str = "stock"

    def __post_init__(self):
        self.asset_type = normalize_asset_type(self.asset_type)

    @property
    def side(self) -> str:
        if self.delta_shares > 0:
            return "buy"
        if self.delta_shares < 0:
            return "sell"
        return "hold"

    @property
    def key(self) -> str:
        return instrument_key(self.asset_type, self.symbol)


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
    asset_type: str = "stock"

    def __post_init__(self):
        self.asset_type = normalize_asset_type(self.asset_type)

    @property
    def key(self) -> str:
        return instrument_key(self.asset_type, self.symbol)


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
    asset_type: str = "stock"

    def __post_init__(self):
        self.asset_type = normalize_asset_type(self.asset_type)

    @property
    def fill_pct(self) -> float:
        return self.filled_shares / self.requested_shares if self.requested_shares > 0 else 0.0

    @property
    def key(self) -> str:
        return instrument_key(self.asset_type, self.symbol)


@dataclass
class PipelineContext:
    """Mutable context carried through pipeline stages."""

    date: date | None = None
    universe: list[str] = field(default_factory=list)
    universe_assets: dict[str, str] = field(default_factory=dict)  # symbol → asset_type
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

    def asset_type_for(self, symbol: str, default: str = "stock") -> str:
        if symbol in self.universe_assets:
            return normalize_asset_type(self.universe_assets[symbol])
        asset_type, parsed_symbol = split_instrument_key(symbol, default)
        if parsed_symbol != symbol:
            return asset_type
        return normalize_asset_type(default)

    def key_for(self, asset_type: str | None, symbol: str) -> str:
        return instrument_key(asset_type or self.asset_type_for(symbol), symbol)

    def price_for(self, asset_type: str | None, symbol: str) -> float:
        key = self.key_for(asset_type, symbol)
        if key in self.prices:
            return float(self.prices.get(key) or 0)
        if symbol in self.prices:
            return float(self.prices.get(symbol) or 0)
        return 0.0

    def holding_for(self, asset_type: str | None, symbol: str) -> int:
        key = self.key_for(asset_type, symbol)
        if key in self.holdings:
            return int(self.holdings.get(key) or 0)
        if normalize_asset_type(asset_type) == "stock" and symbol in self.holdings:
            return int(self.holdings.get(symbol) or 0)
        return 0

    def holding_symbols(self, asset_type: str | None = None) -> set[str]:
        out: set[str] = set()
        desired = normalize_asset_type(asset_type) if asset_type else ""
        for key, quantity in self.holdings.items():
            if quantity <= 0:
                continue
            current_asset_type, symbol = split_instrument_key(key)
            if desired and current_asset_type != desired:
                continue
            out.add(symbol)
        return out

    def total_equity(self) -> float:
        market_value = 0.0
        for key, quantity in self.holdings.items():
            asset_type, symbol = split_instrument_key(key)
            market_value += int(quantity or 0) * self.price_for(asset_type, symbol)
        return self.cash + market_value
