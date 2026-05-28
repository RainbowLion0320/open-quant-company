from __future__ import annotations

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def status() -> CliResult:
    from scripts.db_health_check import run_health_check

    result = run_health_check()
    rows = len(result) if hasattr(result, "__len__") else 0
    return CliResult(
        ok=True,
        command="data status",
        message=f"DB health check returned {rows} row(s)",
        data={"rows": rows},
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
