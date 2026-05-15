"""
交易所抽象 — 交易成本、规则、执行模型

借鉴 Qlib Exchange 设计:
  - 分离成本模型与回测引擎
  - 支持多市场 (A股 / 港股 / 期货)
  - 可配置费率

当前实现: AShareExchange (A股)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class TradeResult:
    """单笔交易结果"""
    symbol: str
    side: OrderSide
    shares: int
    price: float
    gross_amount: float      # 成交金额 (price × shares)
    cost: float               # 交易成本
    net_amount: float         # 净金额 (gross + cost, buy为正/cost, sell为正+cost)


class Exchange(ABC):
    """交易所基类"""

    name: str = "base"

    @abstractmethod
    def calc_cost(self, price: float, shares: int, side: OrderSide) -> float:
        """计算单边交易成本"""
        ...

    @abstractmethod
    def can_trade(self, symbol: str) -> bool:
        """检查是否可交易 (停牌/涨跌停/etc)"""
        ...

    def execute_buy(self, symbol: str, price: float, shares: int) -> TradeResult:
        """执行买入"""
        gross = price * shares
        cost = self.calc_cost(price, shares, OrderSide.BUY)
        return TradeResult(
            symbol=symbol, side=OrderSide.BUY, shares=shares,
            price=price, gross_amount=gross, cost=cost,
            net_amount=-(gross + cost),
        )

    def execute_sell(self, symbol: str, price: float, shares: int) -> TradeResult:
        """执行卖出"""
        gross = price * shares
        cost = self.calc_cost(price, shares, OrderSide.SELL)
        return TradeResult(
            symbol=symbol, side=OrderSide.SELL, shares=shares,
            price=price, gross_amount=gross, cost=cost,
            net_amount=gross - cost,
        )


class AShareExchange(Exchange):
    """A股交易所 — 含印花税/佣金/过户费/T+1"""

    name = "ashare"
    asset_type = "stock"

    def __init__(
        self,
        stamp_tax: float = 0.0005,        # 印花税 (卖出单向)
        commission: float = 0.00025,       # 佣金 (双向, 万2.5)
        transfer_fee: float = 0.00001,     # 过户费 (双向, 十万分之一)
        t_plus: int = 1,                   # T+1
        min_commission: float = 5.0,       # 最低佣金 (5元)
        lot_size: int = 100,               # 每手股数
        stamp_tax_sell_only: bool = True,  # 印花税仅卖出
    ):
        self.stamp_tax = stamp_tax
        self.commission = commission
        self.transfer_fee = transfer_fee
        self.t_plus = t_plus
        self.min_commission = min_commission
        self.lot_size = lot_size
        self.stamp_tax_sell_only = stamp_tax_sell_only

    def calc_cost(self, price: float, shares: int, side: OrderSide) -> float:
        """
        计算交易成本。

        A股费率:
          - 印花税: 0.05% (卖出单向)
          - 佣金: 0.025% (双向, 最低5元)
          - 过户费: 0.001% (双向)
        """
        amount = price * shares

        # 佣金 (最低5元)
        comm = max(amount * self.commission, self.min_commission)

        # 过户费
        transfer = amount * self.transfer_fee

        # 印花税 (仅卖出)
        stamp = 0.0
        if side == OrderSide.SELL and self.stamp_tax_sell_only:
            stamp = amount * self.stamp_tax

        return comm + transfer + stamp

    def can_trade(self, symbol: str) -> bool:
        # 简化：假设总是可交易 (实际需要检查停牌/涨跌停)
        return True

    def apply_cost_rate(self, price: float, side: OrderSide) -> float:
        """返回价格乘数: buy 时 >1 (加成本), sell 时 <1 (减成本)."""
        if side == OrderSide.BUY:
            rate = 1.0 + self.commission + self.transfer_fee
        else:
            rate = 1.0 - self.commission - self.transfer_fee - self.stamp_tax
        return max(rate, 0.99)

    @property
    def roundtrip_cost_pct(self) -> float:
        """完整双边交易成本百分比"""
        return (self.commission * 2 + self.transfer_fee * 2 + self.stamp_tax) * 100


class ETFExchange(Exchange):
    """ETF交易所 — T+0, 无印花税, 低佣金, 无涨跌停"""

    name = "etf"
    asset_type = "etf"

    def __init__(
        self,
        commission: float = 0.00005,       # 佣金 (双向, 万0.5)
        min_commission: float = 0.10,       # 最低佣金 (0.1元)
        lot_size: int = 100,
    ):
        self.commission = commission
        self.min_commission = min_commission
        self.lot_size = lot_size

    def calc_cost(self, price: float, shares: int, side: OrderSide) -> float:
        """ETF: 佣金双向, 无印花税, 无过户费"""
        amount = price * shares
        return max(amount * self.commission, self.min_commission)

    def can_trade(self, symbol: str) -> bool:
        return True

    def apply_cost_rate(self, price: float, side: OrderSide) -> float:
        if side == OrderSide.BUY:
            return 1.0 + self.commission
        else:
            return 1.0 - self.commission

    @property
    def roundtrip_cost_pct(self) -> float:
        return self.commission * 2 * 100


class MultiAssetExchange:
    """多资产交易所 — 按 asset_type 分发到对应 Exchange"""

    def __init__(self):
        self._exchanges: dict = {}

    def register(self, asset_type: str, exchange: Exchange) -> None:
        self._exchanges[asset_type] = exchange

    def get(self, asset_type: str) -> Exchange:
        if asset_type not in self._exchanges:
            raise KeyError(f"No exchange registered for asset type: {asset_type}")
        return self._exchanges[asset_type]

    def calc_cost(self, asset_type: str, price: float, shares: int, side: OrderSide) -> float:
        return self.get(asset_type).calc_cost(price, shares, side)

    @property
    def all_types(self) -> list:
        return list(self._exchanges.keys())

    def __repr__(self) -> str:
        types = ", ".join(f"{k}({v.roundtrip_cost_pct:.4f}%)" for k, v in self._exchanges.items())
        return f"<MultiAssetExchange: {types}>"
