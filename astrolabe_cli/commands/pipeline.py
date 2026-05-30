"""Pipeline CLI commands — list and inspect pipeline flows."""
from __future__ import annotations

from astrolabe_cli.results import CliResult


def list_pipelines() -> CliResult:
    """List all available pipelines."""
    from web.api.services.pipeline import list_pipelines as _list

    items = _list()
    return CliResult(
        ok=True,
        command="pipeline list",
        message=f"{len(items)} pipeline(s) available",
        data={"items": items, "total": len(items)},
    )


def show_pipeline(key: str) -> CliResult:
    """Show a specific pipeline by key."""
    from web.api.services.pipeline import build_pipeline

    result = build_pipeline(key)
    if result is None:
        return CliResult(
            ok=False,
            command="pipeline show",
            message=f"Unknown pipeline: {key}",
            errors=["unknown_pipeline"],
            data={"key": key},
        )
    return CliResult(
        ok=True,
        command="pipeline show",
        message=f"Pipeline: {key}",
        data=result,
    )
