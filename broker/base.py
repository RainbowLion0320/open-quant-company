"""Broker interface shared by paper and future live adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod

from broker.models import Account, Order, Position


class Broker(ABC):
    """Broker abstraction consumed by strategies and execution scripts."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    def get_balance(self) -> Account:
        ...

    @abstractmethod
    def submit_order(self, code: str, price: float, volume: int, side: str) -> str:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def get_orders(self) -> list[Order]:
        ...

    @abstractmethod
    def get_today_trades(self) -> list[Order]:
        ...
