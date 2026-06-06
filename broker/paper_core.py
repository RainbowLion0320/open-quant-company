"""PaperBroker simulation implementation."""
from __future__ import annotations

from broker.base import Broker
from broker.exchange import AShareExchange
from broker.fill_models import (
    CompositeFill,
    FillModel,
    ImmediateFill,
    LimitUpDownAwareFill,
    NoSlippage,
    SlippageModel,
)
from broker.ledger import EventLedger
from broker.matcher import MatchingEngine
from broker.models import Account, Order, Position
from broker.order_sm import OrderStateMachine
from broker.paper_orders import PaperOrderService
from broker.paper_state import PaperStateMixin


class PaperBroker(PaperStateMixin, Broker):
    """
    Local paper broker with event-sourced order lifecycle, pluggable matching,
    A-share cost modeling, optional risk pre-checks, and T+1 sell limits.
    """

    def __init__(
        self,
        initial_cash: float = 1_000_000,
        commission_rate: float = 0.00081,
        stamp_duty: float = 0.0005,
        t_plus_1: bool = True,
        enable_risk: bool = True,
        fill_model: FillModel | None = None,
        slippage_model: SlippageModel | None = None,
        ledger: EventLedger | None = None,
    ):
        self._cash = initial_cash
        self._frozen_cash = 0.0
        self._positions: dict[str, Position] = {}
        self._orders: list[Order] = []
        self._order_counter = 0
        self._today_sells: dict[str, int] = {}
        self._today_buys: dict[str, int] = {}
        self._peak_equity = initial_cash
        self.t_plus_1 = t_plus_1
        self._prices: dict[str, float] = {}
        self._order_sms: dict[str, OrderStateMachine] = {}
        self._ledger = ledger or EventLedger()
        self._exchange = AShareExchange(commission=commission_rate, stamp_tax=stamp_duty)
        self._order_service = PaperOrderService()

        slippage = slippage_model or NoSlippage()
        self._fill_model = fill_model or CompositeFill([
            LimitUpDownAwareFill(slippage=slippage),
            ImmediateFill(slippage=slippage),
        ])
        self._matcher = MatchingEngine(exchange=self._exchange, fill_model=self._fill_model)

        self._risk_mgr = None
        if enable_risk:
            from broker.risk import RiskManager

            self._risk_mgr = RiskManager()

    @property
    def ledger(self) -> EventLedger:
        return self._ledger

    @property
    def matcher(self) -> MatchingEngine:
        return self._matcher

    @property
    def order_states(self) -> dict[str, OrderStateMachine]:
        return self._order_sms

    def set_prices(self, prices: dict[str, float]) -> None:
        """Set current quotes before placing market or limit orders."""
        self._prices.update(prices)
        for code, price in prices.items():
            if code in self._positions:
                self._positions[code].current_price = price

    def _resolve_price(self, code: str, price: float) -> float:
        """Resolve market order price. Returns 0 when no quote is available."""
        if price > 0:
            return price
        return self._prices.get(code, 0)

    def get_positions(self) -> list[Position]:
        return [position for position in self._positions.values() if position.volume > 0]

    def get_balance(self) -> Account:
        market_value = sum(position.market_value for position in self._positions.values())
        return Account(
            total_asset=self._cash + self._frozen_cash + market_value,
            cash=self._cash,
            frozen_cash=self._frozen_cash,
            market_value=market_value,
        )

    def submit_order(self, code: str, price: float, volume: int, side: str) -> str:
        return self._order_service.submit_order(self, code, price, volume, side)

    def cancel_order(self, order_id: str) -> bool:
        return self._order_service.cancel_order(self, order_id)

    def get_orders(self) -> list[Order]:
        return self._order_service.get_orders(self)

    def get_today_trades(self) -> list[Order]:
        return self._order_service.get_today_trades(self)

    def end_of_day(self) -> None:
        self._order_service.end_of_day(self)

    def summary(self) -> str:
        balance = self.get_balance()
        positions = self.get_positions()
        lines = [
            "══════════════════════════",
            "  PaperBroker 账户概览",
            "══════════════════════════",
            f"  总资产: {balance.total_asset:,.2f}",
            f"  可用资金: {balance.cash:,.2f}",
            f"  持仓市值: {balance.market_value:,.2f}",
            f"  持仓数量: {len(positions)}",
        ]
        if positions:
            lines.append("  ────────────────────────")
            for position in sorted(positions, key=lambda item: -item.market_value)[:10]:
                lines.append(
                    f"  {position.code} x{position.volume}  "
                    f"成本{position.avg_cost:.2f} 现价{position.current_price:.2f}  "
                    f"盈亏{position.pnl_pct * 100:+.1f}%"
                )
        lines.append("══════════════════════════")
        return "\n".join(lines)
