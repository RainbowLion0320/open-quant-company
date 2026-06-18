"""Agent Company OS local runtime routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent_os.evidence import EvidenceResolver
from agent_os.runtime import AgentRuntime
from agent_os.semantic_planner import semantic_planner_from_payload
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


@router.get("/model-runtime")
async def get_agent_model_runtime(session_id: str = "") -> dict[str, Any]:
    try:
        return AgentRuntime().model_runtime(session_id or None)
    except KeyError:
        raise DataNotFoundError("agent session", session_id)


@router.get("/sessions/{session_id}")
async def get_agent_session(session_id: str) -> dict[str, Any]:
    payload = AgentRuntime().get_session(session_id)
    if payload is None:
        raise DataNotFoundError("agent session", session_id)
    return payload


@router.get("/sessions/{session_id}/stream")
async def stream_agent_session(session_id: str, once: bool = False, poll_seconds: float = 1.0) -> StreamingResponse:
    if AgentRuntime().get_session(session_id) is None:
        raise DataNotFoundError("agent session", session_id)

    async def event_stream():
        last_signature = ""
        interval = min(max(float(poll_seconds), 0.2), 10.0)
        while True:
            try:
                snapshot = AgentRuntime().session_stream_snapshot(session_id)
            except KeyError:
                missing = {"status": "missing", "session_id": session_id}
                yield f"event: session_missing\ndata: {json.dumps(missing, ensure_ascii=False)}\n\n"
                break
            if snapshot["signature"] != last_signature:
                last_signature = str(snapshot["signature"])
                yield f"event: session_snapshot\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                if once:
                    break
            await asyncio.sleep(interval)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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


@router.post("/sessions/{session_id}/autonomy-step")
async def run_agent_autonomy_step(session_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    try:
        step = AgentRuntime().run_autonomy_step(
            session_id,
            content=str(body.get("content") or body.get("text") or ""),
            desk=str(body.get("desk") or "reporting"),
            semantic_planner=semantic_planner_from_payload(body),
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    except ValueError as exc:
        raise InvalidParameterError("agent_autonomy_step", session_id, str(exc))
    return {"step": step}


@router.post("/sessions/{session_id}/autonomy-run")
async def run_agent_autonomy_run(session_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    try:
        run = AgentRuntime().run_autonomy_loop(
            session_id,
            content=str(body.get("content") or body.get("text") or ""),
            desk=str(body.get("desk") or "reporting"),
            max_steps=int(body.get("max_steps") or 2),
            semantic_planner=semantic_planner_from_payload(body),
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    except ValueError as exc:
        raise InvalidParameterError("agent_autonomy_run", session_id, str(exc))
    return {"run": run}


@router.get("/programs")
async def list_agent_programs(session_id: str = "") -> dict[str, Any]:
    return AgentRuntime().list_autonomy_programs(session_id or None)


@router.post("/sessions/{session_id}/programs")
async def create_agent_program(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        program = AgentRuntime().create_autonomy_program(
            session_id,
            goal=str(payload.get("goal") or payload.get("content") or payload.get("text") or ""),
            desk=str(payload.get("desk") or "reporting"),
            max_steps=int(payload.get("max_steps") or 6),
            semantic_planner=semantic_planner_from_payload(payload),
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    except ValueError as exc:
        raise InvalidParameterError("agent_program", session_id, str(exc))
    return {"program": program}


@router.get("/programs/{program_id}")
async def get_agent_program(program_id: str) -> dict[str, Any]:
    program = AgentRuntime().get_autonomy_program(program_id)
    if program is None:
        raise DataNotFoundError("agent autonomy program", program_id)
    return {"program": program}


@router.post("/programs/{program_id}/run")
async def run_agent_program(program_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    try:
        run = AgentRuntime().run_autonomy_program(
            program_id,
            dry_run=bool(body.get("dry_run") or False),
        )
    except KeyError:
        raise DataNotFoundError("agent autonomy program", program_id)
    return {"run": run}


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
                semantic_planner=semantic_planner_from_payload(payload),
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


@router.post("/plans")
async def preview_agent_workflow_plan(payload: dict[str, Any]) -> dict[str, Any]:
    desk = str(payload.get("desk") or "reporting")
    content = str(payload.get("content") or payload.get("text") or "")
    if not content.strip():
        raise InvalidParameterError("content", content, "expected a non-empty CEO message")
    try:
        plan = AgentRuntime().preview_workflow_plan(
            desk=desk,
            content=content,
            semantic_planner=semantic_planner_from_payload(payload),
        )
    except ValueError as exc:
        raise InvalidParameterError("agent_plan", desk, str(exc))
    return {"plan": plan}


@router.get("/actions")
async def list_agent_actions(
    session_id: str = "",
    status: str = "",
    desk: str = "",
    risk_level: str = "",
) -> dict[str, Any]:
    actions = AgentRuntime().list_actions(
        session_id or None,
        status=status or None,
        desk=desk or None,
        risk_level=risk_level or None,
    )
    return {
        "actions": actions,
        "total": len(actions),
        "filters": {
            "session_id": session_id,
            "status": status,
            "desk": desk,
            "risk_level": risk_level,
        },
    }


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


@router.get("/live/environment")
async def get_agent_live_environment() -> dict[str, Any]:
    return {"environment": AgentRuntime().live_environment()}


@router.post("/live/smoke")
async def run_agent_live_smoke() -> dict[str, Any]:
    return {"smoke": AgentRuntime().run_live_smoke()}


@router.post("/live/preview")
async def preview_agent_live_order(payload: dict[str, Any]) -> dict[str, Any]:
    return {"preview": AgentRuntime().preview_live_order(payload)}


@router.post("/live/proposals")
async def propose_agent_live_order(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        raise InvalidParameterError("session_id", session_id, "expected an agent session id")
    try:
        proposal = AgentRuntime().propose_live_order(session_id=session_id, intent=payload)
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    return {"proposal": proposal}


@router.post("/live/actions/{action_id}/submit")
async def submit_agent_live_order(action_id: str) -> dict[str, Any]:
    try:
        submission = AgentRuntime().submit_live_order_action(action_id)
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
    return {"submission": submission}


@router.get("/live/kill-switch")
async def get_agent_live_kill_switch() -> dict[str, Any]:
    return {"kill_switch": AgentRuntime().live_kill_switch_status()}


@router.post("/live/kill-switch/activate")
async def activate_agent_live_kill_switch(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    kill_switch = AgentRuntime().activate_live_kill_switch(reason=str((payload or {}).get("reason") or ""))
    return {"kill_switch": kill_switch}


@router.post("/live/kill-switch/deactivate")
async def deactivate_agent_live_kill_switch(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    kill_switch = AgentRuntime().deactivate_live_kill_switch(reason=str((payload or {}).get("reason") or ""))
    return {"kill_switch": kill_switch}


@router.post("/live/reconciliation")
async def run_agent_live_reconciliation(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    session_id = str((payload or {}).get("session_id") or "") or None
    reconciliation = AgentRuntime().run_live_reconciliation(session_id=session_id)
    return {"reconciliation": reconciliation}


@router.post("/live/monitor")
async def run_agent_live_monitor(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    session_id = str((payload or {}).get("session_id") or "") or None
    monitor = AgentRuntime().run_live_monitor(session_id=session_id)
    return {"monitor": monitor}


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


@router.post("/paper/actions/{action_id}/cancel")
async def cancel_agent_paper_order(action_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        cancellation = AgentRuntime().cancel_paper_order_action(
            action_id,
            reason=str((payload or {}).get("reason") or ""),
        )
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
    return {"cancellation": cancellation}


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
            notify=bool(payload.get("notify") or False),
            notification_channels=[str(channel) for channel in payload.get("notification_channels", [])],
            dry_run_notifications=bool(payload.get("dry_run_notifications") or False),
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    except ValueError as exc:
        raise InvalidParameterError("agent_report_rhythm", session_id, str(exc))
    return {"rhythm": rhythm}


@router.post("/reports/rhythm/scheduled")
async def run_agent_scheduled_report_rhythm(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    try:
        schedule = AgentRuntime().run_scheduled_report_rhythm(
            force=bool(body.get("force") or False),
            notify=bool(body.get("notify") or False),
            notification_channels=[str(channel) for channel in body.get("notification_channels", [])],
            dry_run_notifications=bool(body.get("dry_run_notifications") or False),
        )
    except ValueError as exc:
        raise InvalidParameterError("agent_scheduled_report_rhythm", "notification_channels", str(exc))
    return {"schedule": schedule}


@router.post("/reports/{report_id}/notify")
async def notify_agent_report(report_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    try:
        notification = AgentRuntime().notify_report(
            report_id,
            channels=[str(channel) for channel in body.get("channels", [])],
            dry_run=bool(body.get("dry_run") or False),
        )
    except KeyError:
        raise DataNotFoundError("agent report", report_id)
    except ValueError as exc:
        raise InvalidParameterError("agent_report_notification", report_id, str(exc))
    return {"notification": notification}


@router.get("/handoffs")
async def list_agent_handoffs(session_id: str = "") -> dict[str, Any]:
    handoffs = AgentRuntime().list_handoffs(session_id or None)
    return {"handoffs": handoffs, "total": len(handoffs)}


@router.get("/work-orders")
async def list_agent_work_orders(session_id: str = "") -> dict[str, Any]:
    return AgentRuntime().list_work_orders(session_id or None)


@router.post("/work-orders")
async def create_agent_work_order(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        raise InvalidParameterError("session_id", session_id, "expected an agent session id")
    try:
        work_order = AgentRuntime().create_work_order(
            session_id=session_id,
            title=str(payload.get("title") or ""),
            summary=str(payload.get("summary") or ""),
            impact=str(payload.get("impact") or ""),
            affected_files=[str(path) for path in payload.get("affected_files", [])],
            suggested_verification=[str(command) for command in payload.get("suggested_verification", [])],
            evidence_refs=[str(evidence_id) for evidence_id in payload.get("evidence_refs", [])],
        )
    except KeyError:
        raise DataNotFoundError("agent session", session_id)
    except ValueError as exc:
        raise InvalidParameterError("work_order", session_id, str(exc))
    return {"work_order": work_order}


@router.patch("/work-orders/{work_order_id}")
async def update_agent_work_order(work_order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        work_order = AgentRuntime().update_work_order_status(
            work_order_id,
            status=str(payload.get("status") or ""),
            resolution=str(payload.get("resolution") or ""),
        )
    except KeyError:
        raise DataNotFoundError("agent work order", work_order_id)
    except ValueError as exc:
        raise InvalidParameterError("work_order", work_order_id, str(exc))
    return {"work_order": work_order}


@router.post("/handoffs/{handoff_id}/resolve")
async def resolve_agent_handoff(handoff_id: str) -> dict[str, Any]:
    try:
        handoff = AgentRuntime().resolve_handoff(handoff_id)
    except KeyError:
        raise DataNotFoundError("agent handoff", handoff_id)
    return {"handoff": handoff}


@router.get("/actions/{action_id}")
async def get_agent_action(action_id: str) -> dict[str, Any]:
    runtime = AgentRuntime()
    action = runtime.get_action(action_id)
    if action is None:
        raise DataNotFoundError("agent action", action_id)
    return {
        "action": action,
        "runs": runtime.list_runs(action_id, include_events=True),
        "paper_reconciliations": runtime.paper_reconciliations_for_action(action_id),
    }


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
    runtime = AgentRuntime()
    try:
        run = runtime.dispatch_action(action_id)
    except KeyError:
        raise DataNotFoundError("agent action", action_id)
    return {"run": runtime.get_run(run.run_id) or run.to_dict()}


@router.get("/evidence/{evidence_id}")
async def get_agent_evidence(evidence_id: str) -> dict[str, Any]:
    return EvidenceResolver().resolve(evidence_id)


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str) -> dict[str, Any]:
    run = AgentRuntime().get_run(run_id)
    if run is None:
        raise DataNotFoundError("agent run", run_id)
    return {"run": run}


@router.get("/runs/{run_id}/stream")
async def stream_agent_run(run_id: str, once: bool = False, poll_seconds: float = 1.0) -> StreamingResponse:
    if AgentRuntime().get_run(run_id) is None:
        raise DataNotFoundError("agent run", run_id)

    async def event_stream():
        last_signature = ""
        interval = min(max(float(poll_seconds), 0.2), 10.0)
        while True:
            try:
                snapshot = AgentRuntime().run_stream_snapshot(run_id)
            except KeyError:
                missing = {"status": "missing", "run_id": run_id}
                yield f"event: run_missing\ndata: {json.dumps(missing, ensure_ascii=False)}\n\n"
                break
            if snapshot["signature"] != last_signature:
                last_signature = str(snapshot["signature"])
                yield f"event: run_snapshot\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                if once:
                    break
            await asyncio.sleep(interval)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/desks")
async def list_agent_desks() -> dict[str, Any]:
    desks = AgentRuntime().list_desks()
    return {"desks": desks, "total": len(desks)}


@router.get("/policies")
async def list_agent_approval_policies() -> dict[str, Any]:
    policies = AgentRuntime().list_approval_policies()
    return {"policies": policies, "total": len(policies)}


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
