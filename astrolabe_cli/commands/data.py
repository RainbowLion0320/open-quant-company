from __future__ import annotations

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


def status() -> CliResult:
    from scripts.db_health_check import run_health_check

    result = run_health_check()
    rows = len(result) if hasattr(result, "__len__") else 0

    # Build freshness gate from health check data
    gate_data = []
    if hasattr(result, "to_dict"):
        for _, row in result.iterrows():
            entry = {"table": row.get("table", ""), "status": "ok"}
            pct = row.get("missing_pct", 0)
            if pct and float(pct) > 50:
                entry["status"] = "stale"
            gate_data.append(entry)

    gate = freshness_gate(gate_data)

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
