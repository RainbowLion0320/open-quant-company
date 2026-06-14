from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_os.approval import approval_required_for_risk
from agent_os.desks import list_desks
from agent_os.evidence import FILE_EVIDENCE_KINDS, hash_file
from agent_os.ledger import AgentLedger
from agent_os.schemas import AgentAction, AgentMessage, AgentRun, AgentSession, EvidenceRef


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class AgentRuntime:
    """Local Agent Company OS runtime.

    The runtime only manages local ledgers, approvals, desk metadata, and evidence references.
    It does not call arbitrary tools or execute broker actions.
    """

    def __init__(self, ledger: AgentLedger | None = None):
        self.ledger = ledger or AgentLedger()

    def create_session(
        self,
        title: str,
        *,
        default_desk: str = "reporting",
        created_by: str = "human",
        tags: list[str] | None = None,
    ) -> AgentSession:
        timestamp = _now()
        session = AgentSession(
            session_id=_id("agt_sess"),
            title=title.strip() or "Untitled session",
            status="active",
            created_by=created_by,
            default_desk=default_desk,
            tags=list(tags or []),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.ledger.insert_session(session.to_dict())
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.ledger.list_sessions()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.ledger.get_session(session_id)
        if not session:
            return None
        return {
            "session": session,
            "messages": self.ledger.list_messages(session_id),
            "actions": self.ledger.list_actions(session_id),
            "runs": self._session_runs(session_id),
        }

    def add_message(
        self,
        session_id: str,
        *,
        role: str,
        desk: str,
        content: str,
        evidence_refs: list[str] | None = None,
        action_refs: list[str] | None = None,
    ) -> AgentMessage:
        if not self.ledger.get_session(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        message = AgentMessage(
            message_id=_id("agt_msg"),
            session_id=session_id,
            role=role,
            desk=desk,
            content=content,
            evidence_refs=list(evidence_refs or []),
            action_refs=list(action_refs or []),
            created_at=_now(),
        )
        self.ledger.insert_message(message.to_dict())
        return message

    def propose_action(
        self,
        *,
        session_id: str,
        desk: str,
        action_type: str,
        risk_level: str,
        summary: str,
        parameters: dict[str, Any] | None = None,
        expected_effect: str = "",
        evidence_refs: list[str] | None = None,
    ) -> AgentAction:
        if not self.ledger.get_session(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        approval_required = approval_required_for_risk(risk_level)
        timestamp = _now()
        action = AgentAction(
            action_id=_id("act"),
            session_id=session_id,
            desk=desk,
            action_type=action_type,
            risk_level=risk_level,
            status="approval_required" if approval_required else "proposed",
            summary=summary,
            parameters=dict(parameters or {}),
            expected_effect=expected_effect,
            evidence_refs=list(evidence_refs or []),
            approval_required=approval_required,
            approval_decision=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.ledger.insert_action(action.to_dict())
        return action

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        return self.ledger.get_action(action_id)

    def list_actions(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_actions(session_id)

    def approve_action(self, action_id: str, *, decided_by: str = "ceo") -> AgentAction:
        return self._decide_action(action_id, "approved", decided_by=decided_by, reason="")

    def reject_action(self, action_id: str, *, decided_by: str = "ceo", reason: str = "") -> AgentAction:
        return self._decide_action(action_id, "rejected", decided_by=decided_by, reason=reason)

    def create_evidence(
        self,
        *,
        kind: str,
        label: str,
        uri: str,
        summary: str,
        freshness_status: str = "fresh",
    ) -> EvidenceRef:
        evidence_hash = ""
        if kind in FILE_EVIDENCE_KINDS and Path(uri).exists():
            evidence_hash = hash_file(uri)
        evidence = EvidenceRef(
            evidence_id=_id("ev"),
            kind=kind,
            label=label,
            uri=uri,
            summary=summary,
            generated_at=_now(),
            hash=evidence_hash,
            freshness_status=freshness_status,
        )
        self.ledger.insert_evidence(evidence.to_dict())
        return evidence

    def record_run(
        self,
        *,
        action_id: str,
        tool_name: str,
        command: list[str],
        status: str,
        return_code: int | None,
        stdout_summary: str,
        stderr_summary: str,
        artifact_refs: list[str] | None = None,
    ) -> AgentRun:
        if not self.ledger.get_action(action_id):
            raise KeyError(f"Agent action not found: {action_id}")
        timestamp = _now()
        run = AgentRun(
            run_id=_id("run"),
            action_id=action_id,
            tool_name=tool_name,
            command=list(command),
            started_at=timestamp,
            finished_at=timestamp,
            status=status,
            return_code=return_code,
            stdout_summary=stdout_summary,
            stderr_summary=stderr_summary,
            artifact_refs=list(artifact_refs or []),
        )
        self.ledger.insert_run(run.to_dict())
        return run

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.ledger.get_run(run_id)

    def list_runs(self, action_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_runs(action_id)

    def list_desks(self) -> list[dict[str, Any]]:
        return list_desks()

    def _decide_action(self, action_id: str, status: str, *, decided_by: str, reason: str) -> AgentAction:
        current = self.ledger.get_action(action_id)
        if not current:
            raise KeyError(f"Agent action not found: {action_id}")
        timestamp = _now()
        decision = {
            "decision": status,
            "decided_by": decided_by,
            "reason": reason,
            "decided_at": timestamp,
        }
        self.ledger.update_action_decision(action_id, status, decision, timestamp)
        updated = self.ledger.get_action(action_id)
        if updated is None:
            raise KeyError(f"Agent action not found after update: {action_id}")
        return AgentAction(**updated)

    def _session_runs(self, session_id: str) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for action in self.ledger.list_actions(session_id):
            runs.extend(self.ledger.list_runs(str(action["action_id"])))
        return runs
