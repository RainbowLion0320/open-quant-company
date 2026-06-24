"""Public broker value objects."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    code: str
    name: str = ""
    volume: int = 0
    avg_cost: float = 0.0
    current_price: float = 0.0
    asset_type: str = "stock"

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
    side: str = ""
    price: float = 0.0
    volume: int = 0
    filled_volume: int = 0
    remaining_volume: int = 0
    status: str = ""
    created_at: str = ""
    status_history: list[dict] = field(default_factory=list)
    asset_type: str = "stock"
