from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_os.schemas import AgentReport


REPORT_KIND_ALIASES = {
    "daily": "daily_brief",
    "daily_brief": "daily_brief",
    "weekly": "weekly_review",
    "weekly_review": "weekly_review",
    "audit": "audit_pack",
    "audit_pack": "audit_pack",
    "data_quality": "data_quality_review",
    "data_quality_review": "data_quality_review",
    "risk": "risk_review",
    "risk_review": "risk_review",
    "execution": "execution_reconciliation",
    "execution_reconciliation": "execution_reconciliation",
    "engineering": "engineering_digest",
    "engineering_digest": "engineering_digest",
    "release": "release_audit",
    "release_audit": "release_audit",
}

REPORT_TITLES = {
    "daily_brief": "Daily CEO Brief",
    "weekly_review": "Weekly Research Review",
    "audit_pack": "Agent Audit Pack",
    "data_quality_review": "Data Quality Review",
    "risk_review": "Risk Review",
    "execution_reconciliation": "Execution Reconciliation",
    "engineering_digest": "Engineering Digest",
    "release_audit": "Release Audit",
}


@dataclass(frozen=True)
class ReportArtifactSource:
    key: str
    title: str
    relative_path: str


REPORT_ARTIFACT_SOURCES = [
    ReportArtifactSource("lifecycle", "Lifecycle Readiness", "lifecycle/latest.json"),
    ReportArtifactSource("data_sources", "Data Source Capabilities", "data-sources/latest.json"),
    ReportArtifactSource("strategy_competition", "Strategy Competition", "tournaments/strategy_competition_latest.json"),
    ReportArtifactSource("ast_intelligence", "AST Intelligence", "architecture/ast/latest.json"),
    ReportArtifactSource("test_design", "Test Design Intelligence", "tests/design/latest.json"),
    ReportArtifactSource("codegraph", "CodeGraph Index", "architecture/codegraph/latest.json"),
]


REPORT_RHYTHM_TEMPLATES = [
    {"kind": "daily_brief", "cadence": "daily", "interval_hours": 24},
    {"kind": "data_quality_review", "cadence": "daily", "interval_hours": 24},
    {"kind": "risk_review", "cadence": "daily", "interval_hours": 24},
    {"kind": "execution_reconciliation", "cadence": "daily", "interval_hours": 24},
    {"kind": "weekly_review", "cadence": "weekly", "interval_hours": 168},
    {"kind": "engineering_digest", "cadence": "weekly", "interval_hours": 168},
    {"kind": "audit_pack", "cadence": "weekly", "interval_hours": 168},
    {"kind": "release_audit", "cadence": "weekly", "interval_hours": 168},
]


def normalize_report_kind(kind: str) -> str:
    normalized = REPORT_KIND_ALIASES.get(kind.strip().lower())
    if not normalized:
        raise ValueError(f"Unsupported agent report kind: {kind}")
    return normalized


def report_title(kind: str) -> str:
    return REPORT_TITLES[normalize_report_kind(kind)]


def report_rhythm_templates() -> list[dict[str, Any]]:
    return [
        {
            **template,
            "title": report_title(str(template["kind"])),
        }
        for template in REPORT_RHYTHM_TEMPLATES
    ]


def build_report_payload(
    *,
    report_id: str,
    session: dict[str, Any],
    messages: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    work_orders: list[dict[str, Any]] | None = None,
    kind: str,
    path: Path,
    markdown_path: Path,
    generated_at: str,
    artifact_context: dict[str, Any] | None = None,
    report_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_kind = normalize_report_kind(kind)
    artifact_context = dict(artifact_context or empty_report_artifact_context())
    artifact_context["trend_synthesis"] = _report_trend_synthesis(artifact_context, report_history or [])
    artifact_context["causal_chain_synthesis"] = _report_causal_chain_synthesis(artifact_context)
    work_order_rows = list(work_orders or [])
    evidence_by_id = {str(row.get("evidence_id")): row for row in evidence}
    evidence_refs = _ordered_unique(
        [
            *[ref for row in messages for ref in row.get("evidence_refs", [])],
            *[ref for row in actions for ref in row.get("evidence_refs", [])],
            *[ref for row in handoffs for ref in row.get("evidence_refs", [])],
            *[ref for row in work_order_rows for ref in row.get("evidence_refs", [])],
            *[ref for row in runs for ref in row.get("artifact_refs", [])],
        ]
    )
    missing_evidence = [ref for ref in evidence_refs if ref not in evidence_by_id]
    recent_messages = messages[-5:]
    open_handoffs = [row for row in handoffs if row.get("status") == "open"]
    open_work_orders = [row for row in work_order_rows if row.get("status") == "open"]
    active_actions = [row for row in actions if row.get("status") in {"proposed", "approval_required", "approved", "running"}]
    summary = (
        f"{len(recent_messages)} recent message(s), {len(active_actions)} active action(s), "
        f"{len(open_work_orders)} open work order(s), "
        f"{len(open_handoffs)} open handoff(s), {len(evidence_refs)} evidence reference(s)."
    )
    sections = [
        {
            "section_id": "session_summary",
            "title": "Session Summary",
            "body": summary,
            "evidence_refs": evidence_refs,
        },
        {
            "section_id": "recent_messages",
            "title": "Recent Desk Notes",
            "body": "\n".join(_message_line(row) for row in recent_messages) or "No recent messages.",
            "evidence_refs": _ordered_unique([ref for row in recent_messages for ref in row.get("evidence_refs", [])]),
        },
        {
            "section_id": "open_work",
            "title": "Open Work",
            "body": _open_work_body(active_actions, open_handoffs, open_work_orders),
            "evidence_refs": _ordered_unique(
                [
                    *[ref for row in active_actions for ref in row.get("evidence_refs", [])],
                    *[ref for row in open_handoffs for ref in row.get("evidence_refs", [])],
                    *[ref for row in open_work_orders for ref in row.get("evidence_refs", [])],
                ]
            ),
        },
        {
            "section_id": "artifact_readiness",
            "title": "Artifact Readiness",
            "body": _artifact_readiness_body(artifact_context),
            "evidence_refs": [],
        },
        {
            "section_id": "artifact_findings",
            "title": "Artifact Findings",
            "body": _artifact_findings_body(artifact_context),
            "evidence_refs": [],
        },
        {
            "section_id": "semantic_synthesis",
            "title": "Semantic Synthesis",
            "body": _semantic_synthesis_body(artifact_context),
            "evidence_refs": [],
        },
        {
            "section_id": "trend_synthesis",
            "title": "Trend Synthesis",
            "body": _trend_synthesis_body(artifact_context),
            "evidence_refs": [],
        },
        {
            "section_id": "causal_chain_synthesis",
            "title": "Causal Chain Synthesis",
            "body": _causal_chain_synthesis_body(artifact_context),
            "evidence_refs": [],
        },
    ]
    sections.extend(
        _operating_rhythm_sections(
            kind=normalized_kind,
            messages=messages,
            actions=actions,
            runs=runs,
            handoffs=handoffs,
            work_orders=work_order_rows,
            evidence=evidence,
            evidence_refs=evidence_refs,
        )
    )
    if missing_evidence:
        sections.append(
            {
                "section_id": "missing_evidence",
                "title": "Missing Evidence",
                "body": ", ".join(missing_evidence),
                "evidence_refs": [],
            }
        )

    return AgentReport(
        report_id=report_id,
        session_id=str(session["session_id"]),
        kind=normalized_kind,
        title=report_title(normalized_kind),
        summary=summary,
        path=str(path),
        markdown_path=str(markdown_path),
        evidence_id="",
        evidence_refs=evidence_refs,
        missing_evidence=missing_evidence,
        artifact_context=artifact_context,
        sections=sections,
        generated_at=generated_at,
    ).to_dict()


def empty_report_artifact_context() -> dict[str, Any]:
    return {
        "available_count": 0,
        "missing_count": len(REPORT_ARTIFACT_SOURCES),
        "invalid_count": 0,
        "synthesis": {
            "status": "missing",
            "root_cause_count": 0,
            "root_causes": [],
            "impacts": [],
            "next_actions": ["Generate lifecycle, data-source, strategy, architecture, test-design, and CodeGraph artifacts."],
        },
        "trend_synthesis": {
            "status": "no_history",
            "history_report_count": 0,
            "recurring_root_cause_count": 0,
            "recurring_root_causes": [],
            "next_actions": ["Generate at least one prior CEO report before evaluating cross-session trends."],
        },
        "causal_chain_synthesis": {
            "status": "no_evidence",
            "chain_count": 0,
            "recurring_chain_count": 0,
            "chains": [],
            "next_actions": ["Generate report evidence artifacts before building causal chains."],
        },
        "items": [
            {
                "key": source.key,
                "title": source.title,
                "status": "missing",
                "relative_path": source.relative_path,
                "path": "",
                "summary": {},
                "findings": [],
            }
            for source in REPORT_ARTIFACT_SOURCES
        ],
    }


def collect_report_artifact_context(artifact_root: Path | None = None) -> dict[str, Any]:
    """Collect a fixed local artifact context for CEO reports.

    The source list is intentionally static. Reports should surface the current
    system evidence state, but they must not scan arbitrary directories or call
    provider/network APIs while rendering.
    """

    root = artifact_root
    if root is None:
        from data.storage.datahub import get_datahub

        root = get_datahub().artifact_dir("lifecycle").parent
    items = [_collect_artifact_item(root, source) for source in REPORT_ARTIFACT_SOURCES]
    context = {
        "available_count": sum(1 for item in items if item["status"] == "available"),
        "missing_count": sum(1 for item in items if item["status"] == "missing"),
        "invalid_count": sum(1 for item in items if item["status"] == "invalid"),
        "items": items,
    }
    context["synthesis"] = _artifact_semantic_synthesis(context)
    return context


def _collect_artifact_item(root: Path, source: ReportArtifactSource) -> dict[str, Any]:
    path = root / source.relative_path
    base = {
        "key": source.key,
        "title": source.title,
        "relative_path": source.relative_path,
        "path": str(path),
        "summary": {},
        "findings": [],
    }
    if not path.exists():
        return {
            **base,
            "status": "missing",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            **base,
            "status": "invalid",
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            **base,
            "status": "invalid",
            "error": "artifact root must be a JSON object",
        }
    return {
        **base,
        "status": "available",
        "summary": _artifact_summary(payload),
        "findings": _artifact_findings(payload),
    }


def _artifact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if isinstance(summary, dict):
        return _bounded_mapping(summary, limit=10)
    selected: dict[str, Any] = {}
    for key in ("status", "ok", "total", "checked_at", "generated_at", "updated_at"):
        if key in payload:
            selected[key] = payload[key]
    return _bounded_mapping(selected, limit=10)


def _artifact_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for key in ("blockers", "issues", "smells", "design_risks", "risks", "failures", "warnings"):
        value = payload.get(key)
        if isinstance(value, list):
            for row in value[:6]:
                findings.append({"kind": key, "evidence": _bounded_value(row)})
    return findings[:12]


def _bounded_mapping(values: dict[str, Any], *, limit: int) -> dict[str, Any]:
    bounded: dict[str, Any] = {}
    for index, (key, value) in enumerate(values.items()):
        if index >= limit:
            bounded["omitted_keys"] = max(0, len(values) - limit)
            break
        bounded[str(key)] = _bounded_value(value)
    return bounded


def _bounded_value(value: Any, *, limit: int = 400) -> Any:
    if isinstance(value, dict):
        return _bounded_mapping(value, limit=8)
    if isinstance(value, list):
        return [_bounded_value(item, limit=limit) for item in value[:5]]
    text = str(value)
    if isinstance(value, str):
        return text if len(text) <= limit else text[:limit] + "...[truncated]"
    return value


def _artifact_readiness_body(artifact_context: dict[str, Any]) -> str:
    lines = [
        (
            f"- Artifact coverage: {artifact_context.get('available_count', 0)} available, "
            f"{artifact_context.get('missing_count', 0)} missing, {artifact_context.get('invalid_count', 0)} invalid."
        )
    ]
    for item in artifact_context.get("items", []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        relative_path = str(item.get("relative_path") or "")
        line = f"- {item.get('key')}: {status} - {relative_path}"
        summary = item.get("summary")
        if status == "available" and isinstance(summary, dict) and summary:
            line += f" - summary={_compact_json(summary)}"
        error = item.get("error")
        if error:
            line += f" - error={error}"
        lines.append(line)
    return "\n".join(lines)


def _artifact_findings_body(artifact_context: dict[str, Any]) -> str:
    lines: list[str] = []
    for item in artifact_context.get("items", []):
        if not isinstance(item, dict) or item.get("status") != "available":
            continue
        findings = item.get("findings") or []
        if not findings:
            continue
        for finding in findings[:5]:
            lines.append(f"- {item.get('key')}: {_compact_json(finding)}")
    return "\n".join(lines) if lines else "No blocker, issue, risk, failure, or warning findings were available in local artifacts."


def _artifact_semantic_synthesis(artifact_context: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in artifact_context.get("items", []) if isinstance(item, dict)]
    by_key = {str(item.get("key") or ""): item for item in items}
    root_causes: list[dict[str, str]] = []
    impacts: list[str] = []
    next_actions: list[str] = []

    lifecycle = by_key.get("lifecycle")
    if lifecycle and lifecycle.get("status") == "available":
        for finding in lifecycle.get("findings", [])[:3]:
            if not isinstance(finding, dict):
                continue
            if str(finding.get("kind") or "") != "blockers":
                continue
            evidence = _compact_json(finding.get("evidence"), limit=240)
            root_causes.append(
                {
                    "cause": "lifecycle_blocker",
                    "evidence": evidence,
                    "recommendation": "Resolve lifecycle blockers before promoting strategies, trading, or treating reports as ready.",
                }
            )
            next_actions.append("Run the lifecycle blocker repair path and regenerate `astroq lifecycle check --json`.")

    data_sources = by_key.get("data_sources")
    if data_sources and data_sources.get("status") == "available":
        summary = data_sources.get("summary") if isinstance(data_sources.get("summary"), dict) else {}
        capability_count = _int_value(summary.get("capability_count"))
        integrated_count = _int_value(summary.get("project_integrated_count"))
        unmapped_count = _int_value(summary.get("capability_unmapped_count"))
        if capability_count > integrated_count or unmapped_count > 0:
            root_causes.append(
                {
                    "cause": "data_source_gap",
                    "evidence": f"{integrated_count}/{capability_count} capabilities integrated; {unmapped_count} unmapped.",
                    "recommendation": "Review Source Capability Registry diff before claiming data coverage is complete.",
                }
            )
            next_actions.append("Run `astroq data sources diff-registry --json` and prioritize unmapped production dimensions.")

    strategy = by_key.get("strategy_competition")
    if strategy and strategy.get("status") == "available":
        summary = strategy.get("summary") if isinstance(strategy.get("summary"), dict) else {}
        blocked = _int_value(summary.get("blocked")) + _int_value(summary.get("invalid_count")) + _int_value(summary.get("error_count"))
        if blocked > 0:
            root_causes.append(
                {
                    "cause": "strategy_evidence_blocked",
                    "evidence": _compact_json(summary, limit=240),
                    "recommendation": "Do not promote strategy layers until missing alpha/OOS/backtest evidence is regenerated.",
                }
            )
            impacts.append(f"{blocked} strategy evidence item(s) are blocked or invalid.")
            next_actions.append("Regenerate strategy competition evidence after data and lifecycle blockers are closed.")

    ast_item = by_key.get("ast_intelligence")
    if ast_item and ast_item.get("status") == "available":
        summary = ast_item.get("summary") if isinstance(ast_item.get("summary"), dict) else {}
        issue_count = _int_value(summary.get("issue_count"))
        if issue_count > 0:
            root_causes.append(
                {
                    "cause": "engineering_quality_risk",
                    "evidence": _compact_json(summary, limit=240),
                    "recommendation": "Open Engineering Desk work orders for real architecture or duplicate-implementation risks.",
                }
            )

    test_design = by_key.get("test_design")
    if test_design and test_design.get("status") == "available":
        summary = test_design.get("summary") if isinstance(test_design.get("summary"), dict) else {}
        design_risk_count = _int_value(summary.get("design_risk_count")) + _int_value(summary.get("smell_count"))
        if design_risk_count > 0:
            root_causes.append(
                {
                    "cause": "test_design_risk",
                    "evidence": _compact_json(summary, limit=240),
                    "recommendation": "Review high-severity test design risks before relying on green test runs alone.",
                }
            )

    missing_count = _int_value(artifact_context.get("missing_count"))
    invalid_count = _int_value(artifact_context.get("invalid_count"))
    if missing_count or invalid_count:
        impacts.append(f"{missing_count} evidence artifact(s) are missing and {invalid_count} are invalid.")
        next_actions.append("Regenerate missing local intelligence artifacts before distributing the report.")

    if any(row["cause"] in {"lifecycle_blocker", "strategy_evidence_blocked"} for row in root_causes):
        status = "blocked"
    elif root_causes or invalid_count:
        status = "attention"
    elif missing_count:
        status = "partial"
    else:
        status = "ready"

    return {
        "status": status,
        "root_cause_count": len(root_causes),
        "root_causes": root_causes[:8],
        "impacts": _ordered_unique(impacts)[:8],
        "next_actions": _ordered_unique(next_actions)[:8],
    }


def _semantic_synthesis_body(artifact_context: dict[str, Any]) -> str:
    synthesis = artifact_context.get("synthesis")
    if not isinstance(synthesis, dict):
        synthesis = _artifact_semantic_synthesis(artifact_context)
    lines = [
        f"- Synthesis status: {synthesis.get('status', 'unknown')}",
        f"- Root causes: {synthesis.get('root_cause_count', 0)}",
    ]
    for root_cause in synthesis.get("root_causes", [])[:8]:
        if not isinstance(root_cause, dict):
            continue
        lines.append(
            "- "
            f"{root_cause.get('cause')}: {root_cause.get('evidence')} "
            f"-> {root_cause.get('recommendation')}"
        )
    for impact in synthesis.get("impacts", [])[:5]:
        lines.append(f"- Impact: {impact}")
    for action in synthesis.get("next_actions", [])[:5]:
        lines.append(f"- Next action: {action}")
    return "\n".join(lines)


def _report_trend_synthesis(
    artifact_context: dict[str, Any],
    report_history: list[dict[str, Any]],
) -> dict[str, Any]:
    history = [report for report in report_history if isinstance(report, dict)]
    current_causes = _root_cause_names(artifact_context)
    if not history:
        return {
            "status": "no_history",
            "history_report_count": 0,
            "recurring_root_cause_count": 0,
            "recurring_root_causes": [],
            "next_actions": ["Generate at least one prior CEO report before evaluating cross-session trends."],
        }

    previous: dict[str, dict[str, Any]] = {}
    for report in history[:20]:
        context = report.get("artifact_context") if isinstance(report.get("artifact_context"), dict) else {}
        for cause in _root_cause_names(context):
            row = previous.setdefault(
                cause,
                {
                    "cause": cause,
                    "previous_count": 0,
                    "latest_report_id": str(report.get("report_id") or ""),
                    "latest_generated_at": str(report.get("generated_at") or ""),
                    "kinds": [],
                },
            )
            row["previous_count"] += 1
            kind = str(report.get("kind") or "")
            if kind and kind not in row["kinds"]:
                row["kinds"].append(kind)

    recurring: list[dict[str, Any]] = []
    for cause in current_causes:
        row = previous.get(cause)
        if not row:
            continue
        previous_count = int(row["previous_count"])
        recurring.append(
            {
                "cause": cause,
                "previous_count": previous_count,
                "total_count": previous_count + 1,
                "latest_report_id": row["latest_report_id"],
                "latest_generated_at": row["latest_generated_at"],
                "kinds": row["kinds"][:5],
                "recommendation": "Escalate repeated root causes into an owner-specific desk action or work order.",
            }
        )

    status = "attention" if recurring else "ready"
    next_actions = [
        "Open recurring blockers as Data/Research/Risk/Engineering desk actions instead of repeating report-only observations."
    ] if recurring else ["No repeated root causes were found in recent report history."]
    return {
        "status": status,
        "history_report_count": len(history),
        "current_root_cause_count": len(current_causes),
        "recurring_root_cause_count": len(recurring),
        "recurring_root_causes": recurring[:8],
        "next_actions": next_actions,
    }


def _trend_synthesis_body(artifact_context: dict[str, Any]) -> str:
    trend = artifact_context.get("trend_synthesis")
    if not isinstance(trend, dict):
        trend = _report_trend_synthesis(artifact_context, [])
    lines = [
        f"- Trend status: {trend.get('status', 'unknown')}",
        f"- History reports: {trend.get('history_report_count', 0)}",
        f"- Recurring root causes: {trend.get('recurring_root_cause_count', 0)}",
    ]
    for recurring in trend.get("recurring_root_causes", [])[:8]:
        if not isinstance(recurring, dict):
            continue
        lines.append(
            "- "
            f"Repeated root cause: {recurring.get('cause')} appeared in "
            f"{recurring.get('total_count')} report(s); latest={recurring.get('latest_report_id')} "
            f"-> {recurring.get('recommendation')}"
        )
    for action in trend.get("next_actions", [])[:5]:
        lines.append(f"- Next action: {action}")
    return "\n".join(lines)


def _report_causal_chain_synthesis(artifact_context: dict[str, Any]) -> dict[str, Any]:
    synthesis = artifact_context.get("synthesis")
    if not isinstance(synthesis, dict):
        synthesis = _artifact_semantic_synthesis(artifact_context)
    root_causes = [row for row in synthesis.get("root_causes", []) or [] if isinstance(row, dict)]
    cause_names = _root_cause_names({"synthesis": synthesis})
    cause_set = set(cause_names)
    chains: list[dict[str, Any]] = []

    if {"lifecycle_blocker", "strategy_evidence_blocked"}.issubset(cause_set):
        nodes = []
        if "data_source_gap" in cause_set:
            nodes.append("data_source_gap")
        nodes.extend(["lifecycle_blocker", "strategy_evidence_blocked"])
        chains.append(
            {
                "chain_id": "data_readiness_to_strategy_block",
                "severity": "P0",
                "status": "blocked",
                "nodes": nodes,
                "owner_desks": ["data", "research", "risk"],
                "evidence": _chain_evidence(root_causes, nodes),
                "impact": "Strategy promotion, paper execution, and live execution must remain blocked until data readiness and alpha evidence are regenerated.",
                "next_action": (
                    "Do not promote or trade affected strategies; run data repair/source-diff checks, "
                    "then regenerate lifecycle and strategy competition evidence."
                ),
            }
        )

    if "data_source_gap" in cause_set and "lifecycle_blocker" in cause_set:
        chains.append(
            {
                "chain_id": "source_capability_to_lifecycle_block",
                "severity": "P1",
                "status": "attention",
                "nodes": ["data_source_gap", "lifecycle_blocker"],
                "owner_desks": ["data", "risk"],
                "evidence": _chain_evidence(root_causes, ["data_source_gap", "lifecycle_blocker"]),
                "impact": "Local readiness cannot prove completeness while source capabilities remain unmapped or stale.",
                "next_action": "Resolve source capability diff before relaxing lifecycle gates.",
            }
        )

    if "engineering_quality_risk" in cause_set or "test_design_risk" in cause_set:
        nodes = [node for node in ("engineering_quality_risk", "test_design_risk") if node in cause_set]
        chains.append(
            {
                "chain_id": "engineering_quality_to_release_risk",
                "severity": "P1",
                "status": "attention",
                "nodes": nodes,
                "owner_desks": ["engineering", "reporting"],
                "evidence": _chain_evidence(root_causes, nodes),
                "impact": "Release confidence is reduced when architecture or test-design evidence carries unresolved risks.",
                "next_action": "Open Engineering Desk work orders and rerun AST/test-design diagnostics after remediation.",
            }
        )

    chains, recurring_chain_count = _apply_causal_chain_history(chains, artifact_context)

    if any(chain["severity"] == "P0" for chain in chains):
        status = "blocked"
    elif chains:
        status = "attention"
    elif cause_names:
        status = "ready"
    else:
        status = "no_evidence"
    return {
        "status": status,
        "chain_count": len(chains),
        "recurring_chain_count": recurring_chain_count,
        "chains": chains[:8],
        "next_actions": _ordered_unique([str(chain["next_action"]) for chain in chains])[:8]
        or ["No causal chains were found in current local artifacts."],
    }


def _apply_causal_chain_history(
    chains: list[dict[str, Any]],
    artifact_context: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    trend = artifact_context.get("trend_synthesis")
    recurring_rows = trend.get("recurring_root_causes", []) if isinstance(trend, dict) else []
    recurring_by_cause = {
        str(row.get("cause") or ""): row
        for row in recurring_rows
        if isinstance(row, dict) and str(row.get("cause") or "")
    }
    recurring_chain_count = 0
    updated: list[dict[str, Any]] = []
    for chain in chains:
        nodes = [str(node) for node in chain.get("nodes", []) if node]
        matches = [recurring_by_cause[node] for node in nodes if node in recurring_by_cause]
        if not matches:
            updated.append(
                {
                    **chain,
                    "escalation": "current_evidence",
                    "history": {
                        "recurring": False,
                        "recurring_causes": [],
                        "max_total_count": 1,
                    },
                }
            )
            continue

        recurring_chain_count += 1
        max_total_count = max(_int_value(row.get("total_count")) for row in matches)
        latest = matches[0]
        escalation = "recurring_blocker" if chain.get("severity") == "P0" or chain.get("status") == "blocked" else "recurring_attention"
        next_action = (
            "Escalate recurring causal chain to standing owner review before repeating report-only observations; "
            f"{chain.get('next_action')}"
        )
        updated.append(
            {
                **chain,
                "escalation": escalation,
                "history": {
                    "recurring": True,
                    "recurring_causes": [str(row.get("cause") or "") for row in matches],
                    "max_total_count": max_total_count,
                    "latest_report_id": str(latest.get("latest_report_id") or ""),
                    "latest_generated_at": str(latest.get("latest_generated_at") or ""),
                    "kinds": _ordered_unique([kind for row in matches for kind in row.get("kinds", [])])[:5],
                },
                "next_action": next_action,
            }
        )
    return updated, recurring_chain_count


def _causal_chain_synthesis_body(artifact_context: dict[str, Any]) -> str:
    causal = artifact_context.get("causal_chain_synthesis")
    if not isinstance(causal, dict):
        causal = _report_causal_chain_synthesis(artifact_context)
    lines = [
        "- Section: causal_chain_synthesis",
        f"- Causal status: {causal.get('status', 'unknown')}",
        f"- Causal chains: {causal.get('chain_count', 0)}",
        f"- Recurring causal chains: {causal.get('recurring_chain_count', 0)}",
    ]
    for chain in causal.get("chains", [])[:8]:
        if not isinstance(chain, dict):
            continue
        nodes = " -> ".join(str(node) for node in chain.get("nodes", []) if node)
        owners = ", ".join(str(desk) for desk in chain.get("owner_desks", []) if desk)
        lines.append(
            "- "
            f"{chain.get('chain_id')}: {chain.get('severity')} / {chain.get('status')} "
            f"({nodes}); owners={owners}; evidence={chain.get('evidence')} "
            f"-> {chain.get('next_action')}"
        )
        history = chain.get("history") if isinstance(chain.get("history"), dict) else {}
        if history.get("recurring"):
            causes = ", ".join(str(cause) for cause in history.get("recurring_causes", []) if cause)
            lines.append(
                "- "
                f"Recurring causal chain: {chain.get('chain_id')} repeated via {causes} across "
                f"{history.get('max_total_count')} report(s); latest={history.get('latest_report_id')}; "
                f"escalation={chain.get('escalation')}"
            )
    for action in causal.get("next_actions", [])[:5]:
        lines.append(f"- Next action: {action}")
    return "\n".join(lines)


def _root_cause_names(artifact_context: dict[str, Any]) -> list[str]:
    synthesis = artifact_context.get("synthesis")
    if not isinstance(synthesis, dict):
        return []
    names: list[str] = []
    for row in synthesis.get("root_causes", []) or []:
        if not isinstance(row, dict):
            continue
        cause = str(row.get("cause") or "").strip()
        if cause and cause not in names:
            names.append(cause)
    return names


def _chain_evidence(root_causes: list[dict[str, Any]], nodes: list[str]) -> str:
    evidence = [
        str(row.get("evidence") or "").strip()
        for row in root_causes
        if str(row.get("cause") or "") in set(nodes) and str(row.get("evidence") or "").strip()
    ]
    return " | ".join(_ordered_unique(evidence))[:1000] or "No direct evidence text available."


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _compact_json(value: Any, *, limit: int = 500) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['title']}",
        "",
        f"- Report ID: `{report['report_id']}`",
        f"- Session ID: `{report['session_id']}`",
        f"- Generated At: `{report['generated_at']}`",
        f"- Evidence Refs: {', '.join(report.get('evidence_refs') or []) or 'none'}",
        "",
    ]
    for section in report.get("sections", []):
        lines.extend(
            [
                f"## {section['title']}",
                "",
                str(section.get("body") or ""),
                "",
                f"Evidence: {', '.join(section.get('evidence_refs') or []) or 'none'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def read_report_index(index_path: Path) -> list[dict[str, Any]]:
    if not index_path.exists():
        return []
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    return [dict(row) for row in payload.get("reports", [])]


def write_report_index(index_path: Path, reports: list[dict[str, Any]]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps({"reports": reports}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _message_line(row: dict[str, Any]) -> str:
    content = str(row.get("content") or "").strip().replace("\n", " ")
    if len(content) > 280:
        content = content[:280] + "..."
    return f"- {row.get('desk')} / {row.get('role')}: {content}"


def _open_work_body(
    actions: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
    work_orders: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    for action in actions:
        lines.append(f"- Action {action.get('action_id')}: {action.get('status')} - {action.get('summary')}")
    for handoff in handoffs:
        lines.append(
            f"- Handoff {handoff.get('handoff_id')}: {handoff.get('source_desk')} -> {handoff.get('target_desk')} - {handoff.get('reason')}"
        )
    for work_order in work_orders:
        lines.append(f"- Work Order {work_order.get('work_order_id')}: {work_order.get('status')} - {work_order.get('title')}")
    return "\n".join(lines) if lines else "No open actions, handoffs, or work orders."


def _operating_rhythm_sections(
    *,
    kind: str,
    messages: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
    work_orders: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    if kind == "weekly_review":
        return [
            {
                "section_id": "weekly_strategy_review",
                "title": "Weekly Strategy Review",
                "body": _rows_body(
                    [
                        *_filter_rows(messages, "research", "strategy", "backtest", "oos", "ic"),
                        *_filter_rows(actions, "strategy", "research", "backtest", "promotion"),
                    ],
                    empty="No strategy or research evidence was recorded in this session.",
                ),
                "evidence_refs": evidence_refs,
            }
        ]
    if kind == "audit_pack":
        return [
            {
                "section_id": "audit_trail",
                "title": "Audit Trail",
                "body": _audit_trail_body(actions, runs, handoffs),
                "evidence_refs": evidence_refs,
            }
        ]
    if kind == "data_quality_review":
        return [
            {
                "section_id": "data_quality_evidence",
                "title": "Data Quality Evidence",
                "body": _evidence_body(evidence, evidence_refs, "data", "lifecycle", "source", "coverage", "freshness"),
                "evidence_refs": evidence_refs,
            }
        ]
    if kind == "risk_review":
        return [
            {
                "section_id": "risk_readiness",
                "title": "Risk Readiness",
                "body": _rows_body(
                    [
                        *_filter_rows(messages, "risk", "blocker", "drawdown", "exposure"),
                        *_filter_rows(actions, "risk", "blocked", "approval", "live_order", "paper_order"),
                        *_filter_rows(handoffs, "risk", "blocker", "execution"),
                    ],
                    empty="No risk blockers or risk desk notes were recorded in this session.",
                ),
                "evidence_refs": evidence_refs,
            }
        ]
    if kind == "execution_reconciliation":
        return [
            {
                "section_id": "execution_reconciliation",
                "title": "Execution Reconciliation",
                "body": _rows_body(
                    [
                        *_filter_rows(actions, "paper_order", "live_order", "execution"),
                        *_filter_rows(runs, "paper", "live", "execution", "reconciliation"),
                    ],
                    empty="No execution runs or reconciliation evidence were recorded in this session.",
                ),
                "evidence_refs": evidence_refs,
            }
        ]
    if kind == "engineering_digest":
        return [
            {
                "section_id": "engineering_work_orders",
                "title": "Engineering Work Orders",
                "body": _rows_body(
                    [
                        *_filter_rows(work_orders, "engineering", "codegraph", "architecture", "work_order"),
                        *_filter_rows(actions, "engineering", "codegraph", "architecture", "work_order"),
                        *_filter_rows(runs, "engineering", "codegraph", "ast", "test design"),
                        *_filter_rows(handoffs, "engineering", "codegraph", "architecture"),
                    ],
                    empty="No engineering work orders or diagnostics were recorded in this session.",
                ),
                "evidence_refs": evidence_refs,
            }
        ]
    if kind == "release_audit":
        return [
            {
                "section_id": "release_audit",
                "title": "Release Audit",
                "body": _release_audit_body(actions, runs, evidence_refs),
                "evidence_refs": evidence_refs,
            }
        ]
    return []


def _filter_rows(rows: list[dict[str, Any]], *needles: str) -> list[dict[str, Any]]:
    lowered_needles = [needle.lower() for needle in needles]
    matches: list[dict[str, Any]] = []
    for row in rows:
        haystack = json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
        if any(needle in haystack for needle in lowered_needles):
            matches.append(row)
    return matches


def _rows_body(rows: list[dict[str, Any]], *, empty: str) -> str:
    if not rows:
        return empty
    lines: list[str] = []
    for row in rows[:12]:
        identifier = row.get("action_id") or row.get("run_id") or row.get("handoff_id") or row.get("message_id") or "row"
        status = row.get("status") or row.get("role") or row.get("desk") or ""
        summary = row.get("summary") or row.get("stdout_summary") or row.get("reason") or row.get("content") or row.get("tool_name") or ""
        lines.append(f"- {identifier}: {status} - {str(summary).strip() or 'recorded'}")
    if len(rows) > 12:
        lines.append(f"- ... {len(rows) - 12} additional record(s) omitted.")
    return "\n".join(lines)


def _evidence_body(evidence: list[dict[str, Any]], evidence_refs: list[str], *needles: str) -> str:
    allowed = set(evidence_refs)
    scoped = [row for row in evidence if str(row.get("evidence_id")) in allowed]
    rows = _filter_rows(scoped, *needles)
    if not rows:
        return "No matching evidence references were recorded in this session."
    return "\n".join(
        f"- {row.get('evidence_id')}: {row.get('label')} - {row.get('summary')} ({row.get('uri')})" for row in rows[:12]
    )


def _audit_trail_body(actions: list[dict[str, Any]], runs: list[dict[str, Any]], handoffs: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            f"- Actions: {len(actions)} total",
            f"- Runs: {len(runs)} total",
            f"- Handoffs: {len(handoffs)} total",
            f"- Terminal actions: {sum(1 for row in actions if row.get('status') in {'succeeded', 'failed', 'blocked', 'rejected', 'canceled', 'expired'})}",
            f"- Failed or blocked runs: {sum(1 for row in runs if row.get('status') in {'failed', 'blocked'})}",
        ]
    )


def _release_audit_body(actions: list[dict[str, Any]], runs: list[dict[str, Any]], evidence_refs: list[str]) -> str:
    return "\n".join(
        [
            f"- Evidence refs: {len(evidence_refs)}",
            f"- Succeeded runs: {sum(1 for row in runs if row.get('status') == 'succeeded')}",
            f"- Failed runs: {sum(1 for row in runs if row.get('status') == 'failed')}",
            f"- Blocked runs: {sum(1 for row in runs if row.get('status') == 'blocked')}",
            f"- Open actions: {sum(1 for row in actions if row.get('status') in {'proposed', 'approval_required', 'approved', 'running'})}",
        ]
    )
