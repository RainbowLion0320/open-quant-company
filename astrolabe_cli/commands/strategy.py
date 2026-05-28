from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload, validate_runtime_mode


def catalog() -> CliResult:
    from research.strategy_catalog import catalog_items

    items = [asdict(item) for item in catalog_items()]
    return CliResult(
        ok=True,
        command="strategy catalog",
        message=f"{len(items)} strategies",
        data={"items": items, "total": len(items)},
    )


def run_strategy(strategy: str, mode: str, limit: int, dry_run: bool) -> CliResult:
    from data.registry import get_strategy
    from data.strategy_plugins import iter_strategy_plugins, run_registered_strategies

    try:
        mode = validate_runtime_mode(mode)
    except ValueError as exc:
        return CliResult(False, "strategy run", message=str(exc), errors=["invalid_runtime_mode"])

    meta: dict[str, Any] | None = get_strategy(strategy) if strategy != "all" else {"status": "production"}
    if not meta:
        return CliResult(False, "strategy run", message=f"Unknown strategy: {strategy}", errors=[strategy])
    if strategy != "all" and meta.get("status") != "production" and mode != "research":
        return CliResult(
            ok=False,
            command="strategy run",
            message=f"{strategy} is not production; rerun with --mode research",
            errors=["candidate_requires_research_mode"],
        )

    try:
        plugins = [plugin.name for plugin in iter_strategy_plugins(strategy, mode=mode)]
    except ValueError as exc:
        return CliResult(False, "strategy run", message=str(exc), errors=["strategy_resolution_failed"])

    if dry_run:
        return CliResult(
            ok=True,
            command="strategy run",
            message=f"Dry run: {len(plugins)} strategy plugin(s)",
            data=dry_run_payload("strategy.run", strategy=strategy, mode=mode, limit=limit, plugins=plugins),
        )

    try:
        result = run_registered_strategies(strategy, limit=limit, mode=mode)
    except Exception as exc:
        return CliResult(
            ok=False,
            command="strategy run",
            message=f"Strategy run failed: {strategy}",
            data={"strategy": strategy, "mode": mode},
            errors=[str(exc)],
        )
    return CliResult(
        ok=True,
        command="strategy run",
        message=f"Ran {strategy} in {mode} mode",
        data={"strategies": result, "mode": mode},
    )


def evidence(strategy: str) -> CliResult:
    from research.strategy_evaluation import strategy_evidence_dir

    path = strategy_evidence_dir() / f"{strategy}.json"
    if not path.exists():
        return CliResult(
            ok=False,
            command="strategy evidence",
            message=f"No evidence report found for {strategy}",
            data={"path": str(path)},
            errors=["evidence_missing"],
        )
    return CliResult(
        ok=True,
        command="strategy evidence",
        message=f"Evidence report found for {strategy}",
        data={"path": str(Path(path).resolve())},
    )
