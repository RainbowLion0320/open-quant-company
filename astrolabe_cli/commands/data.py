from __future__ import annotations

import contextlib
import io

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def freshness_gate(audit_rows: list[dict], *, required: list[str] | None = None) -> dict:
    """Check data freshness from audit/health rows.

    Returns {"ok": bool, "stale": [...], "missing": [...]}.
    """
    required_keys = set(required or [])
    stale = []
    missing = []
    for row in audit_rows:
        key = str(row.get("key") or row.get("table") or row.get("dimension") or "")
        status = str(row.get("status") or "").lower()
        if required_keys and key not in required_keys:
            continue
        if status == "missing":
            missing.append(key)
        elif status in {"stale", "error"}:
            stale.append(key)
    return {"ok": not stale and not missing, "stale": stale, "missing": missing}


def _iter_health_rows(result) -> list[dict]:
    if hasattr(result, "iterrows"):
        return [dict(row) for _, row in result.iterrows()]
    if isinstance(result, list):
        return [dict(row) for row in result if isinstance(row, dict)]
    if isinstance(result, dict):
        rows = result.get("rows")
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
        return [dict(result)]
    return []


def health_result_to_gate_data(result) -> list[dict]:
    """Normalize DB health result rows for freshness_gate()."""
    gate_data: list[dict] = []
    for row in _iter_health_rows(result):
        key = str(row.get("table") or row.get("key") or row.get("dimension") or "")
        status_value = str(row.get("status") or "").lower()
        if not status_value:
            status_value = "ok"
        try:
            missing_pct = float(row.get("missing_pct", 0) or 0)
        except Exception:
            missing_pct = 0.0
        if missing_pct > 50 and status_value == "ok":
            status_value = "stale"
        gate_data.append({"table": key, "status": status_value})
    return gate_data


def run_health_check_quiet():
    from scripts.db_health_check import run_health_check

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        return run_health_check()


def freshness_gate_from_health_check() -> tuple[dict, int]:
    result = run_health_check_quiet()
    rows = len(result) if hasattr(result, "__len__") else 0
    return freshness_gate(health_result_to_gate_data(result)), rows


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
