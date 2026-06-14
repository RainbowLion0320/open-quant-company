from __future__ import annotations

from astrolabe_cli.results import CliResult
from agent_os.evidence import EvidenceResolver
from agent_os.runtime import AgentRuntime


def sessions() -> CliResult:
    runtime = AgentRuntime()
    rows = runtime.list_sessions()
    return CliResult(
        ok=True,
        command="agent sessions",
        message=f"{len(rows)} agent session(s)",
        data={"sessions": rows, "total": len(rows)},
    )


def create_session(title: str, default_desk: str) -> CliResult:
    session = AgentRuntime().create_session(title=title, default_desk=default_desk)
    return CliResult(
        ok=True,
        command="agent session create",
        message=f"Created agent session {session.session_id}",
        data={"session": session.to_dict()},
    )


def show_session(session_id: str) -> CliResult:
    payload = AgentRuntime().get_session(session_id)
    return CliResult(
        ok=payload is not None,
        command="agent session show",
        message="Agent session found" if payload else "Agent session missing",
        data=payload or {"session_id": session_id},
        errors=[] if payload else [f"missing_session:{session_id}"],
    )


def update_session(
    session_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    default_desk: str | None = None,
    tags: list[str] | None = None,
) -> CliResult:
    try:
        session = AgentRuntime().update_session(
            session_id,
            title=title,
            status=status,
            default_desk=default_desk,
            tags=tags,
        )
    except KeyError as exc:
        return CliResult(False, "agent session update", {"session_id": session_id}, "Agent session missing", [str(exc)])
    except ValueError as exc:
        return CliResult(False, "agent session update", {"session_id": session_id}, "Agent session update invalid", [str(exc)])
    return CliResult(
        ok=True,
        command="agent session update",
        message=f"Updated agent session {session_id}",
        data={"session": session.to_dict()},
    )


def add_message(session_id: str, desk: str, text: str) -> CliResult:
    try:
        message = AgentRuntime().add_message(session_id, role="ceo", desk=desk, content=text)
    except KeyError as exc:
        return CliResult(False, "agent message", {"session_id": session_id}, "Agent session missing", [str(exc)])
    return CliResult(
        ok=True,
        command="agent message",
        message=f"Added message {message.message_id}",
        data={"message": message.to_dict()},
    )


def actions(session_id: str = "") -> CliResult:
    runtime = AgentRuntime()
    rows = runtime.list_actions(session_id or None)
    return CliResult(
        ok=True,
        command="agent actions",
        message=f"{len(rows)} agent action(s)",
        data={"actions": rows, "total": len(rows)},
    )


def handoffs(session_id: str = "") -> CliResult:
    runtime = AgentRuntime()
    rows = runtime.list_handoffs(session_id or None)
    return CliResult(
        ok=True,
        command="agent handoffs",
        message=f"{len(rows)} agent handoff(s)",
        data={"handoffs": rows, "total": len(rows)},
    )


def resolve_handoff(handoff_id: str) -> CliResult:
    try:
        handoff = AgentRuntime().resolve_handoff(handoff_id)
    except KeyError as exc:
        return CliResult(False, "agent handoff resolve", {"handoff_id": handoff_id}, "Agent handoff missing", [str(exc)])
    return CliResult(
        ok=True,
        command="agent handoff resolve",
        message=f"Resolved {handoff_id}",
        data={"handoff": handoff},
    )


def show_action(action_id: str) -> CliResult:
    runtime = AgentRuntime()
    action = runtime.get_action(action_id)
    if action is None:
        return CliResult(False, "agent action show", {"action_id": action_id}, "Agent action missing", [f"missing_action:{action_id}"])
    runs = runtime.list_runs(action_id)
    return CliResult(
        ok=True,
        command="agent action show",
        message=f"Agent action {action_id}",
        data={"action": action, "runs": runs},
    )


def run_action(action_id: str) -> CliResult:
    try:
        run = AgentRuntime().dispatch_action(action_id)
    except KeyError as exc:
        return CliResult(False, "agent run", {"action_id": action_id}, "Agent action missing", [str(exc)])
    ok = run.status == "succeeded"
    return CliResult(
        ok=ok,
        command="agent run",
        message=f"Agent run {run.status}",
        data={"run": run.to_dict()},
        errors=[] if ok else [run.stderr_summary or run.status],
    )


def approve(action_id: str) -> CliResult:
    try:
        action = AgentRuntime().approve_action(action_id)
    except KeyError as exc:
        return CliResult(False, "agent approve", {"action_id": action_id}, "Agent action missing", [str(exc)])
    return CliResult(True, "agent approve", {"action": action.to_dict()}, f"Approved {action_id}")


def reject(action_id: str, reason: str) -> CliResult:
    try:
        action = AgentRuntime().reject_action(action_id, reason=reason)
    except KeyError as exc:
        return CliResult(False, "agent reject", {"action_id": action_id}, "Agent action missing", [str(exc)])
    return CliResult(True, "agent reject", {"action": action.to_dict()}, f"Rejected {action_id}")


def cancel(action_id: str, reason: str) -> CliResult:
    try:
        action = AgentRuntime().cancel_action(action_id, reason=reason)
    except KeyError as exc:
        return CliResult(False, "agent cancel", {"action_id": action_id}, "Agent action missing", [str(exc)])
    except ValueError as exc:
        return CliResult(False, "agent cancel", {"action_id": action_id}, "Agent action cannot be canceled", [str(exc)])
    return CliResult(True, "agent cancel", {"action": action.to_dict()}, f"Canceled {action_id}")


def evidence(evidence_id: str) -> CliResult:
    payload = EvidenceResolver().resolve(evidence_id)
    ok = payload.get("status") not in {"missing_evidence"}
    return CliResult(
        ok=ok,
        command="agent evidence",
        message=str(payload.get("status")),
        data=payload,
        errors=[] if ok else [str(payload.get("status"))],
    )


def desks() -> CliResult:
    rows = AgentRuntime().list_desks()
    return CliResult(
        ok=True,
        command="agent desks",
        message=f"{len(rows)} desk agent(s)",
        data={"desks": rows, "total": len(rows)},
    )


def memory_summary() -> CliResult:
    snapshot = AgentRuntime().memory_snapshot()
    return CliResult(
        ok=True,
        command="agent memory",
        message="Agent memory summary",
        data=snapshot,
    )


def memory_export() -> CliResult:
    artifact = AgentRuntime().export_memory()
    return CliResult(
        ok=True,
        command="agent memory export",
        message=f"Exported agent memory to {artifact['path']}",
        data={"artifact": artifact},
    )


def memory_prune(dry_run: bool) -> CliResult:
    result = AgentRuntime().prune_memory(dry_run=dry_run)
    return CliResult(
        ok=True,
        command="agent memory prune",
        message="Agent memory prune dry-run" if dry_run else "Pruned archived agent memory",
        data={"result": result},
    )


def memory_clear(confirm: bool, dry_run: bool) -> CliResult:
    try:
        result = AgentRuntime().clear_memory(confirm=confirm, dry_run=dry_run)
    except ValueError as exc:
        return CliResult(False, "agent memory clear", {}, "Agent memory clear requires confirmation", [str(exc)])
    return CliResult(
        ok=True,
        command="agent memory clear",
        message="Agent memory clear dry-run" if dry_run else "Cleared agent memory",
        data={"result": result},
    )
