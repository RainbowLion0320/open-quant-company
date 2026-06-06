"""Shared freshness gate helpers for health-check rows."""

from __future__ import annotations

from typing import Any


def freshness_gate(audit_rows: list[dict[str, Any]], *, required: list[str] | None = None) -> dict[str, object]:
    """Check data freshness from normalized audit/health rows."""
    required_keys = set(required or [])
    stale: list[str] = []
    missing: list[str] = []
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
        try:
            missing_pct = float(row.get("missing_pct", 0) or 0)
        except Exception:
            missing_pct = 0.0
        if missing_pct > 50 and status_value in {"ok", "fresh"}:
            status_value = "stale"
        gate_data.append({"table": key, "status": status_value})
    return gate_data


def freshness_gate_from_health_result(result: object) -> tuple[dict[str, object], int]:
    """Build gate payload and row count from a health-check result object."""
    rows = len(result) if hasattr(result, "__len__") else 0
    return freshness_gate(health_result_to_gate_data(result)), rows
