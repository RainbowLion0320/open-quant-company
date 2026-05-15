"""
Multi-Asset Architecture — Package Init

Usage:
  from data.assets import get_asset_registry
  registry = get_asset_registry()
  
  # Register adapters
  from data.assets.stock import StockAsset
  registry.register(StockAsset(store_root="data/store"))
  
  # Use
  stock = registry.get("stock")
  data = stock.fetch_daily("000001", "2024-01-01", "2024-12-31")
"""
from data.assets.base import (
    AssetAdapter,
    AssetRegistry,
    get_asset_registry,
)

__all__ = [
    "AssetAdapter",
    "AssetRegistry",
    "get_asset_registry",
]
