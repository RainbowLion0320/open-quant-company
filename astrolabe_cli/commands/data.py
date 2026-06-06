from __future__ import annotations

import contextlib
import io

from data.quality.freshness_gate import freshness_gate, freshness_gate_from_health_result, health_result_to_gate_data

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def run_health_check_quiet():
    from scripts.db_health_check import run_health_check

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        return run_health_check()


def freshness_gate_from_health_check() -> tuple[dict, int]:
    result = run_health_check_quiet()
    return freshness_gate_from_health_result(result)


def status() -> CliResult:
    result = run_health_check_quiet()
    rows = len(result) if hasattr(result, "__len__") else 0
    gate = freshness_gate(health_result_to_gate_data(result))

    return CliResult(
        ok=True,
        command="data status",
        message=f"DB health check returned {rows} row(s)",
        data={"rows": rows, "freshness_gate": gate},
    )


def repair(table: str, limit: int, days: int, dry_run: bool) -> CliResult:
    from scripts.repair_table import REPAIR_MAP, repair as repair_table

    if table not in REPAIR_MAP:
        return CliResult(
            ok=False,
            command="data repair",
            message=f"Unknown or non-repairable table: {table}",
            errors=["unknown_table"],
            data={"table": table},
        )
    if dry_run:
        return CliResult(
            ok=True,
            command="data repair",
            message=f"Dry run: repair {table}",
            data=dry_run_payload("data.repair", table=table, limit=limit, days=days),
        )

    try:
        repair_table(table, limit=limit, days=days)
    except Exception as exc:
        return CliResult(
            ok=False,
            command="data repair",
            message=f"Repair failed: {table}",
            errors=[str(exc)],
            data={"table": table, "limit": limit, "days": days},
        )
    return CliResult(
        ok=True,
        command="data repair",
        message=f"Repair complete: {table}",
        data={"table": table, "limit": limit, "days": days},
    )
