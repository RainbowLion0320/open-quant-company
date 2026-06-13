from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from astrolabe_cli.results import CliResult
from astrolabe_cli.commands.data import freshness_gate_from_health_check
from data.ingestion.source_capabilities import sources_diff_payload
from data.storage.datahub import get_datahub
from research.strategy_competition import build_strategy_competition_report


def _source_capability_check() -> tuple[dict[str, Any], list[str], list[str]]:
    payload = sources_diff_payload()
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    missing = payload.get("registry_missing_source") if isinstance(payload.get("registry_missing_source"), list) else []
    blockers = [f"missing_source_capability:{item.get('dimension')}" for item in missing if isinstance(item, dict)]
    status = "ok" if not blockers else "blocked"
    return {
        "status": status,
        "summary": summary,
        "registry_missing_source": missing,
    }, blockers, []


def _freshness_check() -> tuple[dict[str, Any], list[str], list[str]]:
    gate, rows = freshness_gate_from_health_check()
    stale = list(gate.get("stale") or [])
    missing = list(gate.get("missing") or [])
    warning_keys = list(gate.get("warnings") or [])
    blockers = [f"stale_data:{key}" for key in stale] + [f"missing_data:{key}" for key in missing]
    warnings = [f"freshness_warning:{key}" for key in warning_keys]
    return {
        "status": "ok" if gate.get("ok") else "blocked",
        "rows": rows,
        "freshness_gate": gate,
    }, blockers, warnings


def _strategy_evidence_check() -> tuple[dict[str, Any], list[str], list[str]]:
    report = build_strategy_competition_report()
    rows = report.get("rankings") if isinstance(report.get("rankings"), list) else []
    blockers: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("competition_valid", False):
            continue
        strategy = str(row.get("strategy") or "unknown")
        data_quality = row.get("data_quality") if isinstance(row.get("data_quality"), dict) else {}
        for blocker in data_quality.get("blockers") or []:
            blockers.append(str(blocker))
            blockers.append(f"strategy_blocked:{strategy}:{blocker}")
    return {
        "status": "ok" if not blockers else "blocked",
        "summary": report.get("summary", {}),
        "invalid_strategies": [
            {
                "strategy": row.get("strategy"),
                "blockers": (row.get("data_quality") or {}).get("blockers", []),
                "alpha_evidence": row.get("alpha_evidence", {}),
            }
            for row in rows
            if isinstance(row, dict) and not row.get("competition_valid", False)
        ],
    }, blockers, []


def _execution_check() -> tuple[dict[str, Any], list[str], list[str]]:
    warnings = ["live_broker_not_integrated"]
    return {
        "status": "not_integrated",
        "paper_execution": "available",
        "live_broker": "not_integrated",
    }, [], warnings


def build_lifecycle_payload() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    blockers: list[str] = []
    warnings: list[str] = []
    for key, builder in [
        ("source_capabilities", _source_capability_check),
        ("data_freshness", _freshness_check),
        ("strategy_evidence", _strategy_evidence_check),
        ("execution", _execution_check),
    ]:
        check, check_blockers, check_warnings = builder()
        checks[key] = check
        blockers.extend(check_blockers)
        warnings.extend(check_warnings)

    unique_blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    unique_warnings = sorted(dict.fromkeys(str(item) for item in warnings if item))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": "blocked" if unique_blockers else "ok",
        "checks": checks,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "recommended_command": "astroq lifecycle check --json",
    }


def write_lifecycle_payload(payload: dict[str, Any]) -> str:
    out_dir = get_datahub().artifact_dir("lifecycle")
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    stamped = out_dir / f"lifecycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    stamped.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
    return str(latest)


def check() -> CliResult:
    payload = build_lifecycle_payload()
    path = write_lifecycle_payload(payload)
    payload = {**payload, "artifact_path": path}
    ok = payload["status"] == "ok"
    return CliResult(
        ok=ok,
        command="lifecycle check",
        message="Lifecycle readiness ok" if ok else "Lifecycle readiness blocked",
        data=payload,
        errors=payload["blockers"],
    )
