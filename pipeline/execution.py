"""
ExecutionRouter — turn portfolio targets into order intents and fills.

Stage 4 of the pipeline. Two execution modes:
  - BacktestExecutor: simulated fills at market price
  - LiveExecutor (via PaperBroker): submitted to the paper broker

Both share the same target→intent→fill transformation.

P1-7: Unified cost model via AShareExchange. Commission/slippage calculations
are delegated to the exchange, ensuring backtest and paper trading use the same costs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pipeline.types import PortfolioTarget, OrderIntent, FillResult, PipelineContext
from broker.exchange import AShareExchange, Exchange, OrderSide


@dataclass
class ExecutionConfig:
    """Execution configuration.

    Prefer passing an `exchange` for unified cost model (P1-7).
    Raw commission_rate/stamp_duty are fallbacks for backward compatibility.
    """
    commission_rate: float = 0.00081
    stamp_duty: float = 0.0005  # sell only
    lot_size: int = 100
    t_plus_1: bool = True
    today_buys: dict[str, int] | None = None
    exchange: Exchange | None = None  # P1-7: unified cost model

    def get_exchange(self) -> Exchange:
        if self.exchange is not None:
            return self.exchange
        return AShareExchange(
            commission=self.commission_rate,
            stamp_tax=self.stamp_duty,
            lot_size=self.lot_size,
        )


class ExecutionRouter:
    """Turn adjusted portfolio targets into order intents and fills.

    P1-7: Uses AShareExchange for cost calculation, ensuring consistency
    between backtest and paper trading.
    """

    def __init__(self, config: ExecutionConfig | None = None):
        self.config = config or ExecutionConfig()
        self._exchange = self.config.get_exchange()
        self._today_buys: dict[str, int] = {}

    def targets_to_intents(
        self,
        targets: list[PortfolioTarget],
        ctx: PipelineContext,
    ) -> list[OrderIntent]:
        """Convert portfolio targets to order intents. Sells first, then buys."""
        intents: list[OrderIntent] = []

        sells = [t for t in targets if t.delta_shares < 0]
        buys = [t for t in targets if t.delta_shares > 0]

        for t in sells:
            price = ctx.prices.get(t.symbol, 0)
            if price <= 0:
                continue
            shares = abs(t.delta_shares)
            available = ctx.holdings.get(t.symbol, 0)
            if self.config.t_plus_1:
                bought_today = self._today_buys.get(t.symbol, 0)
                available = max(0, available - bought_today)
            shares = min(shares, available)
            if shares <= 0:
                continue
            lot = self.config.lot_size
            shares = max(lot, shares // lot * lot)
            intents.append(OrderIntent(
                symbol=t.symbol,
                side="sell",
                shares=shares,
                price=price,
                strategy=t.strategy,
                target_ref=t.symbol,
            ))

        for t in buys:
            price = ctx.prices.get(t.symbol, 0)
            if price <= 0:
                continue
            lot = self.config.lot_size
            shares = max(lot, t.delta_shares // lot * lot)
            intents.append(OrderIntent(
                symbol=t.symbol,
                side="buy",
                shares=shares,
                price=price,
                strategy=t.strategy,
                target_ref=t.symbol,
            ))

        return intents

    def execute(
        self,
        intents: list[OrderIntent],
        broker=None,
    ) -> list[FillResult]:
        """Execute order intents and return fills.

        When broker is provided, delegates to broker.submit_order() and
        lets the broker handle cost calculation. In backtest mode (no broker),
        uses the Exchange directly.
        """
        fills: list[FillResult] = []
        ts = datetime.now().isoformat()

        for intent in intents:
            if broker is not None:
                # Paper/Live mode: delegate to broker (which uses its own exchange)
                result = broker.submit_order(
                    code=intent.symbol,
                    price=intent.price,
                    volume=intent.shares,
                    side=intent.side,
                )
                if result and str(result).startswith("PAPER_"):
                    order_id = result
                    intent.order_id = order_id
                    fills.append(FillResult(
                        symbol=intent.symbol,
                        side=intent.side,
                        requested_shares=intent.shares,
                        filled_shares=intent.shares,
                        fill_price=intent.price,
                        commission=self._calc_commission(intent),
                        status="filled",
                        timestamp=ts,
                        order_id=order_id,
                    ))
                    if intent.side == "buy":
                        self._today_buys[intent.symbol] = (
                            self._today_buys.get(intent.symbol, 0) + intent.shares
                        )
                else:
                    fills.append(FillResult(
                        symbol=intent.symbol,
                        side=intent.side,
                        requested_shares=intent.shares,
                        filled_shares=0,
                        fill_price=intent.price,
                        status="rejected",
                        reject_reason=str(result),
                        timestamp=ts,
                    ))
            else:
                # Backtest mode: immediate fill at market using unified exchange cost
                side_enum = OrderSide.BUY if intent.side == "buy" else OrderSide.SELL
                commission = self._exchange.calc_cost(
                    intent.price, intent.shares, side_enum
                )
                fills.append(FillResult(
                    symbol=intent.symbol,
                    side=intent.side,
                    requested_shares=intent.shares,
                    filled_shares=intent.shares,
                    fill_price=intent.price,
                    commission=round(commission, 2),
                    status="filled",
                    timestamp=ts,
                ))

        return fills

    def _calc_commission(self, intent: OrderIntent) -> float:
        """Calculate commission via the unified exchange model."""
        side = OrderSide.BUY if intent.side == "buy" else OrderSide.SELL
        return round(self._exchange.calc_cost(intent.price, intent.shares, side), 2)

    def end_of_day(self):
        """Reset daily buy tracking."""
        self._today_buys.clear()
