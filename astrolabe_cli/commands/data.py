from __future__ import annotations

import contextlib
import io

from data.quality.freshness_gate import freshness_gate, freshness_gate_from_health_result, health_result_to_gate_data

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload
from data.ingestion.source_capabilities import (
    audit_sources,
    sources_diff_payload,
    sources_summary_payload,
)


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


def tushare_audit(probe_network: bool = True) -> CliResult:
    from data.ingestion.tushare_governance import run_tushare_audit

    try:
        result = run_tushare_audit(probe_network=probe_network)
    except Exception as exc:
        return CliResult(
            ok=False,
            command="data tushare-audit",
            message="Tushare audit failed",
            errors=[str(exc)],
        )

    capabilities = result.get("capabilities", {})
    coverage = result.get("coverage", {})
    no_permission = sorted(
        name for name, item in capabilities.items()
        if isinstance(item, dict) and item.get("status") == "no_permission"
    )
    token = result.get("token")
    missing_secret = isinstance(token, dict) and token.get("status") != "ok"
    return CliResult(
        ok=not missing_secret,
        command="data tushare-audit",
        message="Tushare audit complete" if not missing_secret else "Tushare token missing",
        data={
            **result,
            "capability_count": len(capabilities),
            "coverage_count": len(coverage),
            "no_permission": no_permission,
        },
        errors=["missing TUSHARE_TOKEN"] if missing_secret else [],
    )


def tushare_backfill(scope: str, resume: bool, dry_run: bool, limit: int, days: int) -> CliResult:
    from data.ingestion.tushare_governance import run_tushare_backfill

    try:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = run_tushare_backfill(scope=scope, resume=resume, dry_run=dry_run, limit=limit, days=days)
    except Exception as exc:
        return CliResult(
            ok=False,
            command="data tushare-backfill",
            message="Tushare backfill failed",
            errors=[str(exc)],
            data={"scope": scope, "resume": resume, "dry_run": dry_run, "limit": limit, "days": days},
        )

    logs = (stdout.getvalue() + stderr.getvalue()).strip()
    if logs:
        result = {**result, "log_excerpt": logs[-4000:]}
    failed = result.get("failed", [])
    return CliResult(
        ok=not failed,
        command="data tushare-backfill",
        message="Dry run: Tushare backfill plan" if dry_run else "Tushare backfill complete",
        data=result,
        errors=[str(item) for item in failed],
    )


def sources() -> CliResult:
    payload = sources_summary_payload()
    return CliResult(
        ok=True,
        command="data sources",
        message="Data source capability summary",
        data=payload,
    )


def sources_audit(source: str, probe_network: bool) -> CliResult:
    try:
        payload = audit_sources(source=source, probe_network=probe_network, write=True)
    except Exception as exc:
        return CliResult(
            ok=False,
            command="data sources audit",
            message="Data source capability audit failed",
            errors=[str(exc)],
            data={"source": source, "probe_network": probe_network},
        )
    return CliResult(
        ok=payload.get("status") in {"ok", "degraded"},
        command="data sources audit",
        message="Data source capability audit complete",
        data=payload,
        errors=[str(item) for item in payload.get("errors", [])],
    )


def sources_diff_registry() -> CliResult:
    payload = sources_diff_payload()
    return CliResult(
        ok=True,
        command="data sources diff-registry",
        message="Data source capability registry diff complete",
        data=payload,
    )
