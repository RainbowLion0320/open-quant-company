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
) -> dict[str, Any]:
    normalized_kind = normalize_report_kind(kind)
    artifact_context = artifact_context or empty_report_artifact_context()
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
    return {
        "available_count": sum(1 for item in items if item["status"] == "available"),
        "missing_count": sum(1 for item in items if item["status"] == "missing"),
        "invalid_count": sum(1 for item in items if item["status"] == "invalid"),
        "items": items,
    }


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
