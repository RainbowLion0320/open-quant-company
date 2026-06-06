"""
Multi-Asset Architecture — Package Init

Usage:
  from data.market.assets import get_asset_registry
  registry = get_asset_registry()
  
  # Register adapters
  from data.market.assets.stock import StockAsset
  registry.register(StockAsset(store_root="var/store"))
  
  # Use
  stock = registry.get("stock")
  data = stock.fetch_daily("000001", "2024-01-01", "2024-12-31")
"""
from data.market.assets.base import (
    AssetAdapter,
    AssetRegistry,
    get_asset_registry,
)

__all__ = [
    "AssetAdapter",
    "AssetRegistry",
    "get_asset_registry",
]
