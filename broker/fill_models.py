"""
Pluggable slippage and fill models for the matching engine.

SlippageModel: adjusts the execution price based on market conditions.
FillModel: determines how many shares get filled at what price.

These are injected into MatchingEngine, making the fill behavior
configurable independently of the broker logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


# ── Slippage Models ──


class SlippageModel(ABC):
    """Adjust execution price to account for market impact and spread."""

    @abstractmethod
    def apply(
        self,
        price: float,
        side: str,
        shares: int,
        ctx: dict[str, Any] | None = None,
    ) -> float:
        """Return the adjusted execution price after slippage."""
        ...


class NoSlippage(SlippageModel):
    """Execution at the exact market price — used in backtests."""

    def apply(self, price: float, side: str, shares: int,
              ctx: dict[str, Any] | None = None) -> float:
        return price


class FixedBpsSlippage(SlippageModel):
    """Fixed basis-point slippage. Buy: price * (1 + bps/10000), Sell: price * (1 - bps/10000)."""

    def __init__(self, bps: float = 5.0):
        self.bps = bps

    def apply(self, price: float, side: str, shares: int,
              ctx: dict[str, Any] | None = None) -> float:
        factor = (1 + self.bps / 10000) if side == "buy" else (1 - self.bps / 10000)
        return price * factor


class VolBasedSlippage(SlippageModel):
    """Slippage scales with volatility. Higher vol → wider spread.

    Formula: bps = min(base_bps * (annualized_vol / 0.20), max_bps)
    """

    def __init__(
        self,
        base_bps: float = 5.0,
        max_bps: float = 50.0,
        vol_floor: float = 0.05,
        vol_reference: float = 0.20,
    ):
        self.base_bps = base_bps
        self.max_bps = max_bps
        self.vol_floor = vol_floor
        self.vol_reference = vol_reference

    def apply(self, price: float, side: str, shares: int,
              ctx: dict[str, Any] | None = None) -> float:
        vol = self._extract_vol(ctx)
        bps = self.base_bps * (max(vol, self.vol_floor) / self.vol_reference)
        bps = min(bps, self.max_bps)
        factor = (1 + bps / 10000) if side == "buy" else (1 - bps / 10000)
        return price * factor

    @staticmethod
    def _extract_vol(ctx: dict[str, Any] | None) -> float:
        if ctx is None:
            return 0.20
        for key in ("annualized_vol", "volatility", "vol_20d"):
            if key in ctx:
                return float(ctx[key])
        return 0.20


# ── Match Result ──


@dataclass
class MatchResult:
    """The outcome of attempting to match an order against the market."""

    filled_shares: int
    fill_price: float
    status: str  # "filled" | "partial_filled" | "rejected"
    reason: str = ""
    slippage_bps: float = 0.0
    commission: float = 0.0


# ── Fill Models ──


class FillModel(ABC):
    """Determine the fill outcome for an order at a given market price."""

    def __init__(self, slippage: SlippageModel | None = None):
        self.slippage = slippage or NoSlippage()

    @abstractmethod
    def evaluate(
        self,
        requested_shares: int,
        side: str,
        market_price: float,
        symbol: str = "",
        ctx: dict[str, Any] | None = None,
    ) -> MatchResult:
        """Evaluate how many shares get filled."""
        ...

    def _adjusted_price(self, price: float, side: str, shares: int,
                        ctx: dict[str, Any] | None = None) -> float:
        return self.slippage.apply(price, side, shares, ctx)


class ImmediateFill(FillModel):
    """Always fills 100% at the current price. Default for backtests."""

    def evaluate(self, requested_shares: int, side: str, market_price: float,
                 symbol: str = "", ctx: dict[str, Any] | None = None) -> MatchResult:
        price = self._adjusted_price(market_price, side, requested_shares, ctx)
        return MatchResult(
            filled_shares=requested_shares,
            fill_price=price,
            status="filled",
            slippage_bps=self._slippage_bps(market_price, price),
        )

    @staticmethod
    def _slippage_bps(market: float, fill: float) -> float:
        if market <= 0:
            return 0
        return abs((fill - market) / market) * 10000


class ProbabilisticFill(FillModel):
    """Fills with a given probability. On partial fill, fills partial_pct of remaining.

    Simulates real-world uncertainty: sometimes orders don't fill completely.
    """

    def __init__(self, fill_prob: float = 0.90, partial_pct: float = 0.50,
                 slippage: SlippageModel | None = None):
        super().__init__(slippage)
        self.fill_prob = fill_prob
        self.partial_pct = partial_pct

    def evaluate(self, requested_shares: int, side: str, market_price: float,
                 symbol: str = "", ctx: dict[str, Any] | None = None) -> MatchResult:
        import random
        if random.random() >= self.fill_prob:
            partial = max(1, int(requested_shares * self.partial_pct))
            price = self._adjusted_price(market_price, side, partial, ctx)
            return MatchResult(
                filled_shares=partial,
                fill_price=price,
                status="partial_filled",
                reason=f"probabilistic partial: {partial}/{requested_shares}",
            )
        price = self._adjusted_price(market_price, side, requested_shares, ctx)
        return MatchResult(
            filled_shares=requested_shares,
            fill_price=price,
            status="filled",
        )


class LimitUpDownAwareFill(FillModel):
    """A-share aware: blocks fills at limit-up (buy) or limit-down (sell).

    Requires ctx to carry:
      - prev_close: float — previous day's close
      - Or directly: limit_up / limit_down: float

    Also checks for suspension (suspended=True in ctx).
    """

    def __init__(self, limit_pct: float = 0.10, slippage: SlippageModel | None = None):
        super().__init__(slippage)
        self.limit_pct = limit_pct

    def evaluate(self, requested_shares: int, side: str, market_price: float,
                 symbol: str = "", ctx: dict[str, Any] | None = None) -> MatchResult:
        ctx = ctx or {}

        # Suspension check
        if ctx.get("suspended"):
            return MatchResult(
                filled_shares=0,
                fill_price=market_price,
                status="rejected",
                reason=f"{symbol} 停牌无法交易",
            )

        prev_close = ctx.get("prev_close", 0)
        limit_up = ctx.get("limit_up", prev_close * (1 + self.limit_pct) if prev_close > 0 else float("inf"))
        limit_down = ctx.get("limit_down", prev_close * (1 - self.limit_pct) if prev_close > 0 else 0)

        if side == "buy" and market_price >= limit_up:
            return MatchResult(
                filled_shares=0,
                fill_price=market_price,
                status="rejected",
                reason=f"{symbol} 涨停 (limit_up={limit_up:.2f})，无法买入",
            )
        if side == "sell" and market_price <= limit_down:
            return MatchResult(
                filled_shares=0,
                fill_price=market_price,
                status="rejected",
                reason=f"{symbol} 跌停 (limit_down={limit_down:.2f})，无法卖出",
            )

        price = self._adjusted_price(market_price, side, requested_shares, ctx)
        return MatchResult(
            filled_shares=requested_shares,
            fill_price=price,
            status="filled",
        )


# ── Composite ──


class CompositeFill(FillModel):
    """Chains multiple fill models in order. First non-filled result wins."""

    def __init__(self, models: list[FillModel]):
        super().__init__()
        self.models = models

    def evaluate(self, requested_shares: int, side: str, market_price: float,
                 symbol: str = "", ctx: dict[str, Any] | None = None) -> MatchResult:
        for m in self.models:
            result = m.evaluate(requested_shares, side, market_price, symbol, ctx)
            if result.status != "filled":
                return result
        # All passed — fill at the last model's price
        last = self.models[-1]
        return last.evaluate(requested_shares, side, market_price, symbol, ctx)
