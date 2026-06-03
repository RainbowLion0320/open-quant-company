"""Compatibility facade for broker interfaces and the paper broker."""
from __future__ import annotations

from broker.base import Broker
from broker.models import Account, Order, Position
from broker.paper_core import PaperBroker

__all__ = [
    "Account",
    "Broker",
    "Order",
    "PaperBroker",
    "Position",
]
