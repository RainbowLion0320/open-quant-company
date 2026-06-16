from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from astrolabe_cli.results import CliResult
from astrolabe_cli.commands.data import freshness_gate_from_health_check
from data.ingestion.source_capabilities import sources_diff_payload, sources_summary_payload
from data.storage.datahub import get_datahub
from research.strategy_competition import build_strategy_competition_report

SOURCE_CAPABILITY_STATUS_PRIORITY = {
    "no_permission": 100,
    "missing_secret": 90,
    "rate_limited": 80,
    "error": 70,
    "empty": 40,
    "ok": 0,
}
SOURCE_CAPABILITY_ARTIFACTS = (
    "akshare",
    "tushare",
    "tencent_finance",
    "eastmoney",
    "sina_finance",
    "tonghuashun",
    "exchange_official",
    "cninfo",
    "computed",
)


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


def _source_specific_capabilities() -> list[dict[str, Any]]:
    hub = get_datahub()
    rows: list[dict[str, Any]] = []
    for source in SOURCE_CAPABILITY_ARTIFACTS:
        if hasattr(hub, "artifact_path"):
            path = hub.artifact_path("data-sources", f"latest-{source}.json")
        else:
            path = hub.artifact_dir("data-sources") / f"latest-{source}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in payload.get("capabilities", []) if isinstance(payload, dict) else []:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _capability_status_by_dimension() -> dict[str, dict[str, str]]:
    from data.storage.dimensions import get_registry

    payload = sources_summary_payload()
    capabilities = []
    if isinstance(payload, dict):
        capabilities.extend(item for item in payload.get("capabilities", []) if isinstance(item, dict))
    capabilities.extend(_source_specific_capabilities())
    registry = get_registry()
    by_dimension: dict[str, dict[str, str]] = {}
    for item in capabilities:
        status = str(
            item.get("access_status")
            or item.get("probe_status")
            or item.get("permission_status")
            or ""
        )
        if status not in SOURCE_CAPABILITY_STATUS_PRIORITY:
            continue
        dimensions = item.get("mapped_dimensions") if isinstance(item.get("mapped_dimensions"), list) else []
        for dimension in dimensions:
            aliases = {str(dimension)}
            registry_item = registry.get(str(dimension))
            if registry_item is not None:
                aliases.add(registry_item.key)
                if registry_item.health_table:
                    aliases.add(registry_item.health_table)
            for key in aliases:
                current = by_dimension.get(key)
                current_rank = SOURCE_CAPABILITY_STATUS_PRIORITY.get(str(current.get("status")) if current else "", -1)
                rank = SOURCE_CAPABILITY_STATUS_PRIORITY[status]
                if current is None or rank > current_rank:
                    by_dimension[key] = {
                        "status": status,
                        "source": str(item.get("source") or ""),
                        "interface": str(item.get("interface") or ""),
                        "message": str(item.get("message") or item.get("probe_block_reason") or ""),
                    }
    return by_dimension


def _annotate_freshness_detail(
    details: list[dict[str, Any]],
    *,
    key: str,
    reason: str,
    capability: dict[str, str] | None = None,
) -> None:
    for detail in details:
        if str(detail.get("key") or "") != key:
            continue
        detail["reason"] = reason
        if capability:
            detail["capability_status"] = capability.get("status", "")
            detail["capability_source"] = capability.get("source", "")
            detail["capability_interface"] = capability.get("interface", "")
            detail["capability_message"] = capability.get("message", "")
        return


def _freshness_check() -> tuple[dict[str, Any], list[str], list[str]]:
    gate, rows = freshness_gate_from_health_check()
    stale = list(gate.get("stale") or [])
    missing = list(gate.get("missing") or [])
    warning_keys = list(gate.get("warnings") or [])
    details = [dict(item) for item in gate.get("details", []) if isinstance(item, dict)]
    gate = {**gate, "details": details}
    detail_reason = {str(item.get("key") or ""): str(item.get("reason") or "") for item in details}
    capability_by_dimension = _capability_status_by_dimension()
    blockers: list[str] = []
    for key in stale:
        capability = capability_by_dimension.get(str(key))
        if capability and capability.get("status") in {"no_permission", "missing_secret"}:
            status = str(capability["status"])
            blockers.append(f"missing_capability:{key}:{status}")
            _annotate_freshness_detail(details, key=str(key), reason=status, capability=capability)
        elif detail_reason.get(str(key)) == "source_not_updated":
            blockers.append(f"source_not_updated:{key}")
        else:
            blockers.append(f"stale_data:{key}")
    for key in missing:
        capability = capability_by_dimension.get(str(key))
        if capability and capability.get("status") in {"no_permission", "missing_secret"}:
            status = str(capability["status"])
            blockers.append(f"missing_capability:{key}:{status}")
            _annotate_freshness_detail(details, key=str(key), reason=status, capability=capability)
        else:
            blockers.append(f"missing_data:{key}")
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
