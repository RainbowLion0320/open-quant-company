"""Asset overview payload builders."""

from __future__ import annotations


def asset_overview_payload() -> dict:
    from data.market.assets.overview import asset_overview_items

    items = asset_overview_items()
    return {"items": items, "total": len(items)}
