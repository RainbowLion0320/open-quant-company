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
