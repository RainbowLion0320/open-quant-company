"""Assets CLI commands — inspect multi-asset coverage and readiness."""
from __future__ import annotations

from astrolabe_cli.results import CliResult


def overview() -> CliResult:
    """Show asset type coverage, provenance, and readiness."""
    from data.assets.overview import asset_overview_items

    items = asset_overview_items()
    return CliResult(
        ok=True,
        command="assets overview",
        message=f"{len(items)} asset type(s)",
        data={"items": items, "total": len(items)},
    )
