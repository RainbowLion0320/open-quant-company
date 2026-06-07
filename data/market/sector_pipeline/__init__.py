"""Modular sector snapshot pipeline."""
from __future__ import annotations

import pandas as pd

from data.storage.datahub import DataHub
from data.market.sector_pipeline import exposure as _exposure
from data.market.sector_pipeline import membership as _membership
from data.market.sector_pipeline import performance as _performance
from data.market.sector_pipeline import signals as _signals

SW_INDUSTRIES = _membership.SW_INDUSTRIES


def _sync_sector_constants() -> None:
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
    "build_all",
    "build_exposure",
    "build_membership",
    "build_sector_performance",
    "build_signal_aggregation",
]
