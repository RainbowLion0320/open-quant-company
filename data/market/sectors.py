"""Compatibility facade for the modular sector snapshot pipeline."""
from __future__ import annotations

import pandas as pd

from data.storage.datahub import DataHub
from data.market.sector_pipeline import exposure as _exposure
from data.market.sector_pipeline import membership as _membership
from data.market.sector_pipeline import performance as _performance
from data.market.sector_pipeline import signals as _signals
from data.market.sector_pipeline.amounts import (
    _aggregate_amount_metrics,
    _amount_col,
    _amount_metrics,
    _amount_series,
    _empty_amount_metrics,
    _normalize_date_series,
    _normalize_return_series,
)
from data.market.sector_pipeline.exposure import _latest_market_value, _load_position_snapshot
from data.market.sector_pipeline.membership import _canonical_sector_name, _snapshot_path, _store
from data.market.sector_pipeline.performance import _build_proxy_returns, _empty_sector_row, _load_sector_index_returns, _period_return


SW_INDUSTRIES = _membership.SW_INDUSTRIES


def _sync_sector_constants() -> None:
    """Keep monkeypatched facade constants visible to modular builders."""
    _membership.SW_INDUSTRIES = SW_INDUSTRIES
    _performance.SW_INDUSTRIES = SW_INDUSTRIES


def build_membership(hub: DataHub | None = None) -> pd.DataFrame:
    _sync_sector_constants()
    return _membership.build_membership(hub)


def build_sector_performance(hub: DataHub | None = None, lookback_days: int = 120) -> pd.DataFrame:
    _sync_sector_constants()
    return _performance.build_sector_performance(hub, lookback_days=lookback_days)


def build_signal_aggregation(hub: DataHub | None = None) -> pd.DataFrame:
    return _signals.build_signal_aggregation(hub)


def build_exposure(hub: DataHub | None = None) -> pd.DataFrame:
    return _exposure.build_exposure(hub)


def build_all(hub: DataHub | None = None) -> dict:
    """Run all sector snapshot builders. Returns summary dict."""
    hub = hub or DataHub()
    results = {}
    for name, builder in [
        ("membership", build_membership),
        ("performance", build_sector_performance),
        ("signals", build_signal_aggregation),
        ("exposure", build_exposure),
    ]:
        try:
            df = builder(hub)
            results[name] = {"status": "ok", "rows": len(df)}
        except Exception as exc:
            results[name] = {"status": "error", "message": str(exc)[:200]}
    return results


__all__ = [
    "SW_INDUSTRIES",
    "_aggregate_amount_metrics",
    "_amount_col",
    "_amount_metrics",
    "_amount_series",
    "_build_proxy_returns",
    "_canonical_sector_name",
    "_empty_amount_metrics",
    "_empty_sector_row",
    "_latest_market_value",
    "_load_position_snapshot",
    "_load_sector_index_returns",
    "_normalize_date_series",
    "_normalize_return_series",
    "_period_return",
    "_snapshot_path",
    "_store",
    "build_all",
    "build_exposure",
    "build_membership",
    "build_sector_performance",
    "build_signal_aggregation",
]
