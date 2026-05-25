"""
券商接口 — 借鉴 easytrader 的 facade pattern

设计理念:
  Broker 抽象接口 → PaperBroker (模拟) / MiniQMTBroker (实盘, Phase 3)
  所有策略代码只依赖 Broker 接口, 不关心后端是模拟还是实盘

接口:
  get_positions()   → 持仓
  get_balance()     → 资金
  submit_order()    → 下单
  cancel_order()    → 撤单
  get_orders()      → 当日订单

Order lifecycle (P1-7 event-sourced state machine):
  PENDING → PARTIAL_FILLED → FILLED | REJECTED | CANCELLED | EXPIRED
  Every state transition is recorded as an immutable event in the EventLedger.

用法:
  from broker import PaperBroker

  broker = PaperBroker(initial_cash=100000, commission_rate=0.00081)
  broker.submit_order("000001", price=12.5, volume=100, side="buy")
  positions = broker.get_positions()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional

from broker.order_sm import (
    OrderState,
    OrderStateMachine,
    StateTransition,
    InvalidTransition,
)
from broker.fill_models import (
    SlippageModel,
    FillModel,
    ImmediateFill,
    LimitUpDownAwareFill,
    CompositeFill,
    NoSlippage,
    FixedBpsSlippage,
)
from broker.matcher import MatchingEngine, MatchContext
from broker.ledger import EventLedger, LedgerEvent, EventType
from broker.exchange import AShareExchange


# ── Data Classes ──


@dataclass
class Position:
    code: str
    name: str = ""
    volume: int = 0
    avg_cost: float = 0.0
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.volume * self.current_price

    @property
    def cost_value(self) -> float:
        return self.volume * self.avg_cost

    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_value

    @property
    def pnl_pct(self) -> float:
        return self.pnl / self.cost_value if self.cost_value > 0 else 0


@dataclass
class Account:
    total_asset: float = 0.0
    cash: float = 0.0
    frozen_cash: float = 0.0
    market_value: float = 0.0


@dataclass
class Order:
    order_id: str = ""
    code: str = ""
    side: str = ""           # buy/sell
    price: float = 0.0       # limit price (0 = market)
    volume: int = 0          # requested shares
    filled_volume: int = 0   # cumulative filled
    remaining_volume: int = 0  # still pending
    status: str = ""         # current state as string
    created_at: str = ""
    # P1-7: full lifecycle tracking
    status_history: list[dict] = field(default_factory=list)
    # status_history entries: {timestamp, from_state, to_state, reason}


# ── Broker ABC ──


class Broker(ABC):
    """券商抽象接口"""

    @abstractmethod
    def get_positions(self) -> List[Position]:
        ...

    @abstractmethod
    def get_balance(self) -> Account:
        ...

    @abstractmethod
    def submit_order(self, code: str, price: float, volume: int, side: str) -> str:
        """
        提交订单
        :param code: 股票代码 (6位)
        :param price: 委托价格 (0=市价)
        :param volume: 数量(股)
        :param side: buy/sell
        :return: order_id on success, error message on failure
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def get_orders(self) -> List[Order]:
        ...

    @abstractmethod
    def get_today_trades(self) -> List[Order]:
        ...


# ── PaperBroker ──


class PaperBroker(Broker):
    """
    模拟券商 — 本地撮合, 无任何外部依赖

    P1-7: Full event-sourced order lifecycle.
      - OrderStateMachine enforces valid state transitions
      - MatchingEngine uses pluggable fill/slippage models
      - EventLedger records every state change as an immutable event
      - Every fill is traceable back to its signal via ledger.replay()

    支持:
      - 限价单, 市价单默认以当前价成交
      - 部分成交 (via fill model)
      - 佣金: 统一使用 AShareExchange 成本模型
      - T+1 限制
      - 涨停/跌停限制 (via LimitUpDownAwareFill)
      - RiskManager 预检
      - 订单过期 (end_of_day 时未成交订单自动 EXPIRED)
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
        self._positions: Dict[str, Position] = {}
        self._orders: List[Order] = []
        self._order_counter = 0
        self._today_sells: Dict[str, int] = {}
        self._today_buys: Dict[str, int] = {}
        self._peak_equity = initial_cash

        self.t_plus_1 = t_plus_1
        self._prices: Dict[str, float] = {}

        # P1-7: Event-sourced order lifecycle
        self._order_sms: Dict[str, OrderStateMachine] = {}
        self._ledger = ledger or EventLedger()
        self._exchange = AShareExchange(
            commission=commission_rate,
            stamp_tax=stamp_duty,
        )

        # Fill model chain: limit-up/down check → immediate fill with optional slippage
        slippage = slippage_model or NoSlippage()
        self._fill_model = fill_model or CompositeFill([
            LimitUpDownAwareFill(slippage=slippage),
            ImmediateFill(slippage=slippage),
        ])
        self._matcher = MatchingEngine(
            exchange=self._exchange,
            fill_model=self._fill_model,
        )

        # Risk Manager
        self._risk_mgr = None
        if enable_risk:
            from broker.risk import RiskManager
            self._risk_mgr = RiskManager()

    # ── public properties ──

    @property
    def ledger(self) -> EventLedger:
        return self._ledger

    @property
    def matcher(self) -> MatchingEngine:
        return self._matcher

    @property
    def order_states(self) -> Dict[str, OrderStateMachine]:
        return self._order_sms

    # ── price management ──

    def set_prices(self, prices: Dict[str, float]):
        """设置当前行情 (策略需在调用下单前设置)"""
        self._prices.update(prices)
        for code, price in prices.items():
            if code in self._positions:
                self._positions[code].current_price = price

    def _resolve_price(self, code: str, price: float) -> float:
        """Resolve a market order price. Returns 0 if no price available."""
        if price > 0:
            return price
        return self._prices.get(code, 0)

    # ── Broker 接口实现 ──

    def get_positions(self) -> List[Position]:
        return [p for p in self._positions.values() if p.volume > 0]

    def get_balance(self) -> Account:
        mv = sum(p.market_value for p in self._positions.values())
        return Account(
            total_asset=self._cash + self._frozen_cash + mv,
            cash=self._cash,
            frozen_cash=self._frozen_cash,
            market_value=mv,
        )

    def submit_order(self, code: str, price: float, volume: int, side: str) -> str:
        """
        提交订单 — 完整事件溯源流程.

        1. 风控预检 → 2. 创建 PENDING 订单 + 状态机 → 3. 撮合引擎匹配
        → 4. 状态转换 + 事件入账 → 5. 资金/持仓更新 → 6. 返回 order_id
        """
        run_date = datetime.now().strftime("%Y-%m-%d")

        # Resolve market price
        fill_price = self._resolve_price(code, price)
        if fill_price <= 0:
            return f"无行情: {code}"

        balance = self.get_balance()

        # ── Risk pre-check ──
        if self._risk_mgr and side == "buy":
            portfolio = {
                "total_equity": balance.total_asset,
                "total_exposure": balance.market_value,
                "peak_equity": self._peak_equity,
                "positions": {
                    c: {"market_value": p.market_value}
                    for c, p in self._positions.items() if p.volume > 0
                },
            }
            amount = fill_price * volume
            passed, results = self._risk_mgr.check_order(code, amount, portfolio)
            if not passed:
                failed = [r for r in results if not r.passed]
                reasons = "; ".join(r.reason for r in failed)
                return f"风控拒绝: {reasons}"

        # ── Affordability check (buy) ──
        if side == "buy":
            can, max_shares = self._matcher.can_afford(fill_price, volume, self._cash, side)
            if not can:
                if max_shares <= 0:
                    return "资金不足"
                volume = max_shares

        # ── Sellable check (sell) ──
        if side == "sell":
            pos = self._positions.get(code)
            holdings = pos.volume if pos else 0
            bought_today = self._today_buys.get(code, 0) if self.t_plus_1 else 0
            available = max(0, holdings - bought_today)
            if available <= 0:
                if self.t_plus_1 and bought_today > 0:
                    return f"T+1限制: {code} 当日买入不可卖出"
                return f"持仓不足: {code}"
            volume = min(volume, available)

        if volume <= 0:
            return "无可执行数量"

        # ── Create order + state machine ──
        order_id = self._next_order_id()
        ts = datetime.now().isoformat()

        order = Order(
            order_id=order_id,
            code=code,
            side=side,
            price=fill_price,
            volume=volume,
            filled_volume=0,
            remaining_volume=volume,
            status=OrderState.PENDING.value,
            created_at=ts,
        )

        sm = OrderStateMachine(order_id=order_id, created_at=ts)
        self._order_sms[order_id] = sm

        # Emit ORDER_CREATED event
        create_event = LedgerEvent(
            event_id=self._new_event_id("order_created", order_id),
            event_type=EventType.ORDER_CREATED,
            timestamp=ts,
            order_id=order_id,
            run_date=run_date,
            symbol=code,
            strategy="",
            payload={
                "side": side,
                "requested_shares": volume,
                "limit_price": fill_price,
                "from_state": OrderState.PENDING.value,
                "to_state": OrderState.PENDING.value,
                "reason": f"订单创建: {side} {code} {volume}股 @{fill_price:.2f}",
            },
        )
        self._ledger.append(create_event)

        # ── Match via MatchingEngine ──
        pos = self._positions.get(code)
        prev_close = pos.avg_cost if pos and pos.avg_cost > 0 else fill_price

        match_ctx = MatchContext(
            symbol=code,
            side=side,
            requested_shares=volume,
            market_price=fill_price,
            prev_close=prev_close,
            available_cash=self._cash,
            current_holdings=pos.volume if pos else 0,
            t_plus_1_bought_today=self._today_buys.get(code, 0) if self.t_plus_1 else 0,
        )
        result = self._matcher.match(match_ctx)

        # ── Process match result ──
        if result.status == "rejected":
            # Transition to REJECTED
            self._transition_order(
                sm, order, OrderState.REJECTED,
                reason=result.reason,
                run_date=run_date, code=code,
                metadata={"fill_price": fill_price, "requested": volume},
            )
            self._orders.append(order)
            return result.reason if result.reason else f"订单被拒绝: {code}"

        # Filled or partial_filled
        filled_shares = result.filled_shares
        actual_price = result.fill_price
        commission = result.commission

        is_full = (filled_shares >= volume)
        new_state = OrderState.FILLED if is_full else OrderState.PARTIAL_FILLED

        # Calculate cost
        trade_amount = actual_price * filled_shares
        tax = trade_amount * self._exchange.stamp_tax if (side == "sell" and hasattr(self._exchange, 'stamp_tax')) else 0
        total_cost = trade_amount + commission + tax

        # Update cash & positions
        if side == "buy":
            self._cash -= total_cost
            if code not in self._positions:
                self._positions[code] = Position(code=code, volume=0, avg_cost=0.0)
            pos = self._positions[code]
            total_basis = pos.avg_cost * pos.volume + total_cost
            pos.volume += filled_shares
            pos.avg_cost = total_basis / pos.volume if pos.volume > 0 else 0.0
            pos.current_price = actual_price
            self._today_buys[code] = self._today_buys.get(code, 0) + filled_shares
        else:  # sell
            self._cash += trade_amount - commission - tax
            if code in self._positions:
                self._positions[code].volume -= filled_shares
                self._today_sells[code] = self._today_sells.get(code, 0) + filled_shares

        # Update order
        order.filled_volume = filled_shares
        order.remaining_volume = volume - filled_shares
        order.price = actual_price

        # Transition state machine
        self._transition_order(
            sm, order, new_state,
            reason=f"{'全部' if is_full else '部分'}成交: {filled_shares}/{volume}股 @{actual_price:.2f}",
            run_date=run_date, code=code,
            metadata={
                "fill_price": actual_price,
                "filled_shares": filled_shares,
                "requested": volume,
                "commission": commission,
                "side": side,
            },
        )

        self._orders.append(order)

        # Track for risk manager
        if self._risk_mgr:
            self._risk_mgr.record_order()

        # Update peak equity
        balance = self.get_balance()
        if balance.total_asset > self._peak_equity:
            self._peak_equity = balance.total_asset

        return order_id

    def cancel_order(self, order_id: str) -> bool:
        sm = self._order_sms.get(order_id)
        if not sm:
            return False
        if not sm.can_be_cancelled:
            return False

        for o in self._orders:
            if o.order_id == order_id:
                self._transition_order(
                    sm, o, OrderState.CANCELLED,
                    reason="用户主动撤单",
                    run_date=datetime.now().strftime("%Y-%m-%d"),
                    code=o.code,
                )
                return True
        return False

    def get_orders(self) -> List[Order]:
        return self._orders

    def get_today_trades(self) -> List[Order]:
        return [o for o in self._orders if o.status == OrderState.FILLED.value]

    # ── 日末结算 ──

    def end_of_day(self):
        """日末清理: 过期未成交订单, 重置T+1计数, 更新持仓市值"""
        run_date = datetime.now().strftime("%Y-%m-%d")

        # Expire unfilled orders
        for order_id, sm in list(self._order_sms.items()):
            if sm.is_active:
                order = self._find_order(order_id)
                if order and order.remaining_volume > 0:
                    self._transition_order(
                        sm, order, OrderState.EXPIRED,
                        reason=f"收盘未成交: {order.remaining_volume}股剩余",
                        run_date=run_date, code=order.code,
                        metadata={"remaining": order.remaining_volume},
                    )

        # Clean up empty positions
        for code in list(self._positions):
            if self._positions[code].volume <= 0:
                del self._positions[code]
            elif code in self._prices:
                self._positions[code].current_price = self._prices[code]

        self._today_sells.clear()
        self._today_buys.clear()

    # ── Internal helpers ──

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"PAPER_{self._order_counter:06d}"

    def _new_event_id(self, prefix: str, order_id: str) -> str:
        import uuid
        short = uuid.uuid4().hex[:8]
        return f"{prefix}:{order_id}:{short}"

    def _find_order(self, order_id: str) -> Order | None:
        for o in self._orders:
            if o.order_id == order_id:
                return o
        return None

    def _transition_order(
        self,
        sm: OrderStateMachine,
        order: Order,
        to_state: OrderState,
        reason: str = "",
        run_date: str = "",
        code: str = "",
        metadata: dict | None = None,
    ):
        """Transition an order's state machine and record the event in the ledger."""
        try:
            t = sm.transition(to_state, reason=reason, metadata=metadata)
        except InvalidTransition:
            return  # already terminal, skip

        # Update Order dataclass for public API compatibility
        order.status = to_state.value
        order.status_history.append({
            "timestamp": t.timestamp,
            "from_state": t.from_state.value,
            "to_state": t.to_state.value,
            "reason": t.reason,
        })

        # Record event in ledger
        prior_events = self._ledger.events_for_order(sm.order_id)
        parent_event_id = prior_events[-1].event_id if prior_events else ""
        event = LedgerEvent(
            event_id=self._new_event_id(t.event_type, sm.order_id),
            event_type=EventType(t.event_type),
            timestamp=t.timestamp,
            parent_event_id=parent_event_id,
            order_id=sm.order_id,
            run_date=run_date,
            symbol=code,
            strategy="",
            payload={
                "from_state": t.from_state.value,
                "to_state": t.to_state.value,
                "reason": t.reason,
                **(metadata or {}),
            },
        )
        self._ledger.append(event)

    # ── Summary ──

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
            for p in sorted(positions, key=lambda x: -x.market_value)[:10]:
                lines.append(
                    f"  {p.code} x{p.volume}  "
                    f"成本{p.avg_cost:.2f} 现价{p.current_price:.2f}  "
                    f"盈亏{p.pnl_pct*100:+.1f}%"
                )
        lines.append("══════════════════════════")
        return "\n".join(lines)
