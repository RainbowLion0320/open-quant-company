"""PaperBroker simulation implementation."""
from __future__ import annotations

from typing import Any

from broker.base import Broker
from broker.exchange import AShareExchange, OrderSide
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

    def preview_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        """Preview a paper order without creating an order or mutating broker state."""
        normalized = self._normalize_preview_intent(intent)
        symbol = str(normalized["symbol"])
        side = str(normalized["side"])
        quantity = int(normalized["quantity"])
        price = self._resolve_price(symbol, float(normalized["limit_price"]))
        blockers: list[str] = []

        if not symbol:
            blockers.append("missing_symbol")
        if side not in {"buy", "sell"}:
            blockers.append("invalid_side")
        if quantity <= 0:
            blockers.append("invalid_quantity")
        if str(normalized["order_type"]) != "limit":
            blockers.append("unsupported_order_type")
        if price <= 0:
            blockers.append("missing_execution_price")
        if not normalized["evidence_refs"]:
            blockers.append("missing_evidence")

        balance = self.get_balance()
        notional = max(price, 0.0) * max(quantity, 0)
        side_enum = OrderSide.BUY if side == "buy" else OrderSide.SELL
        fees = self._exchange.calc_cost(max(price, 0.0), max(quantity, 0), side_enum) if side in {"buy", "sell"} else 0.0
        checks: list[dict[str, Any]] = []

        if side == "buy" and price > 0 and quantity > 0:
            estimated_cost = notional + fees
            cash_passed = estimated_cost <= balance.cash
            if not cash_passed:
                blockers.append("insufficient_cash")
            checks.append(
                {
                    "name": "cash",
                    "passed": cash_passed,
                    "available_cash": balance.cash,
                    "estimated_cost": estimated_cost,
                }
            )
            if self._risk_mgr:
                portfolio = self._preview_portfolio()
                risk_passed, risk_results = self._risk_mgr.check_order(symbol, notional, portfolio)
                if not risk_passed:
                    blockers.append("risk_gate_failed")
                checks.append(
                    {
                        "name": "paper_risk_manager",
                        "passed": risk_passed,
                        "results": [
                            {
                                "rule": result.rule_name,
                                "passed": result.passed,
                                "reason": result.reason,
                                "current_value": result.current_value,
                                "limit_value": result.limit_value,
                            }
                            for result in risk_results
                        ],
                    }
                )
        elif side == "sell" and price > 0 and quantity > 0:
            position = self._positions.get(symbol)
            holdings = position.volume if position else 0
            bought_today = self._today_buys.get(symbol, 0) if self.t_plus_1 else 0
            available = max(0, holdings - bought_today)
            sell_passed = available >= quantity
            if not sell_passed:
                blockers.append("insufficient_sellable_shares")
            checks.append(
                {
                    "name": "sellable_shares",
                    "passed": sell_passed,
                    "holdings": holdings,
                    "bought_today": bought_today,
                    "available": available,
                }
            )

        unique_blockers = list(dict.fromkeys(blockers))
        return {
            "status": "preview_ready" if not unique_blockers else "blocked",
            "broker": "paper",
            "intent": {**normalized, "limit_price": price},
            "approval_required": True,
            "submitted": False,
            "risk_gate": {
                "passed": not unique_blockers,
                "blockers": unique_blockers,
                "checks": checks,
            },
            "notional": notional,
            "fees": {
                "estimated_total": round(fees, 2),
            },
            "estimated_cash_effect": _cash_effect(side, notional, fees),
            "estimated_position_effect": {
                "symbol": symbol,
                "quantity_delta": quantity if side == "buy" else -quantity,
                "notional_delta": notional if side == "buy" else -notional,
            },
            "account_snapshot": {
                "cash": balance.cash,
                "total_asset": balance.total_asset,
                "market_value": balance.market_value,
            },
            "warnings": [],
        }

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

    def _normalize_preview_intent(self, intent: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": str(intent.get("symbol") or intent.get("code") or "").strip(),
            "side": str(intent.get("side") or "").strip().lower(),
            "quantity": max(_as_int(intent.get("quantity") if "quantity" in intent else intent.get("volume")), 0),
            "order_type": str(intent.get("order_type") or "limit").strip().lower(),
            "limit_price": max(_as_float(intent.get("limit_price") if "limit_price" in intent else intent.get("price")), 0.0),
            "strategy": str(intent.get("strategy") or "manual").strip() or "manual",
            "reason": str(intent.get("reason") or "").strip(),
            "evidence_refs": [str(item) for item in intent.get("evidence_refs", []) if str(item).strip()],
            "risk_snapshot": dict(intent.get("risk_snapshot") or {}),
        }

    def _preview_portfolio(self) -> dict[str, Any]:
        balance = self.get_balance()
        return {
            "total_equity": balance.total_asset,
            "total_exposure": balance.market_value,
            "peak_equity": self._peak_equity,
            "positions": {
                code: {"market_value": position.market_value}
                for code, position in self._positions.items()
                if position.volume > 0
            },
        }


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _cash_effect(side: str, notional: float, fees: float) -> float:
    if side == "buy":
        return -(notional + fees)
    if side == "sell":
        return notional - fees
    return 0.0
