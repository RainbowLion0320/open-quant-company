from __future__ import annotations

import json
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
}

REPORT_TITLES = {
    "daily_brief": "Daily CEO Brief",
    "weekly_review": "Weekly Research Review",
    "audit_pack": "Agent Audit Pack",
}


def normalize_report_kind(kind: str) -> str:
    normalized = REPORT_KIND_ALIASES.get(kind.strip().lower())
    if not normalized:
        raise ValueError(f"Unsupported agent report kind: {kind}")
    return normalized


def report_title(kind: str) -> str:
    return REPORT_TITLES[normalize_report_kind(kind)]


def build_report_payload(
    *,
    report_id: str,
    session: dict[str, Any],
    messages: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    kind: str,
    path: Path,
    markdown_path: Path,
    generated_at: str,
) -> dict[str, Any]:
    normalized_kind = normalize_report_kind(kind)
    evidence_by_id = {str(row.get("evidence_id")): row for row in evidence}
    evidence_refs = _ordered_unique(
        [
            *[ref for row in messages for ref in row.get("evidence_refs", [])],
            *[ref for row in actions for ref in row.get("evidence_refs", [])],
            *[ref for row in handoffs for ref in row.get("evidence_refs", [])],
            *[ref for row in runs for ref in row.get("artifact_refs", [])],
        ]
    )
    missing_evidence = [ref for ref in evidence_refs if ref not in evidence_by_id]
    recent_messages = messages[-5:]
    open_handoffs = [row for row in handoffs if row.get("status") == "open"]
    active_actions = [row for row in actions if row.get("status") in {"proposed", "approval_required", "approved", "running"}]
    summary = (
        f"{len(recent_messages)} recent message(s), {len(active_actions)} active action(s), "
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
            "body": _open_work_body(active_actions, open_handoffs),
            "evidence_refs": _ordered_unique(
                [
                    *[ref for row in active_actions for ref in row.get("evidence_refs", [])],
                    *[ref for row in open_handoffs for ref in row.get("evidence_refs", [])],
                ]
            ),
        },
    ]
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
        sections=sections,
        generated_at=generated_at,
    ).to_dict()


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


def _open_work_body(actions: list[dict[str, Any]], handoffs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for action in actions:
        lines.append(f"- Action {action.get('action_id')}: {action.get('status')} - {action.get('summary')}")
    for handoff in handoffs:
        lines.append(
            f"- Handoff {handoff.get('handoff_id')}: {handoff.get('source_desk')} -> {handoff.get('target_desk')} - {handoff.get('reason')}"
        )
    return "\n".join(lines) if lines else "No open actions or handoffs."
