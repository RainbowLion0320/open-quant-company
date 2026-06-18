"""Settings audit payload helpers used by the settings route."""

from __future__ import annotations

from fastapi import Request


def record_settings_change(request: Request, section: str, method: str, old_data: dict, new_data: dict) -> None:
    """Record a config change without letting audit storage failures block writes."""
    try:
        from data.ops.audit import ConfigAuditLedger

        ledger = ConfigAuditLedger()
        ledger.record(
            section=section,
            method=method,
            old_data=old_data,
            new_data=new_data,
            source_ip=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
        )
    except Exception:
        return
