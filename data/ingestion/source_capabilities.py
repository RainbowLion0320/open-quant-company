"""External data source capability governance.

This module deliberately models provider capabilities separately from the
project data registry. ``data_registry`` says what Astrolabe currently uses;
this registry says what each external source appears able to provide.
"""

from __future__ import annotations

import inspect
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from core.env_secrets import secret_status
from data.ingestion.provider import AKShareAdapter, TushareAdapter
from data.ingestion.source_capability_catalog import (
    AKSHARE_FREQUENCY_OVERRIDES,
    AKSHARE_NAME_DIMENSIONS,
    CANDIDATE_CAPABILITIES,
    RECOMMENDED_AUDIT_COMMAND,
    SOURCE_IDS,
    source_catalog,
)
from data.ingestion.source_discovery import (
    BACKEND_SOURCE_IDS,
    DISCOVERY_DEPTHS,
    SAMPLE_PROBE_ALLOWLIST,
    backend_source_for_akshare_name,
    probe_candidate_capability_sample,
)
from data.ingestion.source_probe_contracts import probe_capability_full_sample
from data.ingestion.tushare_capabilities import TUSHARE_CAPABILITY_CATALOG
from data.storage.datahub import DataHub, get_datahub
from data.storage.dimensions import DataDimension, get_registry


def sources_summary_payload(hub: DataHub | None = None) -> dict[str, Any]:
    path = _artifact_path(hub)
    payload = _read_artifact(path)
    if not isinstance(payload, dict):
        return {
            "status": "no_artifact",
            "latest": None,
            "summary": _empty_summary(),
            "sources": _source_rows([], generated_at=""),
            "capabilities": [],
            "diff": _empty_diff(),
            "recommended_command": RECOMMENDED_AUDIT_COMMAND,
        }
    return _normalize_payload(payload, path)


def sources_diff_payload(hub: DataHub | None = None) -> dict[str, Any]:
    payload = sources_summary_payload(hub)
    diff = payload.get("diff") if isinstance(payload.get("diff"), dict) else _empty_diff()
    return {
        "status": payload.get("status", "no_artifact"),
        "generated_at": payload.get("generated_at"),
        "summary": diff.get("summary", {}),
        "capability_unmapped": diff.get("capability_unmapped", []),
        "registry_missing_source": diff.get("registry_missing_source", []),
        "field_frequency_mismatch": diff.get("field_frequency_mismatch", []),
        "recommended_command": payload.get("recommended_command", RECOMMENDED_AUDIT_COMMAND),
    }


def audit_sources(
    source: str = "all",
    *,
    probe_network: bool = False,
    discovery_depth: str = "catalog",
    dry_run: bool = False,
    resume: bool = False,
    write: bool = True,
    hub: DataHub | None = None,
) -> dict[str, Any]:
    if discovery_depth not in DISCOVERY_DEPTHS:
        raise ValueError(f"Unknown discovery_depth: {discovery_depth}")
    selected = _selected_sources(source)
    errors: list[dict[str, str]] = []
    capabilities: list[dict[str, Any]] = []
    audit_details: dict[str, Any] = {}

    if "akshare" in selected:
        result = audit_akshare_capabilities()
        capabilities.extend(result["capabilities"])
        audit_details["akshare"] = {k: v for k, v in result.items() if k != "capabilities"}
        errors.extend(result.get("errors", []))

    backend_selected = selected & BACKEND_SOURCE_IDS
    if backend_selected:
        result = audit_akshare_backend_capabilities(selected_sources=backend_selected)
        capabilities.extend(result["capabilities"])
        audit_details["akshare_backend_mapping"] = {k: v for k, v in result.items() if k != "capabilities"}
        errors.extend(result.get("errors", []))

    if "tushare" in selected:
        result = audit_tushare_capabilities(probe_network=probe_network and not dry_run)
        capabilities.extend(result["capabilities"])
        audit_details["tushare"] = {k: v for k, v in result.items() if k != "capabilities"}

    for item in CANDIDATE_CAPABILITIES:
        if item["source"] in selected:
            capabilities.append(_capability(**item))

    capabilities = _dedupe_capabilities(capabilities)
    if discovery_depth == "sample":
        capabilities = _apply_sample_probes(capabilities)
    if discovery_depth == "full-sample":
        capabilities = _apply_full_sample_probes(capabilities, dry_run=dry_run, resume=resume, hub=hub, source=source)

    generated_at = datetime.now(timezone.utc).isoformat()
    diff = diff_capabilities_with_registry(capabilities)
    payload: dict[str, Any] = {
        "schema_version": 2,
        "status": "ok" if not errors else "degraded",
        "generated_at": generated_at,
        "recommended_command": RECOMMENDED_AUDIT_COMMAND,
        "discovery_depth": discovery_depth,
        "dry_run": dry_run,
        "resume": resume,
        "sources": _source_rows(capabilities, generated_at=generated_at),
        "summary": _summary(capabilities),
        "capabilities": sorted(capabilities, key=_capability_sort_key),
        "diff": diff,
        "audit": audit_details,
        "errors": errors,
    }
    if write:
        if discovery_depth == "full-sample":
            payload["probe_run"] = _write_probe_run(
                payload,
                hub=hub,
                source=source,
                dry_run=dry_run,
                resume=resume,
                generated_at=generated_at,
            )
        path = _artifact_path(hub, source=source)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        payload["latest"] = {"generated_at": generated_at, "artifact_path": path.as_posix()}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def audit_akshare_capabilities(limit: int | None = None) -> dict[str, Any]:
    try:
        import akshare
    except Exception as exc:
        return {
            "source": "akshare",
            "version": "",
            "capabilities": [],
            "errors": [{"source": "akshare", "message": str(exc)[:300]}],
        }

    names = _public_callable_names(akshare)
    capabilities: list[dict[str, Any]] = []
    for name in names[:limit] if limit else names:
        obj = getattr(akshare, name, None)
        if not callable(obj):
            continue
        module = getattr(obj, "__module__", "") or ""
        mapped_dimensions = AKSHARE_NAME_DIMENSIONS.get(name, [])
        asset_type, data_domain, frequency = _infer_akshare_taxonomy(name)
        capabilities.append(
            _capability(
                source="akshare",
                interface=name,
                asset_type=asset_type,
                data_domain=data_domain,
                frequency=frequency,
                requires_token=False,
                access_status="introspected",
                probe_strategy="introspection_only",
                discovery_scope="full_local_introspection",
                integration_status="project_integrated" if mapped_dimensions else "unmapped",
                mapped_dimensions=mapped_dimensions,
                module=module,
                signature=_signature(obj),
                docstring_summary=_doc_summary(obj),
                field_sample=[],
            )
        )
    return {
        "source": "akshare",
        "version": str(getattr(akshare, "__version__", "")),
        "callable_count": len(capabilities),
        "capabilities": capabilities,
        "errors": [],
    }


def audit_akshare_backend_capabilities(
    selected_sources: set[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    try:
        import akshare
    except Exception as exc:
        return {
            "source": "akshare_backend_mapping",
            "version": "",
            "capabilities": [],
            "errors": [{"source": "akshare_backend_mapping", "message": str(exc)[:300]}],
        }

    selected = set(selected_sources or BACKEND_SOURCE_IDS)
    capabilities: list[dict[str, Any]] = []
    names = _public_callable_names(akshare)
    for name in names[:limit] if limit else names:
        backend_source = _backend_source_for_akshare_name(name)
        if not backend_source or backend_source not in selected:
            continue
        obj = getattr(akshare, name, None)
        module = getattr(obj, "__module__", "") or ""
        asset_type, data_domain, frequency = _infer_akshare_taxonomy(name)
        capabilities.append(
            _capability(
                source=backend_source,
                interface=name,
                asset_type=asset_type,
                data_domain=data_domain,
                frequency=frequency,
                requires_token=False,
                access_status="candidate",
                probe_status="not_probed",
                probe_strategy="akshare_backend_introspection",
                discovery_status="discovered",
                discovery_scope="package_backend_mapping",
                integration_status="backend_source",
                mapped_dimensions=[],
                backend="akshare",
                module=module,
                signature=_signature(obj),
                docstring_summary=_doc_summary(obj),
                field_sample=[],
                sample_probe={"status": "not_probed"},
            )
        )
    return {
        "source": "akshare_backend_mapping",
        "version": str(getattr(akshare, "__version__", "")),
        "callable_count": len(capabilities),
        "capabilities": capabilities,
        "errors": [],
    }


def audit_tushare_capabilities(probe_network: bool = False) -> dict[str, Any]:
    token = secret_status("TUSHARE_TOKEN")
    probe_results: dict[str, dict[str, Any]] = {}
    if probe_network:
        from data.ingestion.tushare_governance import TushareGovernance

        probe_results = TushareGovernance().probe_capabilities(probe_network=True)
    capabilities = []
    for name, meta in TUSHARE_CAPABILITY_CATALOG.items():
        probed = probe_results.get(name, {}) if probe_results else {}
        status = str(probed.get("status") or ("not_probed" if not probe_network else "unknown"))
        discovery_status = "sample_probed" if status in {"ok", "rate_limited", "no_permission", "error"} else "discovered"
        mapped = [item for item in str(meta.get("mapped_dimensions", "")).split(",") if item]
        capabilities.append(
            _capability(
                source="tushare",
                interface=name,
                asset_type=meta["asset_type"],
                data_domain=meta["data_domain"],
                frequency=meta["frequency"],
                requires_token=True,
                access_status=status,
                permission_status=status,
                rate_limit_status="rate_limited" if status == "rate_limited" else "",
                probe_strategy="account_probe" if probe_network else "offline_catalog",
                probe_status=status,
                discovery_status="project_integrated" if mapped else discovery_status,
                discovery_scope="account_probe" if probe_network else "official_catalog",
                integration_status="project_integrated" if mapped else "unmapped",
                mapped_dimensions=mapped,
                rows=probed.get("rows", 0),
                message=str(probed.get("message", ""))[:300],
                field_sample=[],
                sample_probe={"status": status, "row_count": int(probed.get("rows") or 0)}
                if probe_network
                else {"status": "not_probed"},
            )
        )
    return {
        "source": "tushare",
        "token": token,
        "probe_network": probe_network,
        "capabilities": capabilities,
    }


def diff_capabilities_with_registry(
    capabilities: Iterable[dict[str, Any]],
    dimensions: Iterable[DataDimension | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    caps = [dict(item) for item in capabilities]
    dims = list(dimensions if dimensions is not None else get_registry().all.values())
    dim_rows = [_dimension_row(item) for item in dims]

    cap_sources = {(item.get("source"), mapped) for item in caps for mapped in item.get("mapped_dimensions", [])}
    cap_sources_by_source = {str(item.get("source")) for item in caps}
    capability_unmapped = [
        {
            "source": item.get("source", ""),
            "interface": item.get("interface", ""),
            "asset_type": item.get("asset_type", ""),
            "data_domain": item.get("data_domain", ""),
            "frequency": item.get("frequency", ""),
            "integration_status": item.get("integration_status", ""),
            "access_status": item.get("access_status", ""),
            "discovery_status": item.get("discovery_status", ""),
            "probe_status": item.get("probe_status", ""),
        }
        for item in caps
        if not item.get("mapped_dimensions")
        and item.get("source") not in {"exchange_official", "cninfo"}
    ]
    registry_missing_source = []
    field_frequency_mismatch = []
    for dim in dim_rows:
        if dim["status"] == "planned":
            continue
        normalized = _normalize_registry_source(dim["source"])
        if (normalized, dim["key"]) not in cap_sources and normalized not in cap_sources_by_source:
            registry_missing_source.append(
                {
                    "dimension": dim["key"],
                    "source": dim["source"],
                    "normalized_source": normalized,
                    "status": dim["status"],
                    "frequency": dim["freq"],
                    "issue": "registered dimension has no matching source capability",
                }
            )
        for cap in caps:
            cap_source = _normalize_registry_source(str(cap.get("source", "")))
            if cap_source == normalized and dim["key"] in cap.get("mapped_dimensions", []) and cap.get("frequency") != dim["freq"]:
                field_frequency_mismatch.append(
                    {
                        "dimension": dim["key"],
                        "source": dim["source"],
                        "interface": cap.get("interface", ""),
                        "registry_frequency": dim["freq"],
                        "capability_frequency": cap.get("frequency", ""),
                    }
                )
    return {
        "summary": {
            "capability_unmapped_count": len(capability_unmapped),
            "registry_missing_source_count": len(registry_missing_source),
            "field_frequency_mismatch_count": len(field_frequency_mismatch),
        },
        "capability_unmapped": capability_unmapped,
        "registry_missing_source": registry_missing_source,
        "field_frequency_mismatch": field_frequency_mismatch,
    }


def _capability(**kwargs: Any) -> dict[str, Any]:
    mapped = kwargs.pop("mapped_dimensions", [])
    if isinstance(mapped, str):
        mapped = [mapped] if mapped else []
    integration_status = kwargs.pop("integration_status", "unmapped")
    access_status = kwargs.pop("access_status", "unknown")
    probe_status = kwargs.pop("probe_status", "not_probed")
    discovery_status = kwargs.pop(
        "discovery_status",
        _default_discovery_status(integration_status=integration_status, access_status=access_status, probe_status=probe_status),
    )
    sample_probe = kwargs.pop("sample_probe", {"status": probe_status or "not_probed"})
    return {
        "source": kwargs.pop("source", ""),
        "interface": kwargs.pop("interface", ""),
        "asset_type": kwargs.pop("asset_type", "unknown"),
        "data_domain": kwargs.pop("data_domain", "unknown"),
        "frequency": kwargs.pop("frequency", "unknown"),
        "requires_token": bool(kwargs.pop("requires_token", False)),
        "permission_status": kwargs.pop("permission_status", ""),
        "rate_limit_status": kwargs.pop("rate_limit_status", ""),
        "access_status": access_status,
        "probe_strategy": kwargs.pop("probe_strategy", "manual_review"),
        "discovery_status": discovery_status,
        "discovery_scope": kwargs.pop("discovery_scope", "manual_seed"),
        "probe_status": probe_status,
        "sample_probe": sample_probe if isinstance(sample_probe, dict) else {"status": str(sample_probe)},
        "probe_contract_id": kwargs.pop("probe_contract_id", ""),
        "probe_attempted_at": kwargs.pop("probe_attempted_at", ""),
        "probe_block_reason": kwargs.pop("probe_block_reason", ""),
        "elapsed_ms": kwargs.pop("elapsed_ms", None),
        "row_count": kwargs.pop("row_count", None),
        "error_class": kwargs.pop("error_class", ""),
        "source_url": kwargs.pop("source_url", ""),
        "endpoint_pattern": kwargs.pop("endpoint_pattern", ""),
        "field_sample": kwargs.pop("field_sample", []),
        "integration_status": integration_status,
        "mapped_dimensions": list(mapped),
        **kwargs,
    }


def _default_discovery_status(*, integration_status: str, access_status: str, probe_status: str) -> str:
    if integration_status == "project_integrated":
        return "project_integrated"
    if access_status == "internal":
        return "project_integrated"
    if probe_status == "ok":
        return "sample_probed"
    return "discovered"


def _backend_source_for_akshare_name(name: str) -> str:
    return backend_source_for_akshare_name(name)


def _dedupe_capabilities(capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in capabilities:
        normalized = _capability(**item)
        key = (str(normalized.get("source", "")), str(normalized.get("interface", "")))
        existing = merged.get(key)
        if not existing:
            merged[key] = normalized
            continue
        merged[key] = _merge_capability(existing, normalized)
    return list(merged.values())


def _merge_capability(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    current = dict(existing)
    for key, value in incoming.items():
        if key == "mapped_dimensions":
            dims = list(dict.fromkeys([*current.get("mapped_dimensions", []), *value]))
            current[key] = dims
            continue
        if key == "field_sample":
            current[key] = current.get(key) or value
            continue
        if key == "sample_probe":
            if current.get("sample_probe", {}).get("status") in {"", "not_probed"} and value.get("status") not in {"", "not_probed"}:
                current[key] = value
            continue
        if not current.get(key) and value:
            current[key] = value
    if current.get("integration_status") != "project_integrated" and incoming.get("integration_status") == "project_integrated":
        current["integration_status"] = "project_integrated"
        current["discovery_status"] = "project_integrated"
    return current


def _apply_sample_probes(capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated = []
    for item in capabilities:
        current = dict(item)
        if (current.get("source"), current.get("interface")) in SAMPLE_PROBE_ALLOWLIST:
            result = probe_candidate_capability_sample(current)
            if result:
                status = str(result.get("status") or "error")
                current["sample_probe"] = result
                current["probe_status"] = status
                if status == "ok":
                    current["discovery_status"] = "sample_probed"
                    fields = result.get("field_sample")
                    if isinstance(fields, list) and fields:
                        current["field_sample"] = [str(field) for field in fields]
                elif status in {"error", "empty", "rate_limited", "no_permission"}:
                    current["probe_status"] = status
        updated.append(current)
    return updated


def _apply_full_sample_probes(
    capabilities: list[dict[str, Any]],
    *,
    dry_run: bool,
    resume: bool,
    hub: DataHub | None,
    source: str,
) -> list[dict[str, Any]]:
    resume_map = _resume_probe_results(hub=hub, source=source) if resume else {}
    updated = []
    for item in capabilities:
        current = dict(item)
        status = str(current.get("probe_status") or "")
        if current.get("source") == "computed" or current.get("access_status") == "internal":
            updated.append(current)
            continue
        if current.get("source") == "tushare" and status not in {"", "not_probed", "unknown"}:
            updated.append(current)
            continue
        key = (str(current.get("source", "")), str(current.get("interface", "")))
        result = probe_capability_full_sample(current, dry_run=dry_run, resumed=resume_map.get(key))
        current.update({k: v for k, v in result.items() if v is not None or k in {"elapsed_ms", "row_count"}})
        fields = current.get("sample_probe", {}).get("field_sample") if isinstance(current.get("sample_probe"), dict) else None
        if isinstance(fields, list) and fields:
            current["field_sample"] = [str(field) for field in fields]
        if current.get("probe_status") == "ok":
            current["discovery_status"] = "sample_probed"
        updated.append(current)
    return updated


def _resume_probe_results(*, hub: DataHub | None, source: str) -> dict[tuple[str, str], dict[str, Any]]:
    payload = _read_artifact(_artifact_path(hub, source=source)) or {}
    rows = payload.get("capabilities", []) if isinstance(payload, dict) else []
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("source", "")), str(item.get("interface", "")))
        if key[0] and key[1] and str(item.get("probe_status") or "") not in {"", "not_probed", "planned"}:
            results[key] = item
    return results


def _write_probe_run(
    payload: dict[str, Any],
    *,
    hub: DataHub | None,
    source: str,
    dry_run: bool,
    resume: bool,
    generated_at: str,
) -> dict[str, Any]:
    data_hub = hub or get_datahub()
    run_id = generated_at.replace(":", "").replace("+", "Z").replace(".", "-")
    run_dir = data_hub.artifact_dir("data-sources") / "probe-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{run_id}.json"
    caps = payload.get("capabilities", [])
    probe_rows = [
        {
            "source": item.get("source", ""),
            "interface": item.get("interface", ""),
            "probe_status": item.get("probe_status", ""),
            "probe_contract_id": item.get("probe_contract_id", ""),
            "probe_block_reason": item.get("probe_block_reason", ""),
            "row_count": item.get("row_count"),
            "elapsed_ms": item.get("elapsed_ms"),
            "error_class": item.get("error_class", ""),
        }
        for item in caps
        if isinstance(item, dict)
    ]
    run_payload = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": generated_at,
        "source": source,
        "dry_run": dry_run,
        "resume": resume,
        "summary": payload.get("summary", {}),
        "capabilities": probe_rows,
    }
    path.write_text(json.dumps(run_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {"run_id": run_id, "artifact_path": path.as_posix()}


def _capability_sort_key(item: dict[str, Any]) -> tuple[str, int, str]:
    mapped_rank = 0 if item.get("mapped_dimensions") else 1
    return str(item.get("source", "")), mapped_rank, str(item.get("interface", ""))


def _selected_sources(source: str) -> set[str]:
    if source == "all":
        return set(SOURCE_IDS)
    if source not in SOURCE_IDS:
        raise ValueError(f"Unknown data source: {source}")
    return {source}


def _public_callable_names(module: Any) -> list[str]:
    raw = getattr(module, "__all__", None)
    names = list(raw) if raw else [name for name in dir(module) if not name.startswith("_")]
    return sorted(
        {
            name for name in names
            if callable(getattr(module, name, None)) and not inspect.isclass(getattr(module, name, None))
        }
    )


def _signature(obj: Any) -> str:
    try:
        return str(inspect.signature(obj))
    except Exception:
        return ""


def _doc_summary(obj: Any) -> str:
    doc = inspect.getdoc(obj) or ""
    return doc.splitlines()[0][:240] if doc else ""


def _infer_akshare_taxonomy(name: str) -> tuple[str, str, str]:
    if name in AKSHARE_FREQUENCY_OVERRIDES:
        frequency = AKSHARE_FREQUENCY_OVERRIDES[name]
    else:
        frequency = _infer_frequency(name)
    if name.startswith("stock_"):
        domain = "market_price" if any(part in name for part in ("daily", "hist", "spot", "quote")) else "stock_data"
        if "financial" in name:
            domain = "financial_summary"
        if "money" in name or "fund_flow" in name:
            domain = "capital_flow"
        return "stock", domain, frequency
    if name.startswith("fund_"):
        return "fund", "fund_data", frequency
    if name.startswith("bond_"):
        return "bond", "rate" if "rate" in name else "bond_data", frequency
    if name.startswith(("futures_", "futures", "fut_")):
        return "futures", "market_price", frequency
    if name.startswith("macro_"):
        return "macro", "macro", frequency
    if name.startswith("index_") or "_index_" in name:
        return "index", "market_price", frequency
    if name.startswith("option_"):
        return "option", "derivative", frequency
    if name.startswith("currency_") or name.startswith("fx_"):
        return "forex", "currency", frequency
    return "unknown", "unknown", frequency


def _infer_frequency(name: str) -> str:
    lowered = name.lower()
    if "minute" in lowered or "mins" in lowered:
        return "minute"
    if "daily" in lowered or "hist" in lowered or "_day" in lowered:
        return "daily"
    if "month" in lowered:
        return "monthly"
    if "quarter" in lowered or "season" in lowered:
        return "quarterly"
    return "event"


def _source_rows(capabilities: Iterable[dict[str, Any]], generated_at: str) -> list[dict[str, Any]]:
    caps = list(capabilities)
    by_source = {source: [] for source in SOURCE_IDS}
    for item in caps:
        by_source.setdefault(str(item.get("source", "")), []).append(item)
    rows = []
    for item in source_catalog():
        source_caps = by_source.get(item["source"], [])
        access = Counter(str(cap.get("access_status", "unknown")) for cap in source_caps)
        discovery = Counter(str(cap.get("discovery_status", "discovered")) for cap in source_caps)
        probes = Counter(str(cap.get("probe_status", "not_probed")) for cap in source_caps)
        rows.append(
            {
                **item,
                "capability_count": len(source_caps),
                "integrated_count": sum(1 for cap in source_caps if cap.get("integration_status") == "project_integrated"),
                "unmapped_count": sum(1 for cap in source_caps if not cap.get("mapped_dimensions")),
                "discovered_count": _count_discovery(discovery),
                "sample_probed_count": discovery.get("sample_probed", 0),
                "contracted_count": discovery.get("contracted", 0),
                "project_integrated_count": discovery.get("project_integrated", 0),
                "probe_attempted_count": sum(1 for cap in source_caps if cap.get("probe_attempted_at")),
                "probe_planned_count": probes.get("planned", 0),
                "probe_blocked_count": probes.get("blocked", 0),
                "probe_error_count": probes.get("error", 0),
                "probe_ok_count": probes.get("ok", 0),
                "access_statuses": dict(sorted(access.items())),
                "discovery_statuses": dict(sorted(discovery.items())),
                "probe_statuses": dict(sorted(probes.items())),
                "last_audited_at": generated_at if source_caps else "",
            }
        )
    return rows


def _count_discovery(discovery: Counter[str]) -> int:
    return (
        discovery.get("discovered", 0)
        + discovery.get("sample_probed", 0)
        + discovery.get("contracted", 0)
        + discovery.get("project_integrated", 0)
    )


def _summary(capabilities: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts = Counter(str(item.get("source", "")) for item in capabilities)
    integrated = sum(1 for item in capabilities if item.get("integration_status") == "project_integrated")
    discovery = Counter(str(item.get("discovery_status", "discovered")) for item in capabilities)
    probes = Counter(str(item.get("probe_status", "not_probed")) for item in capabilities)
    probe_attempted = sum(1 for item in capabilities if item.get("probe_attempted_at"))
    return {
        "source_count": len(SOURCE_IDS),
        "audited_source_count": len([source for source, count in source_counts.items() if count]),
        "capability_count": len(capabilities),
        "discovered_count": _count_discovery(discovery),
        "sample_probed_count": discovery.get("sample_probed", 0),
        "contracted_count": discovery.get("contracted", 0),
        "project_integrated_count": discovery.get("project_integrated", 0),
        "integrated_count": integrated,
        "unmapped_count": len(capabilities) - integrated,
        "candidate_count": sum(1 for item in capabilities if item.get("access_status") in {"candidate", "manual_review"}),
        "manual_review_count": sum(
            1
            for item in capabilities
            if item.get("access_status") == "manual_review" or item.get("probe_status") == "manual_review"
        ),
        "requires_token_count": sum(1 for item in capabilities if item.get("requires_token")),
        "probe_attempted_count": probe_attempted,
        "probe_planned_count": probes.get("planned", 0),
        "probe_blocked_count": probes.get("blocked", 0),
        "probe_error_count": probes.get("error", 0),
        "probe_ok_count": probes.get("ok", 0),
        "no_permission_count": probes.get("no_permission", 0),
        "rate_limited_count": probes.get("rate_limited", 0),
        "probe_statuses": dict(sorted(probes.items())),
        "discovery_statuses": dict(sorted(discovery.items())),
        "sources": dict(sorted(source_counts.items())),
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "source_count": len(SOURCE_IDS),
        "audited_source_count": 0,
        "capability_count": 0,
        "discovered_count": 0,
        "sample_probed_count": 0,
        "contracted_count": 0,
        "project_integrated_count": 0,
        "integrated_count": 0,
        "unmapped_count": 0,
        "candidate_count": 0,
        "manual_review_count": 0,
        "requires_token_count": 0,
        "probe_attempted_count": 0,
        "probe_planned_count": 0,
        "probe_blocked_count": 0,
        "probe_error_count": 0,
        "probe_ok_count": 0,
        "no_permission_count": 0,
        "rate_limited_count": 0,
        "probe_statuses": {},
        "discovery_statuses": {},
        "sources": {},
        "artifact_age_seconds": None,
    }


def _empty_diff() -> dict[str, Any]:
    return {
        "summary": {
            "capability_unmapped_count": 0,
            "registry_missing_source_count": 0,
            "field_frequency_mismatch_count": 0,
        },
        "capability_unmapped": [],
        "registry_missing_source": [],
        "field_frequency_mismatch": [],
    }


def _normalize_payload(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    normalized = dict(payload)
    raw_capabilities = normalized.get("capabilities", [])
    capabilities = [
        _capability(**item)
        for item in raw_capabilities
        if isinstance(item, dict)
    ]
    summary = normalized.get("summary") if isinstance(normalized.get("summary"), dict) else {}
    normalized["capabilities"] = capabilities
    normalized["summary"] = {
        **_empty_summary(),
        **_summary(capabilities),
        **summary,
        "artifact_age_seconds": _artifact_age_seconds(normalized),
    }
    normalized["sources"] = _source_rows(capabilities, str(normalized.get("generated_at", "")))
    normalized.setdefault("diff", _empty_diff())
    normalized.setdefault("errors", [])
    normalized["latest"] = {
        "generated_at": normalized.get("generated_at"),
        "artifact_path": path.as_posix(),
    }
    normalized["recommended_command"] = str(normalized.get("recommended_command") or RECOMMENDED_AUDIT_COMMAND)
    return normalized


def _artifact_path(hub: DataHub | None = None, *, source: str = "all") -> Path:
    name = "latest.json" if source == "all" else f"latest-{source}.json"
    return (hub or get_datahub()).artifact_path("data-sources", name)


def _read_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _artifact_age_seconds(payload: dict[str, Any]) -> float | None:
    generated_at = str(payload.get("generated_at") or "")
    if not generated_at:
        return None
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - dt).total_seconds(), 3)


def _dimension_row(item: DataDimension | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            "key": str(item.get("key", "")),
            "source": str(item.get("source", "")),
            "freq": str(item.get("freq", "")),
            "status": str(item.get("status", "")),
        }
    return {"key": item.key, "source": item.source, "freq": item.freq, "status": item.status}


def _normalize_registry_source(source: str) -> str:
    if source in {"tushare_free", "tushare_paid"}:
        return "tushare"
    return source


def provider_dimension_map() -> dict[str, list[str]]:
    """Expose current provider-to-dimension mappings for audits and tests."""
    return {
        "akshare": sorted(AKShareAdapter()._supported_keys()),
        "tushare": sorted(TushareAdapter()._supported_keys()),
    }
