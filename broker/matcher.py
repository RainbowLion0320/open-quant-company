"""
Matching Engine — combines slippage, fill, and exchange models to match orders.

Extracted from PaperBroker to make the matching logic independently testable
and configurable. The engine:
  1. Applies the fill model to determine filled shares and execution price
  2. Calculates transaction costs via the exchange
  3. Returns a detailed MatchResult

PaperBroker (and later MiniQMTBroker) delegates to this engine for matching,
while keeping the order lifecycle management in the broker layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from broker.fill_models import (
    SlippageModel,
    FillModel,
    ImmediateFill,
    NoSlippage,
    MatchResult,
)
from broker.exchange import Exchange, AShareExchange, OrderSide


@dataclass
class MatchContext:
    """Carries all market and portfolio state needed for matching.

    This is the unified context passed through the matching pipeline.
    """
    symbol: str = ""
    side: str = ""               # "buy" | "sell"
    requested_shares: int = 0
    market_price: float = 0.0

    # Market conditions (for LimitUpDownAwareFill, etc.)
    prev_close: float = 0.0
    limit_up: float | None = None
    limit_down: float | None = None
    suspended: bool = False

    # Portfolio state (for risk checks upstream)
    available_cash: float = 0.0
    current_holdings: int = 0   # shares currently held
    t_plus_1_bought_today: int = 0  # shares bought today (can't sell)

    # Volatility context (for VolBasedSlippage)
    annualized_vol: float = 0.0

    # Arbitrary extension
    extra: dict[str, Any] = field(default_factory=dict)

    def to_fill_ctx(self) -> dict[str, Any]:
        """Convert to the dict format expected by FillModel.evaluate()."""
        ctx: dict[str, Any] = {
            "prev_close": self.prev_close,
            "suspended": self.suspended,
            "annualized_vol": self.annualized_vol,
        }
        if self.limit_up is not None:
            ctx["limit_up"] = self.limit_up
        if self.limit_down is not None:
            ctx["limit_down"] = self.limit_down
        ctx.update(self.extra)
        return ctx


class MatchingEngine:
    """Matches orders against market conditions using pluggable models.

    Usage:
        engine = MatchingEngine(
            exchange=AShareExchange(),
            fill_model=ImmediateFill(),
        )
        ctx = MatchContext(symbol="000001", side="buy", requested_shares=500, market_price=12.50)
        result = engine.match(ctx)
        # result.filled_shares, result.fill_price, result.commission
    """

    def __init__(
        self,
        exchange: Exchange | None = None,
        fill_model: FillModel | None = None,
        slippage: SlippageModel | None = None,
    ):
        self.exchange = exchange or AShareExchange()
        self.fill_model = fill_model or ImmediateFill(slippage=slippage or NoSlippage())

    def match(self, ctx: MatchContext) -> MatchResult:
        """Match an order against the current market.

        Returns MatchResult with filled_shares, fill_price, status, and commission.
        """
        # 1) Exchange-level checks: can we trade this symbol?
        if not self.exchange.can_trade(ctx.symbol):
            return MatchResult(
                filled_shares=0,
                fill_price=ctx.market_price,
                status="rejected",
                reason=f"{ctx.symbol} 不可交易 (停牌/退市)",
            )

        # 2) Fill model determines what fills
        fill_ctx = ctx.to_fill_ctx()
        result = self.fill_model.evaluate(
            requested_shares=ctx.requested_shares,
            side=ctx.side,
            market_price=ctx.market_price,
            symbol=ctx.symbol,
            ctx=fill_ctx,
        )

        # 3) Calculate commission via exchange
        side_enum = OrderSide.BUY if ctx.side == "buy" else OrderSide.SELL
        commission = self.exchange.calc_cost(
            result.fill_price,
            result.filled_shares,
            side_enum,
        )

        result.commission = round(commission, 2)
        return result

    def can_afford(self, price: float, shares: int, cash: float,
                   side: str = "buy") -> tuple[bool, int]:
        """Check if we can afford a buy order. Returns (can_afford, max_shares).

        For sell orders, always returns True (we check holdings separately).
        """
        if side == "sell":
            return True, shares

        if shares <= 0:
            return False, 0

        lot = self.exchange.lot_size if hasattr(self.exchange, "lot_size") else 100
        while shares > 0:
            est_cost = shares * price + self.exchange.calc_cost(
                price, shares, OrderSide.BUY
            )
            if est_cost <= cash:
                return True, shares
            shares -= lot

        return False, 0

    def sellable_shares(self, symbol: str, requested: int, holdings: int,
                        bought_today: int = 0, t_plus_1: bool = True) -> int:
        """Determine how many shares can be sold, respecting T+1 and holdings."""
        available = holdings
        if t_plus_1:
            available = max(0, available - bought_today)
        return min(requested, available)

    def __repr__(self) -> str:
        return (f"<MatchingEngine exchange={self.exchange.name} "
                f"fill={type(self.fill_model).__name__}>")
