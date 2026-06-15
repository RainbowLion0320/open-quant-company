from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_os.approval import approval_required_for_risk, list_approval_policies as approval_policy_rows
from agent_os.desks import get_desk, list_desks
from agent_os.evidence import FILE_EVIDENCE_KINDS, hash_file
from agent_os.ledger import AgentLedger
from agent_os.notifications import NotificationSender, build_report_notification_message, channel_secret_status, send_notification, supported_channels
from agent_os.reports import (
    build_report_payload,
    collect_report_artifact_context,
    normalize_report_kind,
    read_report_index,
    render_report_markdown,
    report_rhythm_templates,
    write_report_index,
)
from agent_os.schemas import (
    AgentAction,
    AgentHandoff,
    AgentMessage,
    AgentReport,
    AgentRun,
    AgentRunEvent,
    AgentSession,
    AgentWorkOrder,
    DeskResponse,
    EvidenceRef,
)
from agent_os.tools import AgentToolRegistry
from agent_os.workflows import build_desk_workflow_plan
from broker import PaperBroker
from broker.live.qmt import MiniQmtLiveBroker
from data.storage.datahub import get_datahub


ACTION_EXPIRES_AFTER_SECONDS = 900
EXPIRABLE_ACTION_STATUSES = {"proposed", "approval_required", "approved"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _expires_at(created_at: str, seconds: int = ACTION_EXPIRES_AFTER_SECONDS) -> str:
    return _format_timestamp(_parse_timestamp(created_at) + timedelta(seconds=seconds))


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _summary(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _dataclass_to_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return dict(getattr(value, "__dict__", {}))


def _is_paper_reconciliation_evidence(evidence: dict[str, Any]) -> bool:
    return (
        str(evidence.get("kind") or "") == "artifact"
        and "paper_reconciliation" in str(evidence.get("uri") or "")
        and str(evidence.get("label") or "") == "Paper order reconciliation"
    )


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

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        default_desk: str | None = None,
        tags: list[str] | None = None,
    ) -> AgentSession:
        current = self.ledger.get_session(session_id)
        if not current:
            raise KeyError(f"Agent session not found: {session_id}")
        next_status = status if status is not None else str(current["status"])
        if next_status not in {"active", "archived", "blocked"}:
            raise ValueError(f"Invalid agent session status: {next_status}")
        next_title = title.strip() if title is not None else str(current["title"])
        if not next_title:
            raise ValueError("Agent session title cannot be empty")
        next_default_desk = default_desk.strip() if default_desk is not None else str(current["default_desk"])
        try:
            get_desk(next_default_desk)
        except KeyError as exc:
            raise ValueError(f"Invalid default desk: {next_default_desk}") from exc
        next_tags = [str(tag).strip() for tag in (tags if tags is not None else current.get("tags", []))]
        session = AgentSession(
            session_id=session_id,
            title=next_title,
            status=next_status,
            created_by=str(current["created_by"]),
            default_desk=next_default_desk,
            tags=[tag for tag in next_tags if tag],
            created_at=str(current["created_at"]),
            updated_at=_now(),
        )
        self.ledger.update_session(session.to_dict())
        return session

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
            "work_orders": self.ledger.list_work_orders(session_id),
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

    def submit_ceo_message(self, session_id: str, *, desk: str, content: str) -> dict[str, AgentMessage | DeskResponse]:
        session = self.ledger.get_session(session_id)
        if not session:
            raise KeyError(f"Agent session not found: {session_id}")
        target_desk = (desk or str(session.get("default_desk") or "reporting")).strip()
        if get_desk(target_desk) is None:
            raise ValueError(f"Unknown desk: {target_desk}")
        message = self.add_message(session_id, role="ceo", desk=target_desk, content=content)
        desk_response = self._route_ceo_message(
            session_id=session_id,
            source_message_id=message.message_id,
            desk=target_desk,
            content=content,
        )
        return {"message": message, "desk_response": desk_response}

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
            expires_at=_expires_at(timestamp),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.ledger.insert_action(action.to_dict())
        return action

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        return self.ledger.get_action(action_id)

    def paper_reconciliations_for_action(self, action_id: str) -> list[dict[str, Any]]:
        if not self.ledger.get_action(action_id):
            raise KeyError(f"Agent action not found: {action_id}")
        reconciliations: list[dict[str, Any]] = []
        for run in self.ledger.list_runs(action_id):
            for evidence_id in run.get("artifact_refs", []) or []:
                evidence = self.ledger.get_evidence(str(evidence_id))
                if not evidence or not _is_paper_reconciliation_evidence(evidence):
                    continue
                path = Path(str(evidence.get("uri") or ""))
                if not path.exists():
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or str(payload.get("action_id") or "") != action_id:
                    continue
                reconciliations.append(
                    {
                        **payload,
                        "evidence_id": str(evidence["evidence_id"]),
                        "path": str(path),
                        "run_id": str(run["run_id"]),
                        "freshness_status": str(evidence.get("freshness_status") or ""),
                    }
                )
        return reconciliations

    def live_reconciliations_for_action(self, action_id: str) -> list[dict[str, Any]]:
        if not self.ledger.get_action(action_id):
            raise KeyError(f"Agent action not found: {action_id}")
        reconciliations: list[dict[str, Any]] = []
        for run in self.ledger.list_runs(action_id):
            for evidence_id in run.get("artifact_refs", []) or []:
                evidence = self.ledger.get_evidence(str(evidence_id))
                if not evidence:
                    continue
                if str(evidence.get("label") or "") != "Live order reconciliation":
                    continue
                path = Path(str(evidence.get("uri") or ""))
                if "live_reconciliation" not in str(path) or not path.exists():
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or str(payload.get("action_id") or "") != action_id:
                    continue
                reconciliations.append(
                    {
                        **payload,
                        "evidence_id": str(evidence["evidence_id"]),
                        "path": str(path),
                        "run_id": str(run["run_id"]),
                        "freshness_status": str(evidence.get("freshness_status") or ""),
                    }
                )
        return reconciliations

    def list_actions(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_actions(session_id)

    def expire_actions(self, *, session_id: str | None = None) -> dict[str, Any]:
        expired: list[dict[str, Any]] = []
        timestamp = _now()
        for action in self.ledger.list_actions(session_id):
            if self._action_is_expired(action, now=timestamp):
                self.ledger.update_action_status(str(action["action_id"]), "expired", timestamp)
                updated = self.ledger.get_action(str(action["action_id"]))
                if updated is not None:
                    expired.append(updated)
        return {
            "status": "ok",
            "expired": len(expired),
            "actions": expired,
            "checked_at": timestamp,
        }

    def approve_action(self, action_id: str, *, decided_by: str = "ceo") -> AgentAction:
        return self._decide_action(action_id, "approved", decided_by=decided_by, reason="")

    def reject_action(self, action_id: str, *, decided_by: str = "ceo", reason: str = "") -> AgentAction:
        return self._decide_action(action_id, "rejected", decided_by=decided_by, reason=reason)

    def cancel_action(self, action_id: str, *, decided_by: str = "ceo", reason: str = "") -> AgentAction:
        current = self.ledger.get_action(action_id)
        if not current:
            raise KeyError(f"Agent action not found: {action_id}")
        if current.get("status") not in {"proposed", "approval_required", "approved"}:
            raise ValueError(f"Agent action cannot be canceled from status: {current['status']}")
        return self._decide_action(action_id, "canceled", decided_by=decided_by, reason=reason)

    def create_evidence(
        self,
        *,
        kind: str,
        label: str,
        uri: str,
        summary: str,
        freshness_status: str = "fresh",
    ) -> EvidenceRef:
        evidence_id = _id("ev")
        evidence_hash = ""
        snapshot_uri = ""
        if kind in FILE_EVIDENCE_KINDS and Path(uri).exists():
            evidence_hash = hash_file(uri)
            snapshot_uri = str(self._snapshot_evidence_file(evidence_id, Path(uri)))
        evidence = EvidenceRef(
            evidence_id=evidence_id,
            kind=kind,
            label=label,
            uri=uri,
            snapshot_uri=snapshot_uri,
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
        run_id: str | None = None,
        started_at: str | None = None,
    ) -> AgentRun:
        if not self.ledger.get_action(action_id):
            raise KeyError(f"Agent action not found: {action_id}")
        timestamp = _now()
        run = AgentRun(
            run_id=run_id or _id("run"),
            action_id=action_id,
            tool_name=tool_name,
            command=list(command),
            started_at=started_at or timestamp,
            finished_at=timestamp,
            status=status,
            return_code=return_code,
            stdout_summary=stdout_summary,
            stderr_summary=stderr_summary,
            artifact_refs=list(artifact_refs or []),
        )
        self.ledger.insert_run(run.to_dict())
        if stdout_summary:
            self.record_run_event(
                run.run_id,
                action_id=action_id,
                event_type="stdout",
                status="running" if status not in {"blocked"} else status,
                message=stdout_summary,
                payload={"stream": "stdout", "length": len(stdout_summary)},
            )
        if stderr_summary:
            self.record_run_event(
                run.run_id,
                action_id=action_id,
                event_type="stderr",
                status="running" if status not in {"blocked"} else status,
                message=stderr_summary,
                payload={"stream": "stderr", "length": len(stderr_summary)},
            )
        self.record_run_event(
            run.run_id,
            action_id=action_id,
            event_type=status,
            status=status,
            message=f"Run {status}",
            payload={"return_code": return_code, "tool_name": tool_name},
        )
        return run

    def record_run_event(
        self,
        run_id: str,
        *,
        action_id: str,
        event_type: str,
        status: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> AgentRunEvent:
        event = AgentRunEvent(
            event_id=_id("event"),
            run_id=run_id,
            action_id=action_id,
            sequence=self.ledger.next_run_event_sequence(run_id),
            event_type=event_type,
            status=status,
            message=message,
            payload=dict(payload or {}),
            created_at=_now(),
        )
        self.ledger.insert_run_event(event.to_dict())
        return event

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
        action = self._refresh_action_expiry(action)

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
            command = registry.command_for(
                tool_id,
                action.get("parameters", {}),
                approved=action.get("status") == "approved",
            )
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

        run_id = _id("run")
        started_at = _now()
        self.record_run_event(
            run_id,
            action_id=action_id,
            event_type="queued",
            status="queued",
            message="Run queued for fixed registry dispatch.",
            payload={"tool_name": tool_name, "command": command},
        )
        self.ledger.update_action_status(action_id, "running", _now())
        self.record_run_event(
            run_id,
            action_id=action_id,
            event_type="running",
            status="running",
            message="Tool command started.",
            payload={"tool_name": tool_name, "timeout_seconds": timeout_seconds},
        )
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
                run_id=run_id,
                started_at=started_at,
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
                run_id=run_id,
                started_at=started_at,
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
                run_id=run_id,
                started_at=started_at,
            )

    def run_session_read_only_actions(
        self,
        session_id: str,
        *,
        runner: Any | None = None,
        timeout_seconds: int = 120,
        tool_registry: AgentToolRegistry | None = None,
    ) -> dict[str, Any]:
        if not self.ledger.get_session(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        actions = self.ledger.list_actions(session_id)
        runs: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for action in actions:
            action_id = str(action["action_id"])
            risk_level = str(action.get("risk_level") or "")
            status = str(action.get("status") or "")
            if risk_level not in {"read_only", "dry_run"} or bool(action.get("approval_required")):
                skipped.append(
                    {
                        "action_id": action_id,
                        "desk": str(action.get("desk") or ""),
                        "risk_level": risk_level,
                        "status": status,
                        "reason": "not_safe_workflow_action",
                    }
                )
                continue
            if status != "proposed":
                skipped.append(
                    {
                        "action_id": action_id,
                        "desk": str(action.get("desk") or ""),
                        "risk_level": risk_level,
                        "status": status,
                        "reason": "status_not_proposed",
                    }
                )
                continue
            run = self.dispatch_action(
                action_id,
                runner=runner,
                timeout_seconds=timeout_seconds,
                tool_registry=tool_registry,
            )
            runs.append(self.get_run(run.run_id) or run.to_dict())

        succeeded_count = sum(1 for run in runs if run.get("status") == "succeeded")
        failed_count = sum(1 for run in runs if run.get("status") == "failed")
        blocked_count = sum(1 for run in runs if run.get("status") == "blocked")
        status = "ready" if failed_count == 0 and blocked_count == 0 else "partial"
        return {
            "status": status,
            "session_id": session_id,
            "checked_at": _now(),
            "action_count": len(actions),
            "run_count": len(runs),
            "succeeded_count": succeeded_count,
            "failed_count": failed_count,
            "blocked_count": blocked_count,
            "skipped_count": len(skipped),
            "runs": runs,
            "skipped": skipped,
        }

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.ledger.get_run(run_id)
        return self._run_with_events(run) if run else None

    def list_runs(self, action_id: str | None = None, *, include_events: bool = False) -> list[dict[str, Any]]:
        runs = self.ledger.list_runs(action_id)
        if include_events:
            return [self._run_with_events(run) for run in runs]
        return runs

    def list_run_events(self, run_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_run_events(run_id)

    def list_handoffs(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_handoffs(session_id)

    def resolve_handoff(self, handoff_id: str, *, resolved_by: str = "ceo") -> dict[str, Any]:
        handoff = self.ledger.get_handoff(handoff_id)
        if handoff is None:
            raise KeyError(f"Agent handoff not found: {handoff_id}")
        if handoff.get("status") != "resolved":
            self.ledger.update_handoff_status(handoff_id, "resolved", _now())
            handoff = self.ledger.get_handoff(handoff_id)
        if handoff is None:
            raise KeyError(f"Agent handoff not found after update: {handoff_id}")
        return handoff

    def create_work_order(
        self,
        *,
        session_id: str,
        title: str,
        summary: str,
        impact: str,
        affected_files: list[str] | None = None,
        suggested_verification: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        created_by: str = "engineering_desk",
    ) -> dict[str, Any]:
        if not self.ledger.get_session(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Agent work order title cannot be empty")
        timestamp = _now()
        work_order = AgentWorkOrder(
            work_order_id=_id("wo"),
            session_id=session_id,
            desk="engineering",
            title=clean_title,
            summary=summary.strip(),
            impact=impact.strip(),
            affected_files=[str(path).strip() for path in (affected_files or []) if str(path).strip()],
            suggested_verification=[
                str(command).strip() for command in (suggested_verification or []) if str(command).strip()
            ],
            evidence_refs=[str(evidence_id).strip() for evidence_id in (evidence_refs or []) if str(evidence_id).strip()],
            status="open",
            resolution="",
            resolved_at=None,
            created_by=created_by.strip() or "engineering_desk",
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.ledger.insert_work_order(work_order.to_dict())
        return work_order.to_dict()

    def list_work_orders(self, session_id: str | None = None) -> dict[str, Any]:
        rows = self.ledger.list_work_orders(session_id)
        return {
            "status": "ready",
            "work_orders": rows,
            "total": len(rows),
        }

    def update_work_order_status(self, work_order_id: str, *, status: str, resolution: str = "") -> dict[str, Any]:
        allowed_statuses = {"open", "in_progress", "resolved", "canceled"}
        clean_status = status.strip()
        if clean_status not in allowed_statuses:
            raise ValueError(f"Invalid agent work order status: {status}")
        row = self.ledger.get_work_order(work_order_id)
        if row is None:
            raise KeyError(f"Agent work order not found: {work_order_id}")
        timestamp = _now()
        terminal = clean_status in {"resolved", "canceled"}
        self.ledger.update_work_order_status(
            work_order_id,
            status=clean_status,
            resolution=resolution.strip(),
            resolved_at=timestamp if terminal else None,
            updated_at=timestamp,
        )
        updated = self.ledger.get_work_order(work_order_id)
        if updated is None:
            raise KeyError(f"Agent work order not found after update: {work_order_id}")
        return updated

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

    def list_approval_policies(self) -> list[dict[str, Any]]:
        return [dict(policy) for policy in approval_policy_rows()]

    def live_readiness(self) -> dict[str, Any]:
        health = MiniQmtLiveBroker().health()
        kill_switch = self.live_kill_switch_status()
        if kill_switch["active"]:
            blockers = list(health.get("blockers") or [])
            if "live_kill_switch_active" not in blockers:
                blockers.append("live_kill_switch_active")
            health = {
                **health,
                "mode": "blocked",
                "blockers": blockers,
                "live_kill_switch": kill_switch,
                "paper_fallback": False,
            }
        else:
            health = {**health, "live_kill_switch": kill_switch}
        return health

    def preview_live_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        kill_switch = self.live_kill_switch_status()
        if kill_switch["active"]:
            return self._live_kill_switch_block_preview(intent, kill_switch)
        return MiniQmtLiveBroker().preview_order(intent)

    def live_kill_switch_status(self) -> dict[str, Any]:
        return self._read_live_kill_switch_state()

    def activate_live_kill_switch(self, *, reason: str = "", cancel_queued: bool = True) -> dict[str, Any]:
        timestamp = _now()
        clean_reason = reason.strip() or "Live kill switch activated"
        state = {
            "status": "active",
            "active": True,
            "reason": clean_reason,
            "activated_at": timestamp,
            "deactivated_at": "",
            "updated_at": timestamp,
            "paper_fallback": False,
        }
        self._write_live_kill_switch_state(state)
        canceled_actions: list[dict[str, Any]] = []
        if cancel_queued:
            cancel_reason = f"Live kill switch active: {clean_reason}"
            for action in self.ledger.list_actions():
                refreshed = self._refresh_action_expiry(action)
                if str(refreshed.get("action_type")) != "live_order":
                    continue
                if str(refreshed.get("status")) not in EXPIRABLE_ACTION_STATUSES:
                    continue
                try:
                    canceled = self.cancel_action(str(refreshed["action_id"]), reason=cancel_reason)
                except ValueError:
                    continue
                canceled_actions.append(canceled.to_dict())
        event = {
            **state,
            "event": "activated",
            "canceled_count": len(canceled_actions),
            "canceled_actions": canceled_actions,
        }
        artifact_path = self._write_live_kill_switch_event_artifact(event)
        evidence = self.create_evidence(
            kind="artifact",
            label="Live kill switch",
            uri=str(artifact_path),
            summary=f"Live kill switch activated; canceled {len(canceled_actions)} queued live action(s).",
        )
        return {
            **event,
            "artifact_path": str(artifact_path),
            "state_path": str(self._live_kill_switch_state_path()),
            "evidence": evidence.to_dict(),
        }

    def deactivate_live_kill_switch(self, *, reason: str = "") -> dict[str, Any]:
        previous = self.live_kill_switch_status()
        timestamp = _now()
        clean_reason = reason.strip() or "Live kill switch deactivated"
        state = {
            "status": "inactive",
            "active": False,
            "reason": clean_reason,
            "activated_at": str(previous.get("activated_at") or ""),
            "deactivated_at": timestamp,
            "updated_at": timestamp,
            "paper_fallback": False,
        }
        self._write_live_kill_switch_state(state)
        event = {**state, "event": "deactivated", "canceled_count": 0, "canceled_actions": []}
        artifact_path = self._write_live_kill_switch_event_artifact(event)
        evidence = self.create_evidence(
            kind="artifact",
            label="Live kill switch",
            uri=str(artifact_path),
            summary="Live kill switch deactivated.",
        )
        return {
            **event,
            "artifact_path": str(artifact_path),
            "state_path": str(self._live_kill_switch_state_path()),
            "evidence": evidence.to_dict(),
        }

    def propose_live_order(
        self,
        *,
        session_id: str,
        intent: dict[str, Any],
        broker: Any | None = None,
    ) -> dict[str, Any]:
        if not self.ledger.get_session(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        kill_switch = self.live_kill_switch_status()
        if kill_switch["active"]:
            return {
                "status": "blocked",
                "preview": self._live_kill_switch_block_preview(intent, kill_switch),
                "action": None,
                "kill_switch": kill_switch,
            }
        live_broker = broker or MiniQmtLiveBroker()
        preview = live_broker.preview_order(intent)
        if preview["status"] != "preview_ready":
            return {
                "status": "blocked",
                "preview": preview,
                "action": None,
            }

        artifact_path = self._write_live_preview_artifact(session_id, preview)
        evidence = self.create_evidence(
            kind="artifact",
            label="Live order preview",
            uri=str(artifact_path),
            summary=f"Live order preview for {preview['intent']['side']} {preview['intent']['symbol']}",
        )
        action = self.propose_action(
            session_id=session_id,
            desk="execution",
            action_type="live_order",
            risk_level="live_order",
            summary=f"Approve live {preview['intent']['side']} {preview['intent']['symbol']} x{preview['intent']['quantity']}",
            parameters={
                "live_order_intent": preview["intent"],
                "live_order_preview": preview,
                "preview_artifact": str(artifact_path),
            },
            expected_effect=(
                "Requires CEO approval; approved submit re-runs MiniQMT/QMT preview/risk gates, "
                "submits only through the live broker adapter, and records live reconciliation evidence."
            ),
            evidence_refs=[evidence.evidence_id],
        )
        return {
            "status": action.status,
            "preview": preview,
            "action": action.to_dict(),
            "evidence": evidence.to_dict(),
        }

    def submit_live_order_action(
        self,
        action_id: str,
        *,
        broker: Any | None = None,
    ) -> dict[str, Any]:
        action = self.ledger.get_action(action_id)
        if not action:
            raise KeyError(f"Agent action not found: {action_id}")
        action = self._refresh_action_expiry(action)
        if str(action.get("action_type")) != "live_order" or str(action.get("risk_level")) != "live_order":
            return self._record_live_submission_block(
                action,
                broker=broker,
                reason="action is not a live_order",
                update_action_status=True,
            )
        if action.get("status") != "approved":
            return self._record_live_submission_block(
                action,
                broker=broker,
                reason=f"approval required before live submit: {action.get('status')}",
                preview=dict((action.get("parameters") or {}).get("live_order_preview") or {}),
                update_action_status=False,
            )

        intent = dict((action.get("parameters") or {}).get("live_order_intent") or {})
        kill_switch = self.live_kill_switch_status()
        if kill_switch["active"]:
            return self._record_live_submission_block(
                action,
                broker=None,
                reason="live_kill_switch_active",
                preview=self._live_kill_switch_block_preview(intent, kill_switch),
                update_action_status=True,
            )

        live_broker = broker or MiniQmtLiveBroker()
        preview = live_broker.preview_order(intent)
        if preview.get("status") != "preview_ready":
            return self._record_live_submission_block(
                action,
                broker=live_broker,
                reason="live preview blocked before submission",
                preview=preview,
                update_action_status=True,
            )

        ack = dict(live_broker.submit_order(preview["intent"], approval_id=action_id))
        submitted = bool(ack.get("submitted")) and bool(ack.get("broker_order_id"))
        if not submitted:
            reconciliation = self._live_reconciliation_payload(
                action=action,
                status="failed",
                preview=preview,
                ack=ack,
                broker_reconciliation={},
                error=str(ack.get("error") or ack.get("status") or "live submission failed"),
            )
            evidence = self._write_live_reconciliation_evidence(action, reconciliation)
            self.ledger.update_action_status(action_id, "failed", _now())
            run = self.record_run(
                action_id=action_id,
                tool_name="live.live_order.submit",
                command=["live_order_submit", action_id],
                status="failed",
                return_code=1,
                stdout_summary="",
                stderr_summary=str(reconciliation["error"]),
                artifact_refs=[evidence.evidence_id],
            )
            return {
                "status": "failed",
                "preview": preview,
                "ack": ack,
                "run": run.to_dict(),
                "reconciliation": reconciliation,
                "evidence": evidence.to_dict(),
            }

        broker_reconciliation = dict(live_broker.reconcile(ack))
        reconciliation = self._live_reconciliation_payload(
            action=action,
            status="submitted",
            preview=preview,
            ack=ack,
            broker_reconciliation=broker_reconciliation,
            error="",
        )
        evidence = self._write_live_reconciliation_evidence(action, reconciliation)
        self.ledger.update_action_status(action_id, "succeeded", _now())
        run = self.record_run(
            action_id=action_id,
            tool_name="live.live_order.submit",
            command=["live_order_submit", action_id],
            status="succeeded",
            return_code=0,
            stdout_summary=f"live order submitted: {ack['broker_order_id']}",
            stderr_summary="",
            artifact_refs=[evidence.evidence_id],
        )
        return {
            "status": "succeeded",
            "preview": preview,
            "ack": ack,
            "run": run.to_dict(),
            "reconciliation": reconciliation,
            "evidence": evidence.to_dict(),
        }

    def run_live_reconciliation(self, *, session_id: str | None = None, broker: Any | None = None) -> dict[str, Any]:
        live_broker = broker or MiniQmtLiveBroker()
        checked_at = _now()
        actions = [
            action
            for action in reversed(self.ledger.list_actions(session_id))
            if str(action.get("action_type")) == "live_order" and str(action.get("risk_level")) == "live_order"
        ]
        items: list[dict[str, Any]] = []
        reconciled_count = 0
        skipped_count = 0
        blocked_count = 0
        failed_count = 0

        for action in actions:
            action_id = str(action["action_id"])
            submitted_reconciliations = [
                reconciliation
                for reconciliation in self.live_reconciliations_for_action(action_id)
                if str(reconciliation.get("status") or "") == "submitted" and str(reconciliation.get("order_id") or "")
            ]
            if not submitted_reconciliations:
                skipped_count += 1
                items.append(
                    {
                        "action_id": action_id,
                        "status": "skipped",
                        "reason": "no_submitted_live_order",
                        "order_id": "",
                        "broker_reconciliation": {},
                    }
                )
                continue

            latest = submitted_reconciliations[0]
            ack = dict(latest.get("ack") or {})
            try:
                broker_reconciliation = dict(live_broker.reconcile(ack))
            except Exception as exc:  # pragma: no cover - defensive adapter boundary
                failed_count += 1
                items.append(
                    {
                        "action_id": action_id,
                        "status": "failed",
                        "reason": str(exc),
                        "order_id": str(latest.get("order_id") or ack.get("broker_order_id") or ""),
                        "ack": ack,
                        "broker_reconciliation": {},
                        "source_reconciliation": latest,
                    }
                )
                continue

            broker_status = str(broker_reconciliation.get("status") or "")
            item_status = "reconciled" if broker_status in {"matched", "ok", "ready"} else "blocked"
            if item_status == "reconciled":
                reconciled_count += 1
            else:
                blocked_count += 1
            items.append(
                {
                    "action_id": action_id,
                    "status": item_status,
                    "reason": "" if item_status == "reconciled" else broker_status,
                    "order_id": str(latest.get("order_id") or ack.get("broker_order_id") or ""),
                    "ack": ack,
                    "broker_reconciliation": broker_reconciliation,
                    "source_reconciliation": latest,
                }
            )

        status = "ready" if blocked_count == 0 and failed_count == 0 else "partial"
        payload = {
            "status": status,
            "checked_at": checked_at,
            "session_id": session_id or "",
            "action_count": len(actions),
            "reconciled_count": reconciled_count,
            "skipped_count": skipped_count,
            "blocked_count": blocked_count,
            "failed_count": failed_count,
            "items": items,
            "paper_fallback": False,
        }
        path = self._write_live_scheduled_reconciliation_artifact(payload)
        evidence = self.create_evidence(
            kind="artifact",
            label="Live scheduled reconciliation",
            uri=str(path),
            summary=(
                f"Live reconciliation scanned {payload['action_count']} action(s), "
                f"reconciled {payload['reconciled_count']}, skipped {payload['skipped_count']}, "
                f"blocked {payload['blocked_count']}, failed {payload['failed_count']}."
            ),
        )
        return {**payload, "path": str(path), "evidence": evidence.to_dict()}

    def propose_paper_order(
        self,
        *,
        session_id: str,
        intent: dict[str, Any],
        broker: PaperBroker | None = None,
    ) -> dict[str, Any]:
        if not self.ledger.get_session(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        paper_broker = broker or self._load_default_paper_broker()
        preview = paper_broker.preview_order(intent)
        if preview["status"] != "preview_ready":
            return {
                "status": "blocked",
                "preview": preview,
                "action": None,
            }

        artifact_path = self._write_paper_preview_artifact(session_id, preview)
        evidence = self.create_evidence(
            kind="artifact",
            label="Paper order preview",
            uri=str(artifact_path),
            summary=f"Paper order preview for {preview['intent']['side']} {preview['intent']['symbol']}",
        )
        action = self.propose_action(
            session_id=session_id,
            desk="execution",
            action_type="paper_order",
            risk_level="paper_order",
            summary=f"Approve paper {preview['intent']['side']} {preview['intent']['symbol']} x{preview['intent']['quantity']}",
            parameters={
                "paper_order_intent": preview["intent"],
                "paper_order_preview": preview,
                "preview_artifact": str(artifact_path),
            },
            expected_effect="Requires CEO approval; approved submit re-runs PaperBroker preview/risk gates, writes a run, and records reconciliation evidence before marking success.",
            evidence_refs=[evidence.evidence_id],
        )
        return {
            "status": action.status,
            "preview": preview,
            "action": action.to_dict(),
            "evidence": evidence.to_dict(),
        }

    def submit_paper_order_action(
        self,
        action_id: str,
        *,
        broker: PaperBroker | None = None,
    ) -> dict[str, Any]:
        action = self.ledger.get_action(action_id)
        if not action:
            raise KeyError(f"Agent action not found: {action_id}")
        action = self._refresh_action_expiry(action)
        if str(action.get("action_type")) != "paper_order" or str(action.get("risk_level")) != "paper_order":
            return self._record_paper_submission_block(
                action,
                broker=broker,
                reason="action is not a paper_order",
                update_action_status=True,
            )
        if action.get("status") != "approved":
            return self._record_paper_submission_block(
                action,
                broker=broker,
                reason=f"approval required before paper submit: {action.get('status')}",
                update_action_status=False,
            )

        paper_broker = broker or self._load_default_paper_broker()
        intent = dict((action.get("parameters") or {}).get("paper_order_intent") or {})
        preview = paper_broker.preview_order(intent)
        if preview.get("status") != "preview_ready":
            return self._record_paper_submission_block(
                action,
                broker=paper_broker,
                reason="paper preview blocked before submission",
                preview=preview,
                update_action_status=True,
            )

        normalized = preview["intent"]
        order_id_or_reason = paper_broker.submit_order(
            code=str(normalized["symbol"]),
            price=float(normalized["limit_price"]),
            volume=int(normalized["quantity"]),
            side=str(normalized["side"]),
        )
        submitted = str(order_id_or_reason).startswith("PAPER_")
        status = "succeeded" if submitted else "failed"
        reconciliation = self._paper_reconciliation_payload(
            action=action,
            status="submitted" if submitted else "failed",
            preview=preview,
            broker=paper_broker,
            order_id=str(order_id_or_reason) if submitted else "",
            error="" if submitted else str(order_id_or_reason),
        )
        evidence = self._write_paper_reconciliation_evidence(action, reconciliation)
        if submitted and broker is None:
            self._persist_default_paper_broker(paper_broker, preview)
        self.ledger.update_action_status(action_id, status, _now())
        run = self.record_run(
            action_id=action_id,
            tool_name="paper.paper_order.submit",
            command=["paper_order_submit", action_id],
            status=status,
            return_code=0 if submitted else 1,
            stdout_summary=f"paper order submitted: {order_id_or_reason}" if submitted else "",
            stderr_summary="" if submitted else str(order_id_or_reason),
            artifact_refs=[evidence.evidence_id],
        )
        return {
            "status": status,
            "preview": preview,
            "run": run.to_dict(),
            "reconciliation": reconciliation,
            "evidence": evidence.to_dict(),
        }

    def cancel_paper_order_action(
        self,
        action_id: str,
        *,
        broker: PaperBroker | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        action = self.ledger.get_action(action_id)
        if not action:
            raise KeyError(f"Agent action not found: {action_id}")
        action = self._refresh_action_expiry(action)
        if str(action.get("action_type")) != "paper_order" or str(action.get("risk_level")) != "paper_order":
            return self._record_paper_cancellation_block(
                action,
                broker=broker,
                reason="action is not a paper_order",
            )

        paper_broker = broker or self._load_default_paper_broker()
        if action.get("status") in EXPIRABLE_ACTION_STATUSES:
            canceled = self.cancel_action(action_id, reason=reason or "Paper order approval request canceled")
            reconciliation = self._paper_reconciliation_payload(
                action=canceled.to_dict(),
                status="queued_action_canceled",
                preview=dict((action.get("parameters") or {}).get("paper_order_preview") or {}),
                broker=paper_broker,
                order_id="",
                error="",
            )
            reconciliation["cancel_reason"] = reason
            evidence = self._write_paper_reconciliation_evidence(canceled.to_dict(), reconciliation)
            run = self.record_run(
                action_id=action_id,
                tool_name="paper.paper_order.cancel",
                command=["paper_order_cancel", action_id],
                status="succeeded",
                return_code=0,
                stdout_summary="paper order approval request canceled",
                stderr_summary="",
                artifact_refs=[evidence.evidence_id],
            )
            return {
                "status": "canceled",
                "run": run.to_dict(),
                "reconciliation": reconciliation,
                "evidence": evidence.to_dict(),
            }

        if action.get("status") != "succeeded":
            return self._record_paper_cancellation_block(
                action,
                broker=paper_broker,
                reason=f"paper order cannot be canceled from action status: {action.get('status')}",
            )

        submitted = self._latest_submitted_paper_reconciliation(action_id)
        order_id = str(submitted.get("order_id") or "")
        if not order_id:
            return self._record_paper_cancellation_block(
                action,
                broker=paper_broker,
                reason="missing submitted paper order id",
            )

        canceled = paper_broker.cancel_order(order_id)
        if not canceled:
            return self._record_paper_cancellation_block(
                action,
                broker=paper_broker,
                reason=f"paper order is not cancelable or missing: {order_id}",
                order_id=order_id,
                preview=dict(submitted.get("preview") or {}),
            )

        if broker is None:
            self._persist_default_paper_broker(paper_broker, dict(submitted.get("preview") or {}))
        reconciliation = self._paper_reconciliation_payload(
            action=action,
            status="order_canceled",
            preview=dict(submitted.get("preview") or {}),
            broker=paper_broker,
            order_id=order_id,
            error="",
        )
        reconciliation["cancel_reason"] = reason
        evidence = self._write_paper_reconciliation_evidence(action, reconciliation)
        run = self.record_run(
            action_id=action_id,
            tool_name="paper.paper_order.cancel",
            command=["paper_order_cancel", action_id, order_id],
            status="succeeded",
            return_code=0,
            stdout_summary=f"paper order canceled: {order_id}",
            stderr_summary="",
            artifact_refs=[evidence.evidence_id],
        )
        return {
            "status": "canceled",
            "run": run.to_dict(),
            "reconciliation": reconciliation,
            "evidence": evidence.to_dict(),
        }

    def generate_report(self, *, session_id: str, kind: str = "daily_brief") -> dict[str, Any]:
        session = self.ledger.get_session(session_id)
        if not session:
            raise KeyError(f"Agent session not found: {session_id}")
        normalized_kind = normalize_report_kind(kind)
        report_id = _id("rep")
        generated_at = _now()
        report_dir = get_datahub().artifact_dir("agent") / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{normalized_kind}-{generated_at.replace(':', '').replace('-', '').replace('T', '-')}-{report_id}"
        path = report_dir / f"{stem}.json"
        markdown_path = report_dir / f"{stem}.md"
        report = build_report_payload(
            report_id=report_id,
            session=session,
            messages=self.ledger.list_messages(session_id),
            actions=self.ledger.list_actions(session_id),
            runs=self._session_runs(session_id),
            handoffs=self.ledger.list_handoffs(session_id),
            work_orders=self.ledger.list_work_orders(session_id),
            evidence=self.ledger.list_evidence(),
            kind=normalized_kind,
            path=path,
            markdown_path=markdown_path,
            generated_at=generated_at,
            artifact_context=collect_report_artifact_context(),
        )
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        markdown_path.write_text(render_report_markdown(report), encoding="utf-8")
        evidence = self.create_evidence(
            kind="report",
            label=str(report["title"]),
            uri=str(path),
            summary=str(report["summary"]),
        )
        report = {**report, "evidence_id": evidence.evidence_id}
        index_path = report_dir / "index.json"
        reports = [report, *[row for row in read_report_index(index_path) if row.get("report_id") != report_id]]
        write_report_index(index_path, reports)
        return AgentReport(**report).to_dict()

    def list_reports(self, session_id: str | None = None) -> dict[str, Any]:
        index_path = get_datahub().artifact_dir("agent") / "reports" / "index.json"
        reports = read_report_index(index_path)
        if session_id:
            reports = [row for row in reports if row.get("session_id") == session_id]
        return {
            "status": "ready",
            "reports": reports,
            "total": len(reports),
        }

    def plan_report_rhythm(self, *, session_id: str, force: bool = False, as_of: str | None = None) -> dict[str, Any]:
        if not self.ledger.get_session(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        checked_at = as_of or _now()
        checked_dt = _parse_timestamp(checked_at)
        reports = self.list_reports(session_id)["reports"]
        items: list[dict[str, Any]] = []
        for template in report_rhythm_templates():
            kind = str(template["kind"])
            last_report = self._latest_report_for_kind(reports, kind)
            last_generated_at = str(last_report.get("generated_at") or "") if last_report else ""
            if force:
                due = True
                reason = "force"
            elif not last_report:
                due = True
                reason = "never_generated"
            else:
                last_dt = _parse_timestamp(last_generated_at)
                due = checked_dt - last_dt >= timedelta(hours=int(template["interval_hours"]))
                reason = "cadence_elapsed" if due else "not_due"
            items.append(
                {
                    "kind": kind,
                    "title": template["title"],
                    "cadence": template["cadence"],
                    "interval_hours": template["interval_hours"],
                    "last_generated_at": last_generated_at,
                    "due": due,
                    "reason": reason,
                    "status": "planned" if due else "skipped",
                    "report_id": "",
                    "evidence_id": "",
                }
            )
        return {
            "status": "ready",
            "session_id": session_id,
            "checked_at": checked_at,
            "force": force,
            "items": items,
            "due_count": sum(1 for item in items if item["due"]),
        }

    def notify_report(
        self,
        report_id: str,
        *,
        channels: list[str] | None = None,
        dry_run: bool = False,
        sender: NotificationSender | None = None,
    ) -> dict[str, Any]:
        report = self._find_report(report_id)
        if report is None:
            raise KeyError(f"Agent report not found: {report_id}")
        requested_channels = [str(channel).strip().lower() for channel in (channels or supported_channels()) if str(channel).strip()]
        if not requested_channels:
            requested_channels = supported_channels()
        message = build_report_notification_message(report)
        send_callable = sender or send_notification
        channel_results: list[dict[str, Any]] = []
        sent_count = 0
        failed_count = 0
        blocked_count = 0
        for channel in requested_channels:
            try:
                secret_status = channel_secret_status(channel)
            except ValueError as exc:
                failed_count += 1
                channel_results.append(
                    {
                        "channel": channel,
                        "status": "failed",
                        "configured": False,
                        "required_env": [],
                        "missing_env": [],
                        "error": str(exc),
                    }
                )
                continue
            base = {
                "channel": secret_status["channel"],
                "configured": bool(secret_status["configured"]),
                "required_env": list(secret_status["required_env"]),
                "missing_env": list(secret_status["missing_env"]),
            }
            if dry_run:
                channel_results.append({**base, "status": "dry_run", "error": "", "status_code": None})
                continue
            if not secret_status["configured"]:
                blocked_count += 1
                channel_results.append({**base, "status": "missing_secret", "error": "missing notification environment variable", "status_code": None})
                continue
            result = send_callable(str(secret_status["channel"]), message)
            if bool(result.get("ok")):
                sent_count += 1
                channel_results.append(
                    {
                        **base,
                        "status": "sent",
                        "error": "",
                        "status_code": result.get("status_code"),
                        "provider_message_id": str(result.get("provider_message_id") or ""),
                    }
                )
            else:
                failed_count += 1
                channel_results.append(
                    {
                        **base,
                        "status": str(result.get("status") or "failed"),
                        "error": str(result.get("error") or ""),
                        "status_code": result.get("status_code"),
                    }
                )
        if dry_run:
            status = "dry_run"
        elif sent_count == len(channel_results) and channel_results:
            status = "sent"
        elif sent_count > 0:
            status = "partial"
        else:
            status = "blocked"
        payload = {
            "status": status,
            "notification_id": _id("notif"),
            "report_id": str(report["report_id"]),
            "session_id": str(report["session_id"]),
            "report_kind": str(report["kind"]),
            "report_title": str(report["title"]),
            "report_path": str(report["path"]),
            "report_evidence_id": str(report.get("evidence_id") or ""),
            "dry_run": dry_run,
            "checked_at": _now(),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "blocked_count": blocked_count,
            "channels": channel_results,
            "message_preview": {
                "title": message["title"],
                "body": _summary(message["body"], limit=1000),
            },
        }
        path = self._write_report_notification_artifact(payload)
        evidence = self.create_evidence(
            kind="ledger",
            label="Agent report notification",
            uri=str(path),
            summary=f"Report notification {payload['status']} for {payload['report_id']}.",
        )
        return {**payload, "path": str(path), "evidence": evidence.to_dict()}

    def run_report_rhythm(
        self,
        *,
        session_id: str,
        force: bool = False,
        as_of: str | None = None,
        notify: bool = False,
        notification_channels: list[str] | None = None,
        dry_run_notifications: bool = False,
    ) -> dict[str, Any]:
        plan = self.plan_report_rhythm(session_id=session_id, force=force, as_of=as_of)
        generated: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        notifications: list[dict[str, Any]] = []
        for item in plan["items"]:
            if item["due"]:
                report = self.generate_report(session_id=session_id, kind=str(item["kind"]))
                generated.append(report)
                notification = None
                if notify:
                    notification = self.notify_report(
                        str(report["report_id"]),
                        channels=notification_channels,
                        dry_run=dry_run_notifications,
                    )
                    notifications.append(notification)
                items.append(
                    {
                        **item,
                        "status": "generated",
                        "report_id": report["report_id"],
                        "evidence_id": report["evidence_id"],
                        "generated_at": report["generated_at"],
                        "notification_id": str(notification.get("notification_id") or "") if notification else "",
                        "notification_status": str(notification.get("status") or "") if notification else "",
                    }
                )
            else:
                items.append({**item, "status": "skipped"})
        payload = {
            "status": "ready",
            "run_id": _id("rhythm"),
            "session_id": session_id,
            "checked_at": plan["checked_at"],
            "force": force,
            "generated_count": len(generated),
            "skipped_count": sum(1 for item in items if item["status"] == "skipped"),
            "notification_count": len(notifications),
            "notification_failed_count": sum(1 for item in notifications if item.get("status") not in {"sent", "dry_run"}),
            "items": items,
            "reports": generated,
            "notifications": notifications,
        }
        path = self._write_report_rhythm_artifact(payload)
        evidence = self.create_evidence(
            kind="ledger",
            label="Agent report operating rhythm",
            uri=str(path),
            summary=f"Generated {payload['generated_count']} report(s), skipped {payload['skipped_count']} report(s).",
        )
        return {**payload, "path": str(path), "evidence": evidence.to_dict()}

    def run_scheduled_report_rhythm(
        self,
        *,
        force: bool = False,
        as_of: str | None = None,
        session_status: str = "active",
        notify: bool = False,
        notification_channels: list[str] | None = None,
        dry_run_notifications: bool = False,
    ) -> dict[str, Any]:
        checked_at = as_of or _now()
        session_ids = self.ledger.list_session_ids_by_status(session_status)
        sessions: list[dict[str, Any]] = []
        generated_count = 0
        skipped_count = 0
        notification_count = 0
        notification_failed_count = 0
        failed_count = 0
        for session_id in session_ids:
            try:
                rhythm = self.run_report_rhythm(
                    session_id=session_id,
                    force=force,
                    as_of=checked_at,
                    notify=notify,
                    notification_channels=notification_channels,
                    dry_run_notifications=dry_run_notifications,
                )
                sessions.append(
                    {
                        "session_id": session_id,
                        "status": "ready",
                        "generated_count": rhythm["generated_count"],
                        "skipped_count": rhythm["skipped_count"],
                        "notification_count": rhythm["notification_count"],
                        "notification_failed_count": rhythm["notification_failed_count"],
                        "rhythm_run_id": rhythm["run_id"],
                        "path": rhythm["path"],
                        "evidence_id": rhythm["evidence"]["evidence_id"],
                    }
                )
                generated_count += int(rhythm["generated_count"])
                skipped_count += int(rhythm["skipped_count"])
                notification_count += int(rhythm["notification_count"])
                notification_failed_count += int(rhythm["notification_failed_count"])
            except Exception as exc:
                failed_count += 1
                sessions.append(
                    {
                        "session_id": session_id,
                        "status": "failed",
                        "generated_count": 0,
                        "skipped_count": 0,
                        "notification_count": 0,
                        "notification_failed_count": 0,
                        "rhythm_run_id": "",
                        "path": "",
                        "evidence_id": "",
                        "error": str(exc),
                    }
                )
        payload = {
            "status": "ready" if failed_count == 0 else "partial",
            "schedule_id": _id("schedule"),
            "checked_at": checked_at,
            "force": force,
            "session_status": session_status,
            "session_count": len(session_ids),
            "generated_count": generated_count,
            "skipped_count": skipped_count,
            "notification_count": notification_count,
            "notification_failed_count": notification_failed_count,
            "failed_count": failed_count,
            "sessions": sessions,
        }
        path = self._write_scheduled_report_rhythm_artifact(payload)
        evidence = self.create_evidence(
            kind="ledger",
            label="Agent scheduled report rhythm",
            uri=str(path),
            summary=(
                f"Scheduled report rhythm scanned {payload['session_count']} session(s), "
                f"generated {payload['generated_count']} report(s), failed {payload['failed_count']} session(s)."
            ),
        )
        return {**payload, "path": str(path), "evidence": evidence.to_dict()}

    def _snapshot_evidence_file(self, evidence_id: str, source: Path) -> Path:
        root = get_datahub().artifact_dir("agent") / "evidence" / evidence_id
        root.mkdir(parents=True, exist_ok=True)
        target = root / (source.name or "evidence")
        shutil.copy2(source, target)
        return target

    def _write_report_rhythm_artifact(self, payload: dict[str, Any]) -> Path:
        root = get_datahub().artifact_dir("agent") / "reports" / "rhythm"
        root.mkdir(parents=True, exist_ok=True)
        checked_at = str(payload["checked_at"]).replace(":", "").replace("-", "").replace("T", "-").replace("Z", "")
        path = root / f"{checked_at}-{payload['run_id']}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _write_scheduled_report_rhythm_artifact(self, payload: dict[str, Any]) -> Path:
        root = get_datahub().artifact_dir("agent") / "reports" / "scheduled"
        root.mkdir(parents=True, exist_ok=True)
        checked_at = str(payload["checked_at"]).replace(":", "").replace("-", "").replace("T", "-").replace("Z", "")
        path = root / f"{checked_at}-{payload['schedule_id']}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _write_report_notification_artifact(self, payload: dict[str, Any]) -> Path:
        root = get_datahub().artifact_dir("agent") / "reports" / "notifications"
        root.mkdir(parents=True, exist_ok=True)
        checked_at = str(payload["checked_at"]).replace(":", "").replace("-", "").replace("T", "-").replace("Z", "")
        path = root / f"{checked_at}-{payload['notification_id']}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _write_paper_preview_artifact(self, session_id: str, preview: dict[str, Any]) -> Path:
        root = get_datahub().artifact_dir("agent") / "paper_previews"
        root.mkdir(parents=True, exist_ok=True)
        preview_id = _id("paper_preview")
        path = root / f"{preview_id}.json"
        payload = {
            "preview_id": preview_id,
            "session_id": session_id,
            "preview": preview,
            "generated_at": _now(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _write_live_preview_artifact(self, session_id: str, preview: dict[str, Any]) -> Path:
        root = get_datahub().artifact_dir("agent") / "live_previews"
        root.mkdir(parents=True, exist_ok=True)
        preview_id = _id("live_preview")
        path = root / f"{preview_id}.json"
        payload = {
            "preview_id": preview_id,
            "session_id": session_id,
            "preview": preview,
            "generated_at": _now(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _live_kill_switch_state_path(self) -> Path:
        return get_datahub().artifact_dir("agent") / "live_kill_switch" / "state.json"

    def _default_live_kill_switch_state(self) -> dict[str, Any]:
        return {
            "status": "inactive",
            "active": False,
            "reason": "",
            "activated_at": "",
            "deactivated_at": "",
            "updated_at": "",
            "paper_fallback": False,
        }

    def _read_live_kill_switch_state(self) -> dict[str, Any]:
        path = self._live_kill_switch_state_path()
        if not path.exists():
            return {**self._default_live_kill_switch_state(), "state_path": str(path)}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {
                **self._default_live_kill_switch_state(),
                "status": "invalid",
                "active": True,
                "state_path": str(path),
                "read_error": "invalid_live_kill_switch_state",
            }
        if not isinstance(payload, dict):
            return {
                **self._default_live_kill_switch_state(),
                "status": "invalid",
                "active": True,
                "state_path": str(path),
                "read_error": "invalid_live_kill_switch_state",
            }
        active = bool(payload.get("active"))
        return {
            **self._default_live_kill_switch_state(),
            **payload,
            "status": "active" if active else "inactive",
            "active": active,
            "paper_fallback": False,
            "state_path": str(path),
        }

    def _write_live_kill_switch_state(self, state: dict[str, Any]) -> Path:
        path = self._live_kill_switch_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            **self._default_live_kill_switch_state(),
            **state,
            "state_path": str(path),
        }
        payload["active"] = bool(payload.get("active"))
        payload["status"] = "active" if payload["active"] else "inactive"
        payload["paper_fallback"] = False
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _write_live_kill_switch_event_artifact(self, payload: dict[str, Any]) -> Path:
        root = get_datahub().artifact_dir("agent") / "live_kill_switch" / "events"
        root.mkdir(parents=True, exist_ok=True)
        event = str(payload.get("event") or "event")
        timestamp = str(payload.get("updated_at") or _now()).replace(":", "").replace("-", "").replace("T", "-").replace("Z", "")
        path = root / f"{timestamp}-{event}-{uuid.uuid4().hex[:8]}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _live_kill_switch_block_preview(self, intent: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        reason = str(state.get("reason") or "Live kill switch active")
        return {
            "status": "blocked",
            "broker": "miniqmt",
            "intent": dict(intent or {}),
            "approval_required": True,
            "paper_fallback": False,
            "submitted": False,
            "risk_gate": {
                "passed": False,
                "blockers": ["live_kill_switch_active"],
                "checks": [
                    {
                        "name": "live_kill_switch",
                        "passed": False,
                        "reason": reason,
                    }
                ],
            },
            "health": {
                "mode": "blocked",
                "paper_fallback": False,
                "blockers": ["live_kill_switch_active"],
                "live_kill_switch": dict(state),
            },
            "warnings": ["live_kill_switch_active"],
            "created_at": _now(),
        }

    def _record_live_submission_block(
        self,
        action: dict[str, Any],
        *,
        broker: Any | None,
        reason: str,
        preview: dict[str, Any] | None = None,
        update_action_status: bool,
    ) -> dict[str, Any]:
        action_id = str(action["action_id"])
        live_broker = broker or MiniQmtLiveBroker()
        resolved_preview = preview or {}
        if not resolved_preview and action.get("parameters", {}).get("live_order_intent"):
            resolved_preview = live_broker.preview_order(dict(action.get("parameters", {}).get("live_order_intent") or {}))
        reconciliation = self._live_reconciliation_payload(
            action=action,
            status="blocked",
            preview=resolved_preview,
            ack={},
            broker_reconciliation={},
            error=reason,
        )
        evidence = self._write_live_reconciliation_evidence(action, reconciliation)
        if update_action_status:
            self.ledger.update_action_status(action_id, "blocked", _now())
        run = self.record_run(
            action_id=action_id,
            tool_name="live.live_order.submit",
            command=["live_order_submit", action_id],
            status="blocked",
            return_code=None,
            stdout_summary="",
            stderr_summary=reason,
            artifact_refs=[evidence.evidence_id],
        )
        return {
            "status": "blocked",
            "preview": resolved_preview,
            "run": run.to_dict(),
            "reconciliation": reconciliation,
            "evidence": evidence.to_dict(),
        }

    def _record_paper_submission_block(
        self,
        action: dict[str, Any],
        *,
        broker: PaperBroker | None,
        reason: str,
        preview: dict[str, Any] | None = None,
        update_action_status: bool,
    ) -> dict[str, Any]:
        action_id = str(action["action_id"])
        paper_broker = broker or self._load_default_paper_broker()
        resolved_preview = preview or {}
        if not resolved_preview and action.get("parameters", {}).get("paper_order_intent"):
            resolved_preview = paper_broker.preview_order(dict(action.get("parameters", {}).get("paper_order_intent") or {}))
        reconciliation = self._paper_reconciliation_payload(
            action=action,
            status="blocked",
            preview=resolved_preview,
            broker=paper_broker,
            order_id="",
            error=reason,
        )
        evidence = self._write_paper_reconciliation_evidence(action, reconciliation)
        if update_action_status:
            self.ledger.update_action_status(action_id, "blocked", _now())
        run = self.record_run(
            action_id=action_id,
            tool_name="paper.paper_order.submit",
            command=["paper_order_submit", action_id],
            status="blocked",
            return_code=None,
            stdout_summary="",
            stderr_summary=reason,
            artifact_refs=[evidence.evidence_id],
        )
        return {
            "status": "blocked",
            "preview": resolved_preview,
            "run": run.to_dict(),
            "reconciliation": reconciliation,
            "evidence": evidence.to_dict(),
        }

    def _record_paper_cancellation_block(
        self,
        action: dict[str, Any],
        *,
        broker: PaperBroker | None,
        reason: str,
        order_id: str = "",
        preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_id = str(action["action_id"])
        paper_broker = broker or self._load_default_paper_broker()
        reconciliation = self._paper_reconciliation_payload(
            action=action,
            status="blocked",
            preview=preview or dict((action.get("parameters") or {}).get("paper_order_preview") or {}),
            broker=paper_broker,
            order_id=order_id,
            error=reason,
        )
        evidence = self._write_paper_reconciliation_evidence(action, reconciliation)
        run = self.record_run(
            action_id=action_id,
            tool_name="paper.paper_order.cancel",
            command=["paper_order_cancel", action_id] + ([order_id] if order_id else []),
            status="blocked",
            return_code=None,
            stdout_summary="",
            stderr_summary=reason,
            artifact_refs=[evidence.evidence_id],
        )
        return {
            "status": "blocked",
            "run": run.to_dict(),
            "reconciliation": reconciliation,
            "evidence": evidence.to_dict(),
        }

    def _latest_submitted_paper_reconciliation(self, action_id: str) -> dict[str, Any]:
        for reconciliation in self.paper_reconciliations_for_action(action_id):
            if reconciliation.get("status") == "submitted" and reconciliation.get("order_id"):
                return reconciliation
        return {}

    def _paper_reconciliation_payload(
        self,
        *,
        action: dict[str, Any],
        status: str,
        preview: dict[str, Any],
        broker: PaperBroker,
        order_id: str,
        error: str,
    ) -> dict[str, Any]:
        account = broker.get_balance()
        orders = [_dataclass_to_dict(order) for order in broker.get_orders()]
        positions = [_dataclass_to_dict(position) for position in broker.get_positions()]
        return {
            "action_id": str(action["action_id"]),
            "session_id": str(action["session_id"]),
            "status": status,
            "order_id": order_id,
            "error": error,
            "preview": preview,
            "account_after": _dataclass_to_dict(account),
            "positions_after": positions,
            "orders_after": orders,
            "generated_at": _now(),
        }

    def _write_paper_reconciliation_evidence(self, action: dict[str, Any], reconciliation: dict[str, Any]) -> EvidenceRef:
        root = get_datahub().artifact_dir("agent") / "paper_reconciliation"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"paper_reconciliation-{action['action_id']}-{uuid.uuid4().hex[:8]}.json"
        path.write_text(json.dumps(reconciliation, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return self.create_evidence(
            kind="artifact",
            label="Paper order reconciliation",
            uri=str(path),
            summary=f"Paper order reconciliation {reconciliation['status']} for {action['action_id']}",
        )

    def _live_reconciliation_payload(
        self,
        *,
        action: dict[str, Any],
        status: str,
        preview: dict[str, Any],
        ack: dict[str, Any],
        broker_reconciliation: dict[str, Any],
        error: str,
    ) -> dict[str, Any]:
        return {
            "action_id": str(action["action_id"]),
            "session_id": str(action["session_id"]),
            "status": status,
            "order_id": str(ack.get("broker_order_id") or ""),
            "error": error,
            "preview": preview,
            "ack": ack,
            "broker_reconciliation": broker_reconciliation,
            "paper_fallback": False,
            "generated_at": _now(),
        }

    def _write_live_reconciliation_evidence(self, action: dict[str, Any], reconciliation: dict[str, Any]) -> EvidenceRef:
        root = get_datahub().artifact_dir("agent") / "live_reconciliation"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"live_reconciliation-{action['action_id']}-{uuid.uuid4().hex[:8]}.json"
        path.write_text(json.dumps(reconciliation, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return self.create_evidence(
            kind="artifact",
            label="Live order reconciliation",
            uri=str(path),
            summary=f"Live order reconciliation {reconciliation['status']} for {action['action_id']}",
        )

    def _write_live_scheduled_reconciliation_artifact(self, payload: dict[str, Any]) -> Path:
        root = get_datahub().artifact_dir("agent") / "live_reconciliation" / "scheduled"
        root.mkdir(parents=True, exist_ok=True)
        checked_at = str(payload["checked_at"]).replace(":", "").replace("-", "").replace("T", "-").replace("Z", "")
        path = root / f"{checked_at}-{uuid.uuid4().hex[:8]}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _load_default_paper_broker(self) -> PaperBroker:
        from broker.persistence import load_state

        return PaperBroker.from_state(load_state(), enable_risk=True)

    def _persist_default_paper_broker(self, broker: PaperBroker, preview: dict[str, Any]) -> None:
        from broker.persistence import append_nav, append_trade, save_state

        intent = preview["intent"]
        run_date = date.today()
        save_state(broker.snapshot_state())
        balance = broker.get_balance()
        append_nav(run_date, balance.total_asset, balance.cash, balance.market_value)
        append_trade(
            run_date,
            str(intent["symbol"]),
            str(intent["side"]),
            float(intent["limit_price"]),
            int(intent["quantity"]),
            float(preview["notional"]),
            str(intent.get("strategy") or ""),
        )

    def _route_ceo_message(self, *, session_id: str, source_message_id: str, desk: str, content: str) -> DeskResponse:
        plan = build_desk_workflow_plan(desk=desk, content=content)
        evidence_refs: list[str] = []
        proposed_actions: list[str] = []
        for action_spec in plan.actions:
            evidence = self.create_evidence(
                kind="web_route",
                label=action_spec.evidence.label,
                uri=action_spec.evidence.uri,
                summary=action_spec.evidence.summary,
            )
            action = self.propose_action(
                session_id=session_id,
                desk=action_spec.desk,
                action_type=action_spec.action_type,
                risk_level=action_spec.risk_level,
                summary=action_spec.summary,
                parameters={"tool_id": action_spec.tool_id},
                expected_effect=action_spec.expected_effect,
                evidence_refs=[evidence.evidence_id],
            )
            evidence_refs.append(evidence.evidence_id)
            proposed_actions.append(action.action_id)
        return self.respond_as_desk(
            session_id=session_id,
            source_message_id=source_message_id,
            desk=plan.desk,
            answer=plan.answer,
            confidence=plan.confidence,
            evidence_refs=evidence_refs,
            proposed_actions=proposed_actions,
            blockers=plan.blockers,
            handoffs=plan.handoffs,
        )

    def memory_snapshot(self) -> dict[str, Any]:
        sessions = self.ledger.list_sessions()
        messages: list[dict[str, Any]] = []
        for session in sessions:
            messages.extend(self.ledger.list_messages(str(session["session_id"])))
        actions = self.ledger.list_actions()
        runs = self.ledger.list_runs()
        run_events = self.ledger.list_run_events()
        evidence = self.ledger.list_evidence()
        handoffs = self.ledger.list_handoffs()
        work_orders = self.ledger.list_work_orders()
        summary = {
            "session_count": len(sessions),
            "message_count": len(messages),
            "action_count": len(actions),
            "run_count": len(runs),
            "run_event_count": len(run_events),
            "evidence_count": len(evidence),
            "handoff_count": len(handoffs),
            "work_order_count": len(work_orders),
        }
        return {
            "status": "ready",
            "generated_at": _now(),
            "summary": summary,
            "records": {
                "sessions": sessions,
                "messages": messages,
                "actions": actions,
                "runs": runs,
                "run_events": run_events,
                "evidence": evidence,
                "handoffs": handoffs,
                "work_orders": work_orders,
            },
        }

    def export_memory(self) -> dict[str, Any]:
        snapshot = self.memory_snapshot()
        filename_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = get_datahub().artifact_dir("agent") / "memory" / f"memory-{filename_ts}-{uuid.uuid4().hex[:8]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "path": str(path),
            "generated_at": snapshot["generated_at"],
            "summary": snapshot["summary"],
        }

    def prune_memory(self, *, policy: str = "archived_sessions", dry_run: bool = False) -> dict[str, Any]:
        if policy != "archived_sessions":
            raise ValueError(f"Unsupported memory prune policy: {policy}")
        session_ids = self.ledger.list_session_ids_by_status("archived")
        counts = self.ledger.delete_sessions(session_ids, dry_run=dry_run)
        return {
            "status": "dry_run" if dry_run else "pruned",
            "policy": policy,
            "dry_run": dry_run,
            "session_ids": session_ids,
            "counts": counts,
            "generated_at": _now(),
        }

    def clear_memory(self, *, confirm: bool = False, dry_run: bool = False) -> dict[str, Any]:
        if not confirm and not dry_run:
            raise ValueError("Agent memory clear requires confirm=True")
        counts = self.ledger.clear_memory(dry_run=dry_run)
        return {
            "status": "dry_run" if dry_run else "cleared",
            "dry_run": dry_run,
            "counts": counts,
            "generated_at": _now(),
        }

    def _decide_action(self, action_id: str, status: str, *, decided_by: str, reason: str) -> AgentAction:
        current = self.ledger.get_action(action_id)
        if not current:
            raise KeyError(f"Agent action not found: {action_id}")
        current = self._refresh_action_expiry(current)
        if current.get("status") == "expired":
            raise ValueError(f"Agent action is expired: {action_id}")
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

    def _refresh_action_expiry(self, action: dict[str, Any]) -> dict[str, Any]:
        if self._action_is_expired(action, now=_now()):
            action_id = str(action["action_id"])
            self.ledger.update_action_status(action_id, "expired", _now())
            updated = self.ledger.get_action(action_id)
            if updated is not None:
                return updated
        return action

    @staticmethod
    def _action_is_expired(action: dict[str, Any], *, now: str) -> bool:
        if str(action.get("status") or "") not in EXPIRABLE_ACTION_STATUSES:
            return False
        expires_at = str(action.get("expires_at") or "").strip()
        if not expires_at:
            return False
        return _parse_timestamp(expires_at) <= _parse_timestamp(now)

    def _session_runs(self, session_id: str) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for action in self.ledger.list_actions(session_id):
            runs.extend(self.ledger.list_runs(str(action["action_id"])))
        return runs

    def _run_with_events(self, run: dict[str, Any]) -> dict[str, Any]:
        return {
            **run,
            "events": self.ledger.list_run_events(str(run["run_id"])),
        }

    @staticmethod
    def _find_report(report_id: str) -> dict[str, Any] | None:
        target = str(report_id or "").strip()
        if not target:
            return None
        index_path = get_datahub().artifact_dir("agent") / "reports" / "index.json"
        for report in read_report_index(index_path):
            if str(report.get("report_id") or "") == target:
                return report
        return None

    @staticmethod
    def _latest_report_for_kind(reports: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
        candidates = [report for report in reports if report.get("kind") == kind and report.get("generated_at")]
        if not candidates:
            return None
        return max(candidates, key=lambda report: _parse_timestamp(str(report["generated_at"])))

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
