"""Asset coverage overview shared by CLI and Web API."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.settings import get_section
from broker.live.registry import live_adapter_registry


ASSET_ADAPTERS = {
    "stock": "data.market.assets.stock:StockAsset",
    "etf": "data.market.assets.etf:ETFAsset",
    "bond": "data.market.assets.bond:BondAsset",
    "futures": "data.market.assets.futures:FuturesAsset",
    "crypto": "data.market.assets.crypto:CryptoAsset",
}


def _load_class(path: str):
    module_name, class_name = path.split(":", 1)
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


def _safe_universe_size(adapter: Any, enabled: bool) -> int:
    if not enabled:
        return 0
    try:
        return len(adapter.get_universe())
    except Exception:
        return 0


def asset_overview_items(asset_types: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Return configured asset coverage, provenance and readiness.

    The `enabled` flag is sourced from `config/settings.yaml`; adapter class
    metadata only describes capability, not whether the asset is active.
    """
    cfg = get_section("assets", {}) or {}
    keys = list(asset_types or ASSET_ADAPTERS.keys())
    items: list[dict[str, Any]] = []
    live_registry = live_adapter_registry()

    for asset_type in keys:
        asset_cfg = cfg.get(asset_type, {}) or {}
        enabled = bool(asset_cfg.get("enabled", False))
        label = str(asset_cfg.get("label", asset_type))
        adapter_path = ASSET_ADAPTERS.get(asset_type, "")

        try:
            adapter_cls = _load_class(adapter_path)
            adapter = adapter_cls()
            label = label or adapter.label
            live_status = live_registry.status_for(adapter.asset_type)
            data_blockers = _data_blockers(adapter, enabled)
            strategy_status = "ready" if enabled and adapter.RESEARCH_READY and not data_blockers else "blocked"
            backtest_status = "ready" if strategy_status == "ready" else "blocked"
            paper_status = "ready" if enabled and adapter.TRADABLE and strategy_status == "ready" else "blocked"
            items.append({
                "asset_type": adapter.asset_type,
                "label": label or adapter.label,
                "enabled": enabled,
                "data_source": adapter.DATA_SOURCE,
                "data_source_detail": adapter.DATA_SOURCE_DETAIL,
                "research_ready": bool(adapter.RESEARCH_READY),
                "tradable": bool(adapter.TRADABLE) and enabled,
                "universe_size": _safe_universe_size(adapter, enabled),
                "data_status": "ready" if not data_blockers else "blocked",
                "strategy_status": strategy_status,
                "backtest_status": backtest_status,
                "paper_status": paper_status,
                "live_status": live_status.status,
                "live_adapter": live_status.adapter,
                "blockers": [*data_blockers, *list(live_status.blockers)],
                "error": "",
            })
        except Exception as exc:
            items.append({
                "asset_type": asset_type,
                "label": label,
                "enabled": enabled,
                "data_source": "unknown",
                "data_source_detail": "",
                "research_ready": False,
                "tradable": False,
                "universe_size": 0,
                "data_status": "blocked",
                "strategy_status": "blocked",
                "backtest_status": "blocked",
                "paper_status": "blocked",
                "live_status": "blocked",
                "live_adapter": "unavailable",
                "blockers": ["asset_adapter_error"],
                "error": str(exc),
            })

    return items


def _data_blockers(adapter: Any, enabled: bool) -> list[str]:
    if not enabled:
        return ["asset_disabled"]
    blockers: list[str] = []
    if not bool(getattr(adapter, "RESEARCH_READY", False)):
        blockers.append("research_data_not_ready")
    if getattr(adapter, "asset_type", "") == "crypto":
        blockers.append("crypto_data_stale_until_fresh_source")
    return blockers
