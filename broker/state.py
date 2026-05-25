"""Serializable state model for PaperBroker.

Persistence and API layers should exchange this value object with PaperBroker
instead of reaching into broker private fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PaperBrokerState:
    """PaperBroker state that can be restored from and saved to storage."""

    cash: float = 1_000_000.0
    frozen_cash: float = 0.0
    peak_equity: float = 1_000_000.0
    positions: Dict[str, dict] = field(default_factory=dict)
    order_counter: int = 0
    updated_at: str = ""
