from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATA_SOURCE_WORDING_RULES = [
    "Do not call discovered capabilities integrated unless project_integrated_count includes them.",
    "Do not call sample_probed capabilities production-ready.",
    "Candidate sources are discovered or under manual review, not production-integrated sources.",
    "Data source discovered/sample/candidate statuses are not production integration.",
]


def build_tool_result_context(
    *,
    action_context: list[dict[str, Any]],
    dispatch_result: dict[str, Any],
) -> dict[str, Any]:
    """Build bounded provider facts from fixed-tool runs.

    The returned object is for LLM grounding only. It is not a user-facing
    response template and should not decide wording beyond explicit fact rules.
    """

    contexts: list[dict[str, Any]] = []
    action_by_id = {str(row.get("action_id") or ""): row for row in action_context if isinstance(row, dict)}
    for run in dispatch_result.get("runs") if isinstance(dispatch_result.get("runs"), list) else []:
        if not isinstance(run, dict):
            continue
        action_id = str(run.get("action_id") or "")
        action = action_by_id.get(action_id, {})
        tool_id = _tool_id_for_run(run, action)
        item = _context_for_tool(tool_id=tool_id, action=action, run=run)
        if item:
            contexts.append(item)
    return {
        "context_count": len(contexts),
        "items": contexts[:12],
    }


def _tool_id_for_run(run: dict[str, Any], action: dict[str, Any]) -> str:
    spec = action.get("spec") if isinstance(action.get("spec"), dict) else {}
    parameters = spec.get("parameters") if isinstance(spec.get("parameters"), dict) else {}
    return str(parameters.get("tool_id") or spec.get("tool_id") or run.get("tool_name") or "")


def _context_for_tool(*, tool_id: str, action: dict[str, Any], run: dict[str, Any]) -> dict[str, Any] | None:
    base = {
        "tool_id": tool_id,
        "action_id": str(run.get("action_id") or action.get("action_id") or ""),
        "run_id": str(run.get("run_id") or ""),
        "run_status": str(run.get("status") or ""),
        "return_code": run.get("return_code"),
    }
    if tool_id == "astroq.data.sources":
        return {
            **base,
            "kind": "data_source_capability_summary",
            "facts": _data_sources_facts(),
            "wording_rules": list(DATA_SOURCE_WORDING_RULES),
        }
    if tool_id == "astroq.assets.overview":
        return {
            **base,
            "kind": "asset_chain_summary",
            "facts": _asset_overview_facts(),
            "wording_rules": [
                "Enabled asset switches do not imply strategy, paper, or live trading readiness.",
                "Live status must be reported from live_status/blockers only; do not infer live readiness from tradable.",
                "Crypto with stale data is not strategy-ready or trade-ready.",
                "Treasury yield proxies are research inputs, not directly tradable instruments.",
            ],
        }
    return None


def _data_sources_facts() -> dict[str, Any]:
    path = _data_sources_artifact_path()
    if not path.exists():
        return {
            "status": "missing_artifact",
            "artifact_path": str(path),
            "recommended_command": "astroq data sources audit --source all --discovery-depth catalog --json",
            "sources": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid_artifact",
            "artifact_path": str(path),
            "error_class": type(exc).__name__,
            "sources": [],
        }
    if not isinstance(payload, dict):
        return {
            "status": "invalid_artifact",
            "artifact_path": str(path),
            "error_class": "NonObjectArtifact",
            "sources": [],
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    source_rows = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    bounded_sources = [_source_fact(row) for row in source_rows if isinstance(row, dict)]
    return {
        "status": str(payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "generated_at": str(payload.get("generated_at") or ""),
        "recommended_command": str(
            payload.get("recommended_command") or "astroq data sources audit --source all --discovery-depth catalog --json"
        ),
        "source_count": _int(summary.get("source_count"), default=len(bounded_sources)),
        "capability_count": _int(summary.get("capability_count")),
        "discovered_count": _int(summary.get("discovered_count")),
        "project_integrated_count": _int(summary.get("project_integrated_count")),
        "candidate_count": _int(summary.get("candidate_count"), default=_candidate_count(bounded_sources)),
        "sample_probed_count": _int(summary.get("sample_probed_count")),
        "sources": bounded_sources[:20],
    }


def _data_sources_artifact_path() -> Path:
    from data.storage.datahub import get_datahub

    return get_datahub().artifact_path("data-sources", "latest.json")


def _asset_overview_facts() -> dict[str, Any]:
    from data.market.assets.overview import asset_overview_items

    items = asset_overview_items()
    return {
        "status": "ok",
        "asset_count": len(items),
        "ready_counts": {
            "data": sum(1 for item in items if item.get("data_status") == "ready"),
            "strategy": sum(1 for item in items if item.get("strategy_status") == "ready"),
            "backtest": sum(1 for item in items if item.get("backtest_status") == "ready"),
            "paper": sum(1 for item in items if item.get("paper_status") == "ready"),
            "live": sum(1 for item in items if item.get("live_status") in {"ready", "validated"}),
        },
        "assets": [
            {
                "asset_type": str(item.get("asset_type") or ""),
                "label": str(item.get("label") or item.get("asset_type") or ""),
                "enabled": bool(item.get("enabled")),
                "data_status": str(item.get("data_status") or "blocked"),
                "strategy_status": str(item.get("strategy_status") or "blocked"),
                "backtest_status": str(item.get("backtest_status") or "blocked"),
                "paper_status": str(item.get("paper_status") or "blocked"),
                "live_status": str(item.get("live_status") or "blocked"),
                "live_adapter": str(item.get("live_adapter") or ""),
                "blockers": [str(blocker) for blocker in item.get("blockers", [])],
            }
            for item in items
        ],
    }


def _source_fact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": str(row.get("source") or ""),
        "label": str(row.get("label") or row.get("source") or ""),
        "status": str(row.get("status") or "unknown"),
        "capability_count": _int(row.get("capability_count")),
        "discovered_count": _int(row.get("discovered_count")),
        "project_integrated_count": _int(row.get("project_integrated_count")),
        "sample_probed_count": _int(row.get("sample_probed_count")),
        "requires_token": bool(row.get("requires_token")),
    }


def _candidate_count(sources: list[dict[str, Any]]) -> int:
    return sum(1 for source in sources if str(source.get("status") or "") == "candidate")


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
