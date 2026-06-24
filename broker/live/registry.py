"""Live broker routing by asset type.

The registry records which adapter family owns each asset type.  It does not
pretend unsupported assets are live-tradable; unconfigured adapters return
stable blockers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class LiveAdapterStatus:
    asset_type: str
    adapter: str
    status: str
    blockers: tuple[str, ...] = ()
    paper_fallback: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LiveAdapterRegistry:
    """Fail-closed asset → live adapter registry."""

    def __init__(self, statuses: dict[str, LiveAdapterStatus] | None = None):
        self._statuses = dict(statuses or default_live_adapter_statuses())

    def status_for(self, asset_type: str) -> LiveAdapterStatus:
        return self._statuses.get(
            asset_type,
            LiveAdapterStatus(
                asset_type=asset_type,
                adapter="unconfigured",
                status="blocked",
                blockers=("live_adapter_not_configured",),
            ),
        )

    def all(self) -> dict[str, LiveAdapterStatus]:
        return dict(self._statuses)


def default_live_adapter_statuses() -> dict[str, LiveAdapterStatus]:
    return {
        "stock": LiveAdapterStatus("stock", "miniqmt", "configured_contract", blockers=("live_disabled_until_ready",)),
        "etf": LiveAdapterStatus("etf", "miniqmt", "configured_contract", blockers=("live_disabled_until_ready",)),
        "bond": LiveAdapterStatus(
            "bond",
            "miniqmt",
            "conditional",
            blockers=("convertible_bond_only", "treasury_proxy_not_tradable"),
        ),
        "futures": LiveAdapterStatus(
            "futures",
            "ctp_or_configured_futures_gateway",
            "blocked",
            blockers=("live_adapter_not_configured",),
        ),
        "crypto": LiveAdapterStatus(
            "crypto",
            "ccxt_compatible_exchange",
            "blocked",
            blockers=("live_adapter_not_configured", "exchange_secret_missing"),
        ),
        "cash": LiveAdapterStatus("cash", "not_tradable", "not_applicable", blockers=("cash_is_allocation_bucket",)),
    }


def live_adapter_registry() -> LiveAdapterRegistry:
    return LiveAdapterRegistry()
