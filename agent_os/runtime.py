from __future__ import annotations

import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_os.approval import approval_required_for_risk
from agent_os.desks import get_desk, list_desks
from agent_os.evidence import FILE_EVIDENCE_KINDS, hash_file
from agent_os.ledger import AgentLedger
from agent_os.schemas import AgentAction, AgentHandoff, AgentMessage, AgentRun, AgentSession, DeskResponse, EvidenceRef
from agent_os.tools import AgentToolRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _summary(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


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
            "handoffs": self.ledger.list_handoffs(session_id),
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
        self._validate_desk_action_scope(
            desk=desk,
            action_type=action_type,
            risk_level=risk_level,
            tool_id=self._tool_id_for_action(action_type, parameters or {}),
        )
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

    def dispatch_action(
        self,
        action_id: str,
        *,
        runner: Any | None = None,
        timeout_seconds: int = 120,
        tool_registry: AgentToolRegistry | None = None,
    ) -> AgentRun:
        """Execute a fixed registry command for a safe or approved action.

        This is intentionally narrow: it dispatches only command arrays from
        AgentToolRegistry and records every blocked/failed outcome in the run ledger.
        """
        action = self.ledger.get_action(action_id)
        if not action:
            raise KeyError(f"Agent action not found: {action_id}")

        tool_id = self._tool_id_for_action(str(action.get("action_type") or ""), action.get("parameters", {}))
        tool_name = tool_id or "unbound_tool"
        registry = tool_registry or AgentToolRegistry()
        try:
            self._validate_desk_action_scope(
                desk=str(action.get("desk") or ""),
                action_type=str(action.get("action_type") or ""),
                risk_level=str(action.get("risk_level") or ""),
                tool_id=tool_id,
                tool_registry=registry,
            )
        except (KeyError, PermissionError, ValueError) as exc:
            self.ledger.update_action_status(action_id, "blocked", _now())
            return self.record_run(
                action_id=action_id,
                tool_name=tool_name,
                command=[],
                status="blocked",
                return_code=None,
                stdout_summary="",
                stderr_summary=str(exc),
            )
        if action["approval_required"] and action["status"] != "approved":
            return self.record_run(
                action_id=action_id,
                tool_name=tool_name,
                command=[],
                status="blocked",
                return_code=None,
                stdout_summary="",
                stderr_summary=f"approval required before dispatch: {action['status']}",
            )
        if action["status"] in {"rejected", "canceled", "expired"}:
            return self.record_run(
                action_id=action_id,
                tool_name=tool_name,
                command=[],
                status="blocked",
                return_code=None,
                stdout_summary="",
                stderr_summary=f"action status cannot be dispatched: {action['status']}",
            )

        try:
            command = registry.command_for(tool_id, action.get("parameters", {}))
        except (KeyError, ValueError) as exc:
            self.ledger.update_action_status(action_id, "blocked", _now())
            return self.record_run(
                action_id=action_id,
                tool_name=tool_name,
                command=[],
                status="blocked",
                return_code=None,
                stdout_summary="",
                stderr_summary=str(exc),
            )

        self.ledger.update_action_status(action_id, "running", _now())
        run_callable = runner or subprocess.run
        try:
            result = run_callable(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            status = "succeeded" if result.returncode == 0 else "failed"
            self.ledger.update_action_status(action_id, status, _now())
            return self.record_run(
                action_id=action_id,
                tool_name=tool_name,
                command=command,
                status=status,
                return_code=result.returncode,
                stdout_summary=_summary(result.stdout or ""),
                stderr_summary=_summary(result.stderr or ""),
            )
        except subprocess.TimeoutExpired as exc:
            self.ledger.update_action_status(action_id, "failed", _now())
            return self.record_run(
                action_id=action_id,
                tool_name=tool_name,
                command=command,
                status="failed",
                return_code=None,
                stdout_summary=_summary(str(exc.stdout or "")),
                stderr_summary=f"timeout after {timeout_seconds}s",
            )
        except Exception as exc:
            self.ledger.update_action_status(action_id, "failed", _now())
            return self.record_run(
                action_id=action_id,
                tool_name=tool_name,
                command=command,
                status="failed",
                return_code=None,
                stdout_summary="",
                stderr_summary=str(exc),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.ledger.get_run(run_id)

    def list_runs(self, action_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_runs(action_id)

    def list_handoffs(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_handoffs(session_id)

    def respond_as_desk(
        self,
        *,
        session_id: str,
        source_message_id: str,
        desk: str,
        answer: str,
        confidence: float = 0.5,
        evidence_refs: list[str] | None = None,
        proposed_actions: list[str] | None = None,
        blockers: list[str] | None = None,
        handoffs: list[dict[str, Any]] | None = None,
    ) -> DeskResponse:
        if not self.ledger.get_session(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        desk_record = get_desk(desk)
        if desk_record is None:
            raise ValueError(f"Unknown desk: {desk}")
        evidence = list(evidence_refs or [])
        action_refs = list(proposed_actions or [])
        handoff_rows: list[dict[str, Any]] = []
        for handoff in handoffs or []:
            target = str(handoff.get("target_desk") or "")
            if target not in desk_record.get("handoff_targets", []):
                raise ValueError(f"handoff from {desk} to {target} is not allowed")
            row = AgentHandoff(
                handoff_id=_id("handoff"),
                session_id=session_id,
                source_message_id=source_message_id,
                source_desk=desk,
                target_desk=target,
                reason=str(handoff.get("reason") or ""),
                status="open",
                evidence_refs=list(handoff.get("evidence_refs") or evidence),
                created_at=_now(),
                resolved_at="",
            )
            self.ledger.insert_handoff(row.to_dict())
            handoff_rows.append(row.to_dict())

        message = self.add_message(
            session_id,
            role="desk_agent",
            desk=desk,
            content=answer,
            evidence_refs=evidence,
            action_refs=action_refs,
        )
        return DeskResponse(
            message=message,
            answer=answer,
            confidence=confidence,
            evidence_refs=evidence,
            proposed_actions=action_refs,
            blockers=list(blockers or []),
            handoffs=handoff_rows,
        )

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

    @staticmethod
    def _tool_id_for_action(action_type: str, parameters: dict[str, Any] | None) -> str:
        params = parameters or {}
        return str(params.get("tool_id") or action_type or "")

    def _validate_desk_action_scope(
        self,
        *,
        desk: str,
        action_type: str,
        risk_level: str,
        tool_id: str,
        tool_registry: AgentToolRegistry | None = None,
    ) -> None:
        desk_record = get_desk(desk)
        if desk_record is None:
            raise ValueError(f"Unknown desk: {desk}")
        forbidden = set(desk_record.get("forbidden_actions", []))
        if risk_level in forbidden or action_type in forbidden:
            raise PermissionError(f"{desk} desk is not allowed to propose {risk_level or action_type} actions")
        registry = tool_registry or AgentToolRegistry()
        if not tool_id or registry.get(tool_id) is None:
            return
        tool = registry.get(tool_id)
        allowed_tools = set(desk_record.get("allowed_tools", []))
        allowed_by_desk = tool_id in allowed_tools
        allowed_by_tool = desk in set(tool.desk_scopes if tool else [])
        if not allowed_by_desk or not allowed_by_tool:
            raise PermissionError(f"{desk} desk is not allowed to use agent tool {tool_id}")
