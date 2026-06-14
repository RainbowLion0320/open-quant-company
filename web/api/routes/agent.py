"""Agent Company OS local runtime routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agent_os.evidence import EvidenceResolver
from agent_os.runtime import AgentRuntime
from web.api.errors import DataNotFoundError, InvalidParameterError

router = APIRouter(prefix="/api/agent", tags=["Agent"])


@router.get("/sessions")
async def list_agent_sessions() -> dict[str, Any]:
    sessions = AgentRuntime().list_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@router.post("/sessions")
async def create_agent_session(payload: dict[str, Any]) -> dict[str, Any]:
    session = AgentRuntime().create_session(
        title=str(payload.get("title") or "Untitled session"),
        default_desk=str(payload.get("default_desk") or "reporting"),
        tags=list(payload.get("tags") or []),
    )
    return {"session": session.to_dict()}


@router.get("/sessions/{session_id}")
async def get_agent_session(session_id: str) -> dict[str, Any]:
    payload = AgentRuntime().get_session(session_id)
    if payload is None:
        raise DataNotFoundError("agent session", session_id)
    return payload


@router.patch("/sessions/{session_id}")
async def update_agent_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw_tags = payload.get("tags") if "tags" in payload else None
    if raw_tags is not None and not isinstance(raw_tags, list):
        raise InvalidParameterError("tags", str(raw_tags), "expected a list")
    try:
        session = AgentRuntime().update_session(
            session_id,
            title=payload.get("title") if "title" in payload else None,
            status=payload.get("status") if "status" in payload else None,
            default_desk=payload.get("default_desk") if "default_desk" in payload else None,
            tags=[str(tag) for tag in raw_tags] if raw_tags is not None else None,
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    except ValueError as exc:
        raise InvalidParameterError("session", session_id, str(exc))
    return {"session": session.to_dict()}


@router.post("/sessions/{session_id}/messages")
async def add_agent_message(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role") or "ceo")
    desk = str(payload.get("desk") or "reporting")
    try:
        if role == "ceo":
            routed = AgentRuntime().submit_ceo_message(
                session_id,
                desk=desk,
                content=str(payload.get("content") or ""),
            )
            return {"message": routed["message"].to_dict(), "desk_response": routed["desk_response"].to_dict()}
        message = AgentRuntime().add_message(
            session_id,
            role=role,
            desk=desk,
            content=str(payload.get("content") or ""),
            evidence_refs=list(payload.get("evidence_refs") or []),
            action_refs=list(payload.get("action_refs") or []),
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    except ValueError as exc:
        raise InvalidParameterError("agent_message", session_id, str(exc))
    return {"message": message.to_dict()}


@router.get("/actions")
async def list_agent_actions(session_id: str = "") -> dict[str, Any]:
    actions = AgentRuntime().list_actions(session_id or None)
    return {"actions": actions, "total": len(actions)}


@router.post("/actions/expire")
async def expire_agent_actions(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = AgentRuntime().expire_actions(session_id=str((payload or {}).get("session_id") or "") or None)
    return {"result": result}


@router.get("/reports")
async def list_agent_reports(session_id: str = "") -> dict[str, Any]:
    return AgentRuntime().list_reports(session_id or None)


@router.get("/live/readiness")
async def get_agent_live_readiness() -> dict[str, Any]:
    return {"health": AgentRuntime().live_readiness()}


@router.post("/live/preview")
async def preview_agent_live_order(payload: dict[str, Any]) -> dict[str, Any]:
    return {"preview": AgentRuntime().preview_live_order(payload)}


@router.post("/paper/proposals")
async def propose_agent_paper_order(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        raise InvalidParameterError("session_id", session_id, "expected an agent session id")
    try:
        proposal = AgentRuntime().propose_paper_order(session_id=session_id, intent=payload)
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    return {"proposal": proposal}


@router.post("/paper/actions/{action_id}/submit")
async def submit_agent_paper_order(action_id: str) -> dict[str, Any]:
    try:
        submission = AgentRuntime().submit_paper_order_action(action_id)
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
    return {"submission": submission}


@router.post("/reports")
async def generate_agent_report(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        report = AgentRuntime().generate_report(
            session_id=str(payload.get("session_id") or ""),
            kind=str(payload.get("kind") or "daily_brief"),
        )
    except KeyError:
        raise DataNotFoundError("agent session", str(payload.get("session_id") or ""))
    except ValueError as exc:
        raise InvalidParameterError("agent_report", str(payload.get("kind") or ""), str(exc))
    return {"report": report}


@router.post("/reports/rhythm")
async def run_agent_report_rhythm(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    try:
        rhythm = AgentRuntime().run_report_rhythm(
            session_id=session_id,
            force=bool(payload.get("force") or False),
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    return {"rhythm": rhythm}


@router.get("/handoffs")
async def list_agent_handoffs(session_id: str = "") -> dict[str, Any]:
    handoffs = AgentRuntime().list_handoffs(session_id or None)
    return {"handoffs": handoffs, "total": len(handoffs)}


@router.post("/handoffs/{handoff_id}/resolve")
async def resolve_agent_handoff(handoff_id: str) -> dict[str, Any]:
    try:
        handoff = AgentRuntime().resolve_handoff(handoff_id)
    except KeyError:
        raise DataNotFoundError("agent handoff", handoff_id)
    return {"handoff": handoff}


@router.get("/actions/{action_id}")
async def get_agent_action(action_id: str) -> dict[str, Any]:
    action = AgentRuntime().get_action(action_id)
    if action is None:
        raise DataNotFoundError("agent action", action_id)
    return {"action": action, "runs": AgentRuntime().list_runs(action_id)}


@router.post("/actions/{action_id}/approve")
async def approve_agent_action(action_id: str) -> dict[str, Any]:
    try:
        action = AgentRuntime().approve_action(action_id)
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
    except ValueError as exc:
        raise InvalidParameterError("action_id", action_id, str(exc))
    return {"action": action.to_dict()}


@router.post("/actions/{action_id}/reject")
async def reject_agent_action(action_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        action = AgentRuntime().reject_action(action_id, reason=str((payload or {}).get("reason") or ""))
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
    except ValueError as exc:
        raise InvalidParameterError("action_id", action_id, str(exc))
    return {"action": action.to_dict()}


@router.post("/actions/{action_id}/cancel")
async def cancel_agent_action(action_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        action = AgentRuntime().cancel_action(action_id, reason=str((payload or {}).get("reason") or ""))
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
    except ValueError as exc:
        raise InvalidParameterError("action_id", action_id, str(exc))
    return {"action": action.to_dict()}


@router.post("/actions/{action_id}/run")
async def run_agent_action(action_id: str) -> dict[str, Any]:
    try:
        run = AgentRuntime().dispatch_action(action_id)
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
    return {"run": run.to_dict()}


@router.get("/evidence/{evidence_id}")
async def get_agent_evidence(evidence_id: str) -> dict[str, Any]:
    return EvidenceResolver().resolve(evidence_id)


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str) -> dict[str, Any]:
    run = AgentRuntime().get_run(run_id)
    if run is None:
        raise DataNotFoundError("agent run", run_id)
    return {"run": run}


@router.get("/desks")
async def list_agent_desks() -> dict[str, Any]:
    desks = AgentRuntime().list_desks()
    return {"desks": desks, "total": len(desks)}


@router.get("/memory")
async def get_agent_memory() -> dict[str, Any]:
    return AgentRuntime().memory_snapshot()


@router.post("/memory/export")
async def export_agent_memory() -> dict[str, Any]:
    return {"artifact": AgentRuntime().export_memory()}


@router.post("/memory/prune")
async def prune_agent_memory(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        result = AgentRuntime().prune_memory(
            policy=str((payload or {}).get("policy") or "archived_sessions"),
            dry_run=bool((payload or {}).get("dry_run", False)),
        )
    except ValueError as exc:
        raise InvalidParameterError("policy", str((payload or {}).get("policy") or ""), str(exc))
    return {"result": result}


@router.post("/memory/clear")
async def clear_agent_memory(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        result = AgentRuntime().clear_memory(
            confirm=bool((payload or {}).get("confirm", False)),
            dry_run=bool((payload or {}).get("dry_run", False)),
        )
    except ValueError as exc:
        raise InvalidParameterError("confirm", str((payload or {}).get("confirm") or ""), str(exc))
    return {"result": result}
