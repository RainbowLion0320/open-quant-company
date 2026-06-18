"""Shared freshness gate helpers for health-check rows."""

from __future__ import annotations

from typing import Any


def freshness_gate(audit_rows: list[dict[str, Any]], *, required: list[str] | None = None) -> dict[str, object]:
    """Check data freshness from normalized audit/health rows."""
    required_keys = set(required or [])
    stale: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []
    details: list[dict[str, str]] = []
    for row in audit_rows:
        key = str(row.get("key") or row.get("table") or row.get("dimension") or "")
        status = str(row.get("status") or "").lower()
        if required_keys and key not in required_keys:
            continue
        severity = _freshness_severity(row, required=key in required_keys)
        if status == "missing":
            if severity == "warning":
                warnings.append(key)
            else:
                missing.append(key)
        elif status in {"stale", "error"}:
            if severity == "warning":
                warnings.append(key)
            else:
                stale.append(key)
        if status in {"missing", "stale", "error"}:
            details.append(
                {
                    "key": key,
                    "status": status,
                    "severity": severity,
                    "reason": str(row.get("reason") or row.get("freshness_reason") or ""),
                    "scope": str(row.get("scope") or row.get("data_domain") or ""),
                }
            )
    return {"ok": not stale and not missing, "stale": stale, "missing": missing, "warnings": warnings, "details": details}


def _freshness_severity(row: dict[str, Any], *, required: bool) -> str:
    if required:
        return "blocker"
    configured = str(row.get("freshness_severity") or "").lower()
    if configured == "warning":
        return "warning"
    repair_policy = str(row.get("repair_policy") or "").lower()
    data_domain = str(row.get("data_domain") or row.get("scope") or "").lower()
    registry_key = str(row.get("registry_key") or row.get("key") or row.get("dimension") or "").lower()
    table = str(row.get("table") or "").lower()
    if (
        repair_policy == "rate_limited"
        and data_domain in {"market_event", "event", ""}
        and registry_key in {"limit_list", "stock_limit_list", ""}
        and table in {"stock_limit_list", "limit_list", ""}
    ):
        return "warning"
    return "blocker"


def _iter_health_rows(result: object) -> list[dict[str, Any]]:
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


def health_result_to_gate_data(result: object) -> list[dict[str, str]]:
    """Normalize DB health result rows for freshness_gate()."""
    gate_data: list[dict[str, str]] = []
    for row in _iter_health_rows(result):
        key = str(row.get("table") or row.get("key") or row.get("dimension") or "")
        status_value = str(row.get("freshness_status") or row.get("status") or "").lower()
        if not status_value:
            status_value = "ok"
        gate_data.append(
            {
                "table": key,
                "status": status_value,
                "registry_key": str(row.get("registry_key") or row.get("key") or row.get("dimension") or ""),
                "repair_policy": str(row.get("repair_policy") or ""),
                "data_domain": str(row.get("data_domain") or row.get("scope") or ""),
                "freshness_reason": str(row.get("freshness_reason") or row.get("reason") or ""),
                "freshness_severity": str(row.get("freshness_severity") or ""),
            }
        )
    return gate_data


def freshness_gate_from_health_result(result: object) -> tuple[dict[str, object], int]:
    """Build gate payload and row count from a health-check result object."""
    rows = len(result) if hasattr(result, "__len__") else 0
    return freshness_gate(health_result_to_gate_data(result)), rows
