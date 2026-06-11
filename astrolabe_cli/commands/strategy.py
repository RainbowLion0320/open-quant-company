from __future__ import annotations

from dataclasses import asdict
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
    from data.strategy.catalog import get_strategy
    from data.strategy.plugins import iter_strategy_plugins, run_registered_strategies

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


def evidence(strategy: str | None = None) -> CliResult:
    from research.strategy_evaluation import list_evidence_artifacts, load_evidence_artifact

    if not strategy:
        items = list_evidence_artifacts()
        return CliResult(
            ok=True,
            command="strategy evidence",
            message=f"{len(items)} strategy evidence item(s)",
            data={"items": items, "total": len(items)},
        )

    detail = load_evidence_artifact(strategy)
    return CliResult(
        ok=True,
        command="strategy evidence",
        message=f"Evidence detail for {strategy}",
        data=detail,
    )


def compete(run_backtest: bool = False, oos_months: int = 36) -> CliResult:
    if run_backtest:
        try:
            from backtest.run_all_strategies import run_strategy_comparison

            run_strategy_comparison()
        except Exception as exc:
            return CliResult(
                ok=False,
                command="strategy compete",
                message="Strategy backtest run failed before competition report",
                errors=[str(exc)],
            )

    try:
        from research.strategy_competition import write_strategy_competition_report

        report, path = write_strategy_competition_report(oos_months=oos_months)
    except Exception as exc:
        return CliResult(
            ok=False,
            command="strategy compete",
            message="Strategy competition report failed",
            errors=[str(exc)],
        )
    return CliResult(
        ok=True,
        command="strategy compete",
        message=f"Strategy competition report written: {path}",
        data={"report": report, "path": str(path)},
    )
