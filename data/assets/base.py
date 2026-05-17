"""
Multi-Asset Architecture — Base Classes

Uniform interface for all asset types (stock, fund, futures, crypto, macro).
Every new asset type implements AssetAdapter and registers in AssetRegistry.

Design principles:
  1. One interface, many adapters — no hardcoded "if stock elif fund"
  2. Parquet store per asset type — data/store/{asset_type}/
  3. Registry-driven — config/settings.yaml → assets section
  4. Production-grade — typed, error-handled, config-driven
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from pathlib import Path
import pandas as pd

from data.datahub import get_datahub


class AssetAdapter(ABC):
    """
    Abstract base for all asset type data adapters.

    Each subclass handles one asset type (stock, fund, futures, crypto, macro).
    The adapter is responsible for:
      - Fetching daily price/OHLCV data
      - Providing the universe of tradable symbols
      - Returning metadata for individual symbols
      - Building PIT features (optional, may be shared)
    """

    # ── Class-level metadata (override in subclass) ──
    asset_type: str = ""       # "stock", "fund", "futures", "crypto", "macro"
    label: str = ""            # "A股股票", "公募基金", etc.
    description: str = ""

    def __init__(self, store_root: Path | str | None = None):
        """
        Args:
            store_root: root of the data store (data/store/)
        """
        self.store_root = Path(store_root) if store_root is not None else get_datahub().store_dir()
        self.asset_dir = self.store_root / self.asset_type
        self.asset_dir.mkdir(parents=True, exist_ok=True)

    # ── Core Interface (must implement) ──

    @abstractmethod
    def fetch_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch daily OHLCV data for a single symbol.

        Returns DataFrame with columns: date, open, high, low, close, volume
        Returns None if symbol not found or data unavailable.
        """
        ...

    @abstractmethod
    def get_universe(self) -> List[str]:
        """
        Return list of all available symbols for this asset type.
        """
        ...

    @abstractmethod
    def get_metadata(self, symbol: str) -> Dict:
        """
        Return metadata dict for a symbol: name, industry, market, etc.
        Returns empty dict if unknown.
        """
        ...

    # ── Optional extensions ──

    def fetch_fundamentals(self, symbol: str) -> Dict:
        """
        Fetch fundamental data (ROE, margins, D/E, etc).
        Override in subclasses that support this.
        """
        return {}

    def fetch_valuation(self, symbol: str, date: Optional[str] = None) -> Dict:
        """
        Fetch valuation data (PE, PB, PS, market cap, etc).
        Override in subclasses that support this.
        """
        return {}

    def fetch_financials(self, symbol: str, date: Optional[str] = None) -> Dict:
        """
        Fetch detailed financial statements data.
        Override in subclasses that support this.
        """
        return {}

    def fetch_factor_data(self, symbol: str, factor_name: str, date: Optional[str] = None) -> Optional[float]:
        """
        Fetch a specific factor value (fund flows, sentiment, etc).
        Override in subclasses that support additional factor dimensions.
        """
        return None

    # ── Store paths ──

    @property
    def signals_dir(self) -> Path:
        d = self.asset_dir / "signals"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def features_dir(self) -> Path:
        d = self.asset_dir / "features"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def daily_dir(self) -> Path:
        d = self.asset_dir / "daily"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def cache_path(self, symbol: str, suffix: str = "parquet") -> Path:
        """Path for symbol-level cache file."""
        return self.daily_dir / f"{symbol}.{suffix}"

    # ── Utility ──

    def __repr__(self) -> str:
        return f"<{self.asset_type}: {self.label}>"


class AssetRegistry:
    """
    Central registry of all asset type adapters.

    Like StrategyRegistry — single source of truth for what asset types exist.
    Assets are registered in config/settings.yaml → assets, then instantiated here.
    """

    def __init__(self):
        self._adapters: Dict[str, AssetAdapter] = {}

    def register(self, adapter: AssetAdapter) -> None:
        """Register an asset adapter."""
        if adapter.asset_type in self._adapters:
            raise ValueError(f"Asset type '{adapter.asset_type}' already registered")
        self._adapters[adapter.asset_type] = adapter

    def get(self, asset_type: str) -> Optional[AssetAdapter]:
        """Get adapter by asset type name."""
        return self._adapters.get(asset_type)

    @property
    def all(self) -> Dict[str, AssetAdapter]:
        return dict(self._adapters)

    @property
    def asset_types(self) -> List[str]:
        return list(self._adapters.keys())

    def get_universe(self, asset_type: str) -> List[str]:
        """Shortcut: get all symbols for a given asset type."""
        adapter = self.get(asset_type)
        return adapter.get_universe() if adapter else []

    def fetch_daily(self, asset_type: str, symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """Shortcut: fetch daily data via the right adapter."""
        adapter = self.get(asset_type)
        return adapter.fetch_daily(symbol, start, end) if adapter else None

    def __repr__(self) -> str:
        types = ", ".join(self._adapters.keys())
        return f"<AssetRegistry: {types}>"


# ── Global singleton ──
_asset_registry: Optional[AssetRegistry] = None


def get_asset_registry() -> AssetRegistry:
    """Get or create the global asset registry singleton."""
    global _asset_registry
    if _asset_registry is None:
        _asset_registry = AssetRegistry()
    return _asset_registry
