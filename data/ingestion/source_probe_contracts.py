"""Safe sample probe contracts for external source capabilities."""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from data.ingestion.source_discovery import SAMPLE_PROBE_ALLOWLIST, probe_candidate_capability_sample

SAFE_AKSHARE_NO_ARG_PATTERNS = (
    "_spot",
    "spot_",
    "macro_",
    "bond_",
    "index_",
    "stock_board_",
)


@dataclass(frozen=True)
class ProbeContract:
    contract_id: str
    runner: Callable[[], Any] | None = None
    block_reason: str = ""


def probe_capability_full_sample(
    capability: dict[str, Any],
    *,
    dry_run: bool = False,
    resumed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return probe metadata for one capability without writing provider data."""
    if resumed and _is_completed_probe(resumed):
        sample = dict(resumed.get("sample_probe") or {})
        sample["resume_skipped"] = True
        return {
            **_extract_probe_fields(resumed),
            "sample_probe": sample,
        }

    contract = probe_contract_for(capability)
    if contract.block_reason:
        return _blocked_result(capability, contract)
    if dry_run:
        return {
            "probe_status": "planned",
            "probe_contract_id": contract.contract_id,
            "probe_block_reason": "",
            "probe_attempted_at": "",
            "elapsed_ms": None,
            "row_count": None,
            "error_class": "",
            "sample_probe": {"status": "planned", "contract_id": contract.contract_id},
        }
    if contract.runner is None:
        return _blocked_result(capability, ProbeContract(contract.contract_id, block_reason="missing_probe_contract"))

    attempted_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    try:
        result = contract.runner()
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        return {
            "probe_status": "error",
            "probe_contract_id": contract.contract_id,
            "probe_block_reason": "",
            "probe_attempted_at": attempted_at,
            "elapsed_ms": elapsed_ms,
            "row_count": 0,
            "error_class": exc.__class__.__name__,
            "sample_probe": {
                "status": "error",
                "contract_id": contract.contract_id,
                "row_count": 0,
                "field_sample": [],
                "message": str(exc)[:240],
            },
        }

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    if isinstance(result, dict) and isinstance(result.get("status"), str):
        row_count, fields = _result_shape(result)
        status = str(result.get("status") or "error")
        message = str(result.get("message") or "")
    else:
        row_count, fields = _result_shape(result)
        status = "ok" if row_count > 0 or fields else "empty"
        message = "sample parsed" if status == "ok" else "sample returned no rows"
    return {
        "probe_status": status,
        "probe_contract_id": contract.contract_id,
        "probe_block_reason": "",
        "probe_attempted_at": attempted_at,
        "elapsed_ms": elapsed_ms,
        "row_count": row_count,
        "error_class": "",
        "field_sample": fields,
        "sample_probe": {
            "status": status,
            "contract_id": contract.contract_id,
            "row_count": row_count,
            "field_sample": fields,
            "message": message,
        },
    }


def probe_contract_for(capability: dict[str, Any]) -> ProbeContract:
    source = str(capability.get("source") or "")
    interface = str(capability.get("interface") or "")
    backend = str(capability.get("backend") or "")
    if source == "computed" or capability.get("access_status") == "internal":
        return ProbeContract("internal.registry", block_reason="internal_capability")
    if source == "tushare":
        return ProbeContract("tushare.account_probe")
    if (source, interface) in SAMPLE_PROBE_ALLOWLIST:
        return ProbeContract(
            f"{source}.{interface}.sample_http",
            runner=lambda: probe_candidate_capability_sample(capability),
        )
    if source == "akshare" or backend == "akshare":
        return _akshare_contract(interface)
    if capability.get("access_status") == "manual_review":
        return ProbeContract(f"{source}.{interface}.manual", block_reason="missing_probe_contract")
    return ProbeContract(f"{source}.{interface}.unknown", block_reason="missing_probe_contract")


def _akshare_contract(interface: str) -> ProbeContract:
    try:
        import akshare
    except Exception:
        return ProbeContract(f"akshare.{interface}", block_reason="provider_unavailable")
    fn = getattr(akshare, interface, None)
    if not callable(fn):
        return ProbeContract(f"akshare.{interface}", block_reason="provider_callable_missing")
    if _has_required_params(fn):
        return ProbeContract(f"akshare.{interface}", block_reason="missing_probe_contract")
    if not _is_safe_akshare_sample_name(interface):
        reason = "unsafe_unbounded_query" if _has_any_params(fn) else "missing_probe_contract"
        return ProbeContract(f"akshare.{interface}", block_reason=reason)
    return ProbeContract("akshare.no_arg_dataframe", runner=fn)


def _is_safe_akshare_sample_name(interface: str) -> bool:
    lowered = interface.lower()
    return any(pattern in lowered for pattern in SAFE_AKSHARE_NO_ARG_PATTERNS)


def _has_required_params(fn: Callable[..., Any]) -> bool:
    try:
        signature = inspect.signature(fn)
    except Exception:
        return True
    for param in signature.parameters.values():
        if param.kind in {param.VAR_POSITIONAL, param.VAR_KEYWORD}:
            continue
        if param.default is inspect._empty:
            return True
    return False


def _has_any_params(fn: Callable[..., Any]) -> bool:
    try:
        return bool(inspect.signature(fn).parameters)
    except Exception:
        return True


def _result_shape(result: Any) -> tuple[int, list[str]]:
    if isinstance(result, dict) and isinstance(result.get("status"), str):
        fields = result.get("field_sample")
        row_count = result.get("row_count")
        return int(row_count or 0), sorted(str(item) for item in fields) if isinstance(fields, list) else []
    columns = getattr(result, "columns", None)
    if columns is not None:
        row_count = len(result) if hasattr(result, "__len__") else 0
        return int(row_count), sorted(str(item) for item in list(columns)[:40])
    if isinstance(result, list):
        row_count = len(result)
        first = result[0] if result else {}
        fields = sorted(str(item) for item in first.keys()) if isinstance(first, dict) else []
        return row_count, fields
    if isinstance(result, dict):
        return 1 if result else 0, sorted(str(item) for item in result.keys())[:40]
    try:
        return int(len(result)), []
    except Exception:
        return (1 if result is not None else 0), []


def _blocked_result(capability: dict[str, Any], contract: ProbeContract) -> dict[str, Any]:
    reason = contract.block_reason or "missing_probe_contract"
    return {
        "probe_status": "blocked",
        "probe_contract_id": contract.contract_id,
        "probe_block_reason": reason,
        "probe_attempted_at": "",
        "elapsed_ms": None,
        "row_count": None,
        "error_class": "",
        "sample_probe": {
            "status": "blocked",
            "contract_id": contract.contract_id,
            "block_reason": reason,
            "message": f"Probe blocked: {reason}",
        },
    }


def _is_completed_probe(item: dict[str, Any]) -> bool:
    status = str(item.get("probe_status") or "")
    return status in {"ok", "empty", "error", "blocked", "no_permission", "rate_limited", "missing_secret"}


def _extract_probe_fields(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "probe_status",
        "probe_contract_id",
        "probe_block_reason",
        "probe_attempted_at",
        "elapsed_ms",
        "row_count",
        "error_class",
        "field_sample",
    )
    return {key: item.get(key) for key in keys if key in item}
