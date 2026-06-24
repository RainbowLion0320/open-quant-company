"""PaperBroker order lifecycle and event-ledger integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from data.market.assets.contracts import instrument_key, normalize_asset_type
from broker.ledger import EventType, LedgerEvent
from broker.matcher import MatchContext
from broker.models import Order, Position
from broker.order_sm import InvalidTransition, OrderState, OrderStateMachine


class PaperOrderService:
    """Order lifecycle service composed by PaperBroker."""

    def submit_order(
        self,
        broker: Any,
        code: str,
        price: float,
        volume: int,
        side: str,
        asset_type: str = "stock",
    ) -> str:
        """Submit an order through risk checks, matching, state transition, and ledger append."""
        asset_type = normalize_asset_type(asset_type)
        key = instrument_key(asset_type, code)
        run_date = datetime.now().strftime("%Y-%m-%d")
        fill_price = broker._resolve_price(code, price, asset_type)
        if fill_price <= 0:
            return f"无行情: {asset_type}:{code}"

        balance = broker.get_balance()
        if broker._risk_mgr and side == "buy":
            portfolio = {
                "total_equity": balance.total_asset,
                "total_exposure": balance.market_value,
                "peak_equity": broker._peak_equity,
                "positions": {
                    c: {"asset_type": p.asset_type, "market_value": p.market_value}
                    for c, p in broker._positions.items()
                    if p.volume > 0
                },
            }
            passed, results = broker._risk_mgr.check_order(code, fill_price * volume, portfolio)
            if not passed:
                reasons = "; ".join(r.reason for r in results if not r.passed)
                return f"风控拒绝: {reasons}"

        if side == "buy":
            can, max_shares = broker._matcher.can_afford(fill_price, volume, broker._cash, side, asset_type)
            if not can:
                if max_shares <= 0:
                    return "资金不足"
                volume = max_shares

        if side == "sell":
            pos = broker._positions.get(key)
            holdings = pos.volume if pos else 0
            bought_today = broker._today_buys.get(key, 0) if broker.t_plus_1 else 0
            available = max(0, holdings - bought_today)
            if available <= 0:
                if broker.t_plus_1 and bought_today > 0:
                    return f"T+1限制: {code} 当日买入不可卖出"
                return f"持仓不足: {code}"
            volume = min(volume, available)

        if volume <= 0:
            return "无可执行数量"

        order, sm, ts = self._create_pending_order(broker, code, side, fill_price, volume, asset_type)
        self._append_order_created(broker, order, ts, run_date)

        pos = broker._positions.get(key)
        result = broker._matcher.match(MatchContext(
            symbol=code,
            asset_type=asset_type,
            side=side,
            requested_shares=volume,
            market_price=fill_price,
            prev_close=pos.avg_cost if pos and pos.avg_cost > 0 else fill_price,
            available_cash=broker._cash,
            current_holdings=pos.volume if pos else 0,
            t_plus_1_bought_today=broker._today_buys.get(key, 0) if broker.t_plus_1 else 0,
        ))

        if result.status == "rejected":
            self._transition_order(
                broker,
                sm,
                order,
                OrderState.REJECTED,
                reason=result.reason,
                run_date=run_date,
                code=code,
                metadata={"fill_price": fill_price, "requested": volume, "asset_type": asset_type},
            )
            broker._orders.append(order)
            return result.reason if result.reason else f"订单被拒绝: {code}"

        self._apply_fill(broker, order, sm, result, volume, side, code, run_date, asset_type)
        broker._orders.append(order)
        if broker._risk_mgr:
            broker._risk_mgr.record_order()
        broker._peak_equity = max(broker._peak_equity, broker.get_balance().total_asset)
        return order.order_id

    def cancel_order(self, broker: Any, order_id: str) -> bool:
        sm = broker._order_sms.get(order_id)
        if not sm or not sm.can_be_cancelled:
            return False

        for order in broker._orders:
            if order.order_id == order_id:
                self._transition_order(
                    broker,
                    sm,
                    order,
                    OrderState.CANCELLED,
                    reason="用户主动撤单",
                    run_date=datetime.now().strftime("%Y-%m-%d"),
                    code=order.code,
                    metadata={"asset_type": order.asset_type},
                )
                return True
        return False

    def get_orders(self, broker: Any) -> list[Order]:
        return broker._orders

    def get_today_trades(self, broker: Any) -> list[Order]:
        return [order for order in broker._orders if order.status == OrderState.FILLED.value]

    def end_of_day(self, broker: Any) -> None:
        """Expire active orders and reset T+1 counters."""
        run_date = datetime.now().strftime("%Y-%m-%d")
        for order_id, sm in list(broker._order_sms.items()):
            if not sm.is_active:
                continue
            order = self._find_order(broker, order_id)
            if order and order.remaining_volume > 0:
                self._transition_order(
                    broker,
                    sm,
                    order,
                    OrderState.EXPIRED,
                    reason=f"收盘未成交: {order.remaining_volume}股剩余",
                    run_date=run_date,
                    code=order.code,
                    metadata={"remaining": order.remaining_volume, "asset_type": order.asset_type},
                )

        for code in list(broker._positions):
            if broker._positions[code].volume <= 0:
                del broker._positions[code]
            elif code in broker._prices:
                broker._positions[code].current_price = broker._prices[code]

        broker._today_sells.clear()
        broker._today_buys.clear()

    def _create_pending_order(
        self,
        broker: Any,
        code: str,
        side: str,
        fill_price: float,
        volume: int,
        asset_type: str,
    ) -> tuple[Order, OrderStateMachine, str]:
        order_id = self._next_order_id(broker)
        ts = datetime.now().isoformat()
        order = Order(
            order_id=order_id,
            code=code,
            asset_type=asset_type,
            side=side,
            price=fill_price,
            volume=volume,
            remaining_volume=volume,
            status=OrderState.PENDING.value,
            created_at=ts,
        )
        sm = OrderStateMachine(order_id=order_id, created_at=ts)
        broker._order_sms[order_id] = sm
        return order, sm, ts

    def _append_order_created(self, broker: Any, order: Order, ts: str, run_date: str) -> None:
        broker._ledger.append(LedgerEvent(
            event_id=self._new_event_id("order_created", order.order_id),
            event_type=EventType.ORDER_CREATED,
            timestamp=ts,
            order_id=order.order_id,
            run_date=run_date,
            symbol=order.code,
            strategy="",
            payload={
                "side": order.side,
                "asset_type": order.asset_type,
                "requested_shares": order.volume,
                "limit_price": order.price,
                "from_state": OrderState.PENDING.value,
                "to_state": OrderState.PENDING.value,
                "reason": f"订单创建: {order.side} {order.code} {order.volume}股 @{order.price:.2f}",
            },
        ))

    def _apply_fill(
        self,
        broker: Any,
        order,
        sm,
        result,
        volume: int,
        side: str,
        code: str,
        run_date: str,
        asset_type: str,
    ) -> None:
        filled_shares = result.filled_shares
        actual_price = result.fill_price
        commission = result.commission
        trade_amount = actual_price * filled_shares
        exchange = broker._exchange_for(asset_type)
        tax = trade_amount * exchange.stamp_tax if side == "sell" and hasattr(exchange, "stamp_tax") else 0
        total_cost = trade_amount + commission + tax
        key = instrument_key(asset_type, code)

        if side == "buy":
            broker._cash -= total_cost
            if key not in broker._positions:
                broker._positions[key] = Position(code=code, volume=0, avg_cost=0.0, asset_type=asset_type)
            pos = broker._positions[key]
            total_basis = pos.avg_cost * pos.volume + total_cost
            pos.volume += filled_shares
            pos.avg_cost = total_basis / pos.volume if pos.volume > 0 else 0.0
            pos.current_price = actual_price
            broker._today_buys[key] = broker._today_buys.get(key, 0) + filled_shares
        else:
            broker._cash += trade_amount - commission - tax
            if key in broker._positions:
                broker._positions[key].volume -= filled_shares
                broker._today_sells[key] = broker._today_sells.get(key, 0) + filled_shares

        order.filled_volume = filled_shares
        order.remaining_volume = volume - filled_shares
        order.price = actual_price
        is_full = filled_shares >= volume
        self._transition_order(
            broker,
            sm,
            order,
            OrderState.FILLED if is_full else OrderState.PARTIAL_FILLED,
            reason=f"{'全部' if is_full else '部分'}成交: {filled_shares}/{volume}股 @{actual_price:.2f}",
            run_date=run_date,
            code=code,
            metadata={
                "fill_price": actual_price,
                "filled_shares": filled_shares,
                "requested": volume,
                "commission": commission,
                "side": side,
                "asset_type": asset_type,
            },
        )

    def _next_order_id(self, broker: Any) -> str:
        broker._order_counter += 1
        return f"PAPER_{broker._order_counter:06d}"

    def _new_event_id(self, prefix: str, order_id: str) -> str:
        import uuid

        return f"{prefix}:{order_id}:{uuid.uuid4().hex[:8]}"

    def _find_order(self, broker: Any, order_id: str) -> Order | None:
        for order in broker._orders:
            if order.order_id == order_id:
                return order
        return None

    def _transition_order(
        self,
        broker: Any,
        sm: OrderStateMachine,
        order: Order,
        to_state: OrderState,
        reason: str = "",
        run_date: str = "",
        code: str = "",
        metadata: dict | None = None,
    ) -> None:
        try:
            transition = sm.transition(to_state, reason=reason, metadata=metadata)
        except InvalidTransition:
            return

        order.status = to_state.value
        order.status_history.append({
            "timestamp": transition.timestamp,
            "from_state": transition.from_state.value,
            "to_state": transition.to_state.value,
            "reason": transition.reason,
        })

        prior_events = broker._ledger.events_for_order(sm.order_id)
        parent_event_id = prior_events[-1].event_id if prior_events else ""
        broker._ledger.append(LedgerEvent(
            event_id=self._new_event_id(transition.event_type, sm.order_id),
            event_type=EventType(transition.event_type),
            timestamp=transition.timestamp,
            parent_event_id=parent_event_id,
            order_id=sm.order_id,
            run_date=run_date,
            symbol=code,
            strategy="",
            payload={
                "from_state": transition.from_state.value,
                "to_state": transition.to_state.value,
                "reason": transition.reason,
                "asset_type": order.asset_type,
                **(metadata or {}),
            },
        ))
