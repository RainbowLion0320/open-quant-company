"""Canonical multi-asset contracts.

These value objects are intentionally small.  They make asset identity explicit
without replacing the existing AssetAdapter implementations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CANONICAL_ASSET_TYPES = ("stock", "etf", "bond", "futures", "crypto", "cash")


def normalize_asset_type(value: str | None) -> str:
    asset_type = str(value or "stock").strip().lower()
    return asset_type or "stock"


def instrument_key(asset_type: str | None, symbol: str) -> str:
    """Stable position key.

    Stock keeps the historical plain symbol key to avoid invalidating existing
    PaperBroker and backtest state.  Non-stock assets are namespaced.
    """
    normalized = normalize_asset_type(asset_type)
    clean_symbol = str(symbol or "").strip()
    if normalized == "stock":
        return clean_symbol
    return f"{normalized}:{clean_symbol}"


def split_instrument_key(key: str, default_asset_type: str = "stock") -> tuple[str, str]:
    value = str(key or "").strip()
    if ":" in value:
        asset_type, symbol = value.split(":", 1)
        return normalize_asset_type(asset_type), symbol
    return normalize_asset_type(default_asset_type), value


@dataclass(frozen=True)
class AssetInstrument:
    asset_type: str
    symbol: str
    exchange: str = ""
    name: str = ""
    currency: str = "CNY"
    contract_multiplier: float = 1.0
    min_trade_unit: int = 1
    margin_rate: float = 0.0
    trading_calendar: str = ""
    live_tradable: bool = False
    research_ready: bool = False
    data_source: str = "unknown"
    blockers: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return instrument_key(self.asset_type, self.symbol)


@dataclass(frozen=True)
class AssetUniverse:
    asset_type: str
    instruments: tuple[AssetInstrument, ...] = ()
    blockers: tuple[str, ...] = ()

    @property
    def symbols(self) -> list[str]:
        return [item.symbol for item in self.instruments]


@dataclass
class AssetPricePanel:
    asset_type: str
    prices: Any
    symbols: list[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    status: str = "ok"
    blockers: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.status == "ok" and not self.blockers
