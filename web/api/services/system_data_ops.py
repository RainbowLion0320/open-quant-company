"""System data operations payload builders."""

from __future__ import annotations


def backfill_history_payload(dimension: str = "", status: str = "", limit: int = 20) -> dict:
    from data.ops.backfill import BackfillLedger

    ledger = BackfillLedger()
    entries = ledger.history(dimension=dimension, status=status, limit=limit)
    return {
        "entries": [
            {
                "run_id": entry.run_id,
                "dimension": entry.dimension,
                "status": entry.status,
                "date_start": entry.date_start,
                "date_end": entry.date_end,
                "rows_fetched": entry.rows_fetched,
                "error": entry.error,
                "retry_count": entry.retry_count,
                "started_at": entry.started_at,
                "completed_at": entry.completed_at,
                "duration_seconds": entry.duration_seconds,
                "triggered_by": entry.triggered_by,
            }
            for entry in entries
        ],
        "summary": ledger.summary(),
        "total": len(entries),
        "status": "ok",
    }


def last_backfill_payload(dimension: str) -> dict:
    from data.ops.backfill import BackfillLedger

    ledger = BackfillLedger()
    last = ledger.last_run(dimension)
    last_ok = ledger.last_successful(dimension)
    return {
        "dimension": dimension,
        "last_run": {
            "run_id": last.run_id,
            "status": last.status,
            "started_at": last.started_at,
            "completed_at": last.completed_at,
            "rows_fetched": last.rows_fetched,
            "error": last.error,
        } if last else None,
        "last_successful": {
            "run_id": last_ok.run_id,
            "started_at": last_ok.started_at,
            "rows_fetched": last_ok.rows_fetched,
        } if last_ok else None,
        "status": "ok",
    }


def provider_health_payload() -> dict:
    from data.ingestion.provider import provider_health_report

    return {"providers": provider_health_report(), "status": "ok"}


def contracts_payload(dimension: str = "") -> dict:
    from data.quality.contract import list_contracts

    contracts = list_contracts()
    if dimension:
        contracts = [contract for contract in contracts if contract.dimension == dimension]
    return {
        "contracts": [
            {
                "dimension": contract.dimension,
                "schema_version": contract.schema_version,
                "columns": contract.columns,
                "primary_key": contract.primary_key,
                "freq": contract.freq,
                "sla_days": contract.sla_days,
                "pit_rule": contract.pit_rule,
                "owner": contract.owner,
                "description": contract.description,
                "migration_count": len(contract.migrations),
            }
            for contract in contracts
        ],
        "total": len(contracts),
        "status": "ok",
    }


def audit_history_payload(section: str = "", limit: int = 50) -> dict:
    from data.ops.audit import ConfigAuditLedger

    ledger = ConfigAuditLedger()
    entries = ledger.history(section=section, limit=limit)
    return {
        "entries": [
            {
                "change_id": entry.change_id,
                "timestamp": entry.timestamp,
                "section": entry.section,
                "method": entry.method,
                "changed_keys": entry.changed_keys,
                "source_ip": entry.source_ip,
                "run_mode": entry.run_mode,
            }
            for entry in entries
        ],
        "summary": ledger.summary(),
        "total": len(entries),
        "status": "ok",
    }
