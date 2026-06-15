from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentSession:
    session_id: str
    title: str
    status: str
    created_by: str
    default_desk: str
    tags: list[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentMessage:
    message_id: str
    session_id: str
    role: str
    desk: str
    content: str
    evidence_refs: list[str] = field(default_factory=list)
    action_refs: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentAction:
    action_id: str
    session_id: str
    desk: str
    action_type: str
    risk_level: str
    status: str
    summary: str
    parameters: dict[str, Any]
    expected_effect: str
    evidence_refs: list[str]
    approval_required: bool
    approval_decision: dict[str, Any] | None
    expires_at: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    kind: str
    label: str
    uri: str
    snapshot_uri: str
    summary: str
    generated_at: str
    hash: str
    freshness_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentRun:
    run_id: str
    action_id: str
    tool_name: str
    command: list[str]
    started_at: str
    finished_at: str
    status: str
    return_code: int | None
    stdout_summary: str
    stderr_summary: str
    artifact_refs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentRunEvent:
    event_id: str
    run_id: str
    action_id: str
    sequence: int
    event_type: str
    status: str
    message: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentHandoff:
    handoff_id: str
    session_id: str
    source_message_id: str
    source_desk: str
    target_desk: str
    reason: str
    status: str
    evidence_refs: list[str]
    created_at: str
    resolved_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ApprovalPolicy:
    policy_id: str
    risk_level: str
    default_decision: str
    required_role: str
    expires_after_seconds: int
    reason: str
    approval_required: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentReport:
    report_id: str
    session_id: str
    kind: str
    title: str
    summary: str
    path: str
    markdown_path: str
    evidence_id: str
    evidence_refs: list[str]
    missing_evidence: list[str]
    artifact_context: dict[str, Any]
    sections: list[dict[str, Any]]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeskResponse:
    message: AgentMessage
    answer: str
    confidence: float
    evidence_refs: list[str]
    proposed_actions: list[str]
    blockers: list[str]
    handoffs: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message.to_dict(),
            "answer": self.answer,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "proposed_actions": list(self.proposed_actions),
            "blockers": list(self.blockers),
            "handoffs": [dict(handoff) for handoff in self.handoffs],
        }
