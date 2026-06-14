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


@router.post("/sessions/{session_id}/messages")
async def add_agent_message(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        message = AgentRuntime().add_message(
            session_id,
            role=str(payload.get("role") or "ceo"),
            desk=str(payload.get("desk") or "reporting"),
            content=str(payload.get("content") or ""),
            evidence_refs=list(payload.get("evidence_refs") or []),
            action_refs=list(payload.get("action_refs") or []),
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    return {"message": message.to_dict()}


@router.get("/actions")
async def list_agent_actions(session_id: str = "") -> dict[str, Any]:
    actions = AgentRuntime().list_actions(session_id or None)
    return {"actions": actions, "total": len(actions)}


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
    return {"action": action.to_dict()}


@router.post("/actions/{action_id}/reject")
async def reject_agent_action(action_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        action = AgentRuntime().reject_action(action_id, reason=str((payload or {}).get("reason") or ""))
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
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
