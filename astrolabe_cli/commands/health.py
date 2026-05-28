from __future__ import annotations

from astrolabe_cli.results import CliResult


def run_health() -> CliResult:
    from data.datahub import get_datahub
    from web.api.version import get_project_version

    hub = get_datahub()
    return CliResult(
        ok=True,
        command="health",
        message="Astrolabe local environment is reachable",
        data={
            "project": "astrolabe-quant",
            "version": get_project_version(),
            "store_root": str(hub.store_root),
            "cache_root": str(hub.cache_root),
        },
    )
