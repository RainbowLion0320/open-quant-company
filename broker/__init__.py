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

用法:
  from broker import PaperBroker

  broker = PaperBroker(initial_cash=100000, commission_rate=0.00081)
  broker.submit_order("000001", price=12.5, volume=100, side="buy")
  positions = broker.get_positions()
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime


class OrderStatus:
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


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
    side: str = ""  # buy/sell
    price: float = 0.0
    volume: int = 0
    filled_volume: int = 0
    status: str = OrderStatus.PENDING
    created_at: str = ""


class Broker(ABC):
    """券商抽象接口"""

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """获取当前持仓"""
        pass

    @abstractmethod
    def get_balance(self) -> Account:
        """获取账户资金"""
        pass

    @abstractmethod
    def submit_order(self, code: str, price: float, volume: int, side: str) -> str:
        """
        提交订单
        :param code: 股票代码 (6位)
        :param price: 委托价格
        :param volume: 数量(股)
        :param side: buy/sell
        :return: order_id
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        pass

    @abstractmethod
    def get_orders(self) -> List[Order]:
        """获取当日订单"""
        pass

    @abstractmethod
    def get_today_trades(self) -> List[Order]:
        """获取当日成交"""
        pass


class PaperBroker(Broker):
    """
    模拟券商 — 本地撮合, 无任何外部依赖

    支持:
      - 限价单 (FIX_PRICE), 市价单默认以当前价成交
      - 佣金: 自定义费率 (默认0.081% = A股完整买卖成本)
      - T+1 限制 (当日买不可当日卖)
      - 涨停/跌停限制
      - ★ RiskManager 预检 (Phase 4.3)
    """

    def __init__(
        self,
        initial_cash: float = 1_000_000,
        commission_rate: float = 0.00081,
        stamp_duty: float = 0.0005,
        t_plus_1: bool = True,
        enable_risk: bool = True,
    ):
        self._cash = initial_cash
        self._frozen_cash = 0.0
        self._positions: Dict[str, Position] = {}
        self._orders: List[Order] = []
        self._order_counter = 0
        self._today_sells: Dict[str, int] = {}
        self._today_buys: Dict[str, int] = {}
        self._peak_equity = initial_cash

        self.commission_rate = commission_rate
        self.stamp_duty = stamp_duty
        self.t_plus_1 = t_plus_1
        self._prices: Dict[str, float] = {}

        # ★ Risk Manager
        self._risk_mgr = None
        if enable_risk:
            from broker.risk import RiskManager
            self._risk_mgr = RiskManager()

    def set_prices(self, prices: Dict[str, float]):
        """设置当前行情 (策略需在调用下单前设置)"""
        self._prices.update(prices)
        # ★ 同步更新持仓现价，否则 market_value 始终为 0
        for code, price in prices.items():
            if code in self._positions:
                self._positions[code].current_price = price

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"PAPER_{self._order_counter:06d}"

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
        # 成交价确定。市价单必须先解析出价格，否则风控无法按真实订单金额预检。
        if price <= 0:
            price = self._prices.get(code, 0)
            if price <= 0:
                return f"无行情: {code}"

        # ★ Risk pre-check (Phase 4.3)
        if self._risk_mgr and side == "buy":
            balance = self.get_balance()
            portfolio = {
                "total_equity": balance.total_asset,
                "total_exposure": balance.market_value,
                "peak_equity": self._peak_equity,
                "positions": {
                    c: {"market_value": p.market_value}
                    for c, p in self._positions.items() if p.volume > 0
                },
            }
            amount = price * volume
            passed, results = self._risk_mgr.check_order(code, amount, portfolio)
            if not passed:
                failed = [r for r in results if not r.passed]
                reasons = "; ".join(r.reason for r in failed)
                return f"风控拒绝: {reasons}"

        # 卖出检查：任何模式下都不能卖超过可用持仓；T+1 模式需扣除当日买入。
        if side == "sell":
            pos = self._positions.get(code)
            bought_today = self._today_buys.get(code, 0) if self.t_plus_1 else 0
            available = max(0, (pos.volume if pos else 0) - bought_today)
            if volume > available:
                volume = available
                if volume <= 0:
                    if self.t_plus_1 and bought_today:
                        return f"T+1限制: {code} 当日买入不可卖出"
                    return f"持仓不足: {code}"

        order_id = self._next_order_id()
        order = Order(
            order_id=order_id,
            code=code,
            side=side,
            price=price,
            volume=volume,
            filled_volume=volume,  # 模拟立即成交
            status=OrderStatus.FILLED,
            created_at=datetime.now().isoformat(),
        )

        # 计算成本
        trade_amount = price * volume
        commission = trade_amount * self.commission_rate
        tax = trade_amount * self.stamp_duty if side == "sell" else 0
        total_cost = trade_amount + commission + tax

        if side == "buy":
            if total_cost > self._cash:
                # 资金不足, 按可用资金计算最大可买
                max_vol = int(self._cash / (price * (1 + self.commission_rate)) / 100) * 100
                if max_vol <= 0:
                    order.status = OrderStatus.REJECTED
                    order.filled_volume = 0
                    self._orders.append(order)
                    return "资金不足"
                volume = max_vol
                total_cost = price * volume * (1 + self.commission_rate)
                order.volume = volume
                order.filled_volume = volume

            self._cash -= total_cost
            if code not in self._positions:
                self._positions[code] = Position(code=code, volume=0, avg_cost=0)
            pos = self._positions[code]
            total_cost_basis = pos.avg_cost * pos.volume + price * volume
            pos.volume += volume
            pos.avg_cost = total_cost_basis / pos.volume if pos.volume > 0 else 0
            pos.current_price = price  # 默认以成交价标记现价
            self._today_buys[code] = self._today_buys.get(code, 0) + volume

        else:  # sell
            self._cash += trade_amount - commission - tax
            if code in self._positions:
                self._positions[code].volume -= volume
                self._today_sells[code] = self._today_sells.get(code, 0) + volume

        self._orders.append(order)

        # ★ Record order for daily limit tracking
        if self._risk_mgr and side == "buy":
            self._risk_mgr.record_order()

        # ★ Update peak equity
        balance = self.get_balance()
        if balance.total_asset > self._peak_equity:
            self._peak_equity = balance.total_asset

        return order_id

    def cancel_order(self, order_id: str) -> bool:
        for o in self._orders:
            if o.order_id == order_id and o.status == OrderStatus.PENDING:
                o.status = OrderStatus.CANCELLED
                return True
        return False

    def get_orders(self) -> List[Order]:
        return self._orders

    def get_today_trades(self) -> List[Order]:
        return [o for o in self._orders if o.status == OrderStatus.FILLED]

    # ── 日末结算 ──

    def end_of_day(self):
        """日末清理: 更新持仓市值, 重置T+1计数"""
        for code in list(self._positions):
            if self._positions[code].volume <= 0:
                del self._positions[code]
            elif code in self._prices:
                self._positions[code].current_price = self._prices[code]
        self._today_sells.clear()
        self._today_buys.clear()

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
