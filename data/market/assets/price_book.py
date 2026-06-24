"""Multi-asset price panel helpers.

The helpers are deliberately fail-closed: a missing adapter, empty universe, or
empty/stale fetch produces blockers instead of synthetic prices.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from data.market.assets.base import get_asset_registry
from data.market.assets.contracts import AssetPricePanel
from data.market.assets.overview import ASSET_ADAPTERS, _load_class


def get_asset_price_panel(
    asset_type: str,
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
) -> AssetPricePanel:
    registry = get_asset_registry()
    adapter = registry.get(asset_type)
    if adapter is None and asset_type in ASSET_ADAPTERS:
        try:
            adapter = _load_class(ASSET_ADAPTERS[asset_type])()
            registry.register(adapter)
        except Exception:
            adapter = None
    requested = [str(symbol) for symbol in symbols if str(symbol).strip()]
    if adapter is None:
        return AssetPricePanel(
            asset_type=asset_type,
            prices=pd.DataFrame(),
            symbols=requested,
            start_date=start_date,
            end_date=end_date,
            status="blocked",
            blockers=[f"missing_asset_adapter:{asset_type}"],
        )
    if not requested:
        return AssetPricePanel(
            asset_type=asset_type,
            prices=pd.DataFrame(),
            start_date=start_date,
            end_date=end_date,
            status="blocked",
            blockers=["empty_universe"],
            provenance=adapter.get_data_source(),
        )

    columns: dict[str, pd.Series] = {}
    blockers: list[str] = []
    for symbol in requested:
        df = adapter.fetch_daily(symbol, start_date, end_date)
        if df is None or df.empty or "close" not in df.columns:
            blockers.append(f"missing_price:{asset_type}:{symbol}")
            continue
        frame = df.copy()
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
            frame = frame.dropna(subset=["date"]).set_index("date")
        else:
            frame.index = pd.to_datetime(frame.index, errors="coerce")
            frame = frame[frame.index.notna()]
        close = pd.to_numeric(frame["close"], errors="coerce").dropna()
        close = close[close > 0]
        if close.empty:
            blockers.append(f"empty_close:{asset_type}:{symbol}")
            continue
        columns[symbol] = close

    prices = pd.DataFrame(columns).sort_index()
    status = "ok" if not blockers and not prices.empty else "blocked"
    if prices.empty and "empty_price_panel" not in blockers:
        blockers.append("empty_price_panel")
    return AssetPricePanel(
        asset_type=asset_type,
        prices=prices,
        symbols=list(columns.keys()),
        start_date=start_date,
        end_date=end_date,
        status=status,
        blockers=blockers,
        provenance=adapter.get_data_source(),
    )


def get_multi_asset_price_book(
    requests: dict[str, Iterable[str]],
    start_date: str,
    end_date: str,
) -> dict[str, AssetPricePanel]:
    return {
        asset_type: get_asset_price_panel(asset_type, symbols, start_date, end_date)
        for asset_type, symbols in requests.items()
    }
