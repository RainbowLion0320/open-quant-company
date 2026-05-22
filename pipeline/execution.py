"""
ExecutionRouter — turn portfolio targets into order intents and fills.

Stage 4 of the pipeline. Two execution modes:
  - BacktestExecutor: simulated fills at market price
  - LiveExecutor (via PaperBroker): submitted to the paper broker

Both share the same target→intent→fill transformation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pipeline.types import PortfolioTarget, OrderIntent, FillResult, PipelineContext


@dataclass
class ExecutionConfig:
    commission_rate: float = 0.00081
    stamp_duty: float = 0.0005  # sell only
    lot_size: int = 100
    t_plus_1: bool = True
    today_buys: dict[str, int] | None = None


class ExecutionRouter:
    """Turn adjusted portfolio targets into order intents and fills."""

    def __init__(self, config: ExecutionConfig | None = None):
        self.config = config or ExecutionConfig()
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
        """Execute order intents and return fills."""
        fills: list[FillResult] = []
        ts = datetime.now().isoformat()

        for intent in intents:
            if broker is not None:
                result = broker.submit_order(
                    code=intent.symbol,
                    price=intent.price,
                    volume=intent.shares,
                    side=intent.side,
                )
                if result and str(result).startswith("PAPER_"):
                    fills.append(FillResult(
                        symbol=intent.symbol,
                        side=intent.side,
                        requested_shares=intent.shares,
                        filled_shares=intent.shares,
                        fill_price=intent.price,
                        commission=self._calc_commission(intent),
                        status="filled",
                        timestamp=ts,
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
                # Backtest mode: immediate fill at market
                fills.append(FillResult(
                    symbol=intent.symbol,
                    side=intent.side,
                    requested_shares=intent.shares,
                    filled_shares=intent.shares,
                    fill_price=intent.price,
                    commission=self._calc_commission(intent),
                    status="filled",
                    timestamp=ts,
                ))

        return fills

    def _calc_commission(self, intent: OrderIntent) -> float:
        amount = intent.price * intent.shares
        c = amount * self.config.commission_rate
        if intent.side == "sell":
            c += amount * self.config.stamp_duty
        return round(c, 2)

    def end_of_day(self):
        """Reset daily buy tracking."""
        self._today_buys.clear()
