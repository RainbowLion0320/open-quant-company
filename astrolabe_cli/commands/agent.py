from __future__ import annotations

from astrolabe_cli.results import CliResult
from agent_os.evidence import EvidenceResolver
from agent_os.runtime import AgentRuntime
from agent_os.semantic_planner import semantic_planner_from_cli


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


def run_session_read_only_actions(session_id: str) -> CliResult:
    try:
        workflow = AgentRuntime().run_session_read_only_actions(session_id)
    except KeyError as exc:
        return CliResult(
            False,
            "agent session run-readonly",
            {"session_id": session_id},
            "Agent session missing",
            [str(exc)],
        )
    ok = workflow["status"] == "ready"
    return CliResult(
        ok=ok,
        command="agent session run-readonly",
        message=(
            f"Ran {workflow['run_count']} read-only action(s), "
            f"skipped {workflow['skipped_count']} action(s)"
        ),
        data={"workflow": workflow},
        errors=[] if ok else [f"workflow_status:{workflow['status']}"],
    )


def autonomy_step(
    session_id: str,
    text: str,
    desk: str = "reporting",
    semantic_draft_file: str = "",
    *,
    provider_semantic: bool = False,
    planner_provider: str = "",
    planner_model: str = "",
) -> CliResult:
    try:
        step = AgentRuntime().run_autonomy_step(
            session_id,
            content=text,
            desk=desk,
            semantic_planner=semantic_planner_from_cli(
                semantic_draft_file=semantic_draft_file,
                provider_semantic=provider_semantic,
                planner_provider=planner_provider,
                planner_model=planner_model,
            ),
        )
    except KeyError as exc:
        return CliResult(False, "agent autonomy step", {"session_id": session_id}, "Agent session missing", [str(exc)])
    except ValueError as exc:
        return CliResult(False, "agent autonomy step", {"session_id": session_id, "desk": desk}, "Agent autonomy step invalid", [str(exc)])
    ok = step["status"] in {"ready", "partial"}
    return CliResult(
        ok=ok,
        command="agent autonomy step",
        message=(
            f"Bounded autonomy step {step['status']}: "
            f"ran {step['run_count']} action(s), skipped {step['skipped_count']} action(s)"
        ),
        data={"step": step},
        errors=[] if ok else [str(step["status"])],
    )


def add_message(
    session_id: str,
    desk: str,
    text: str,
    semantic_draft_file: str = "",
    *,
    provider_semantic: bool = False,
    planner_provider: str = "",
    planner_model: str = "",
) -> CliResult:
    try:
        routed = AgentRuntime().submit_ceo_message(
            session_id,
            desk=desk,
            content=text,
            semantic_planner=semantic_planner_from_cli(
                semantic_draft_file=semantic_draft_file,
                provider_semantic=provider_semantic,
                planner_provider=planner_provider,
                planner_model=planner_model,
            ),
        )
    except KeyError as exc:
        return CliResult(False, "agent message", {"session_id": session_id}, "Agent session missing", [str(exc)])
    except ValueError as exc:
        return CliResult(False, "agent message", {"session_id": session_id, "desk": desk}, "Agent message invalid", [str(exc)])
    message = routed["message"]
    desk_response = routed["desk_response"]
    return CliResult(
        ok=True,
        command="agent message",
        message=f"Added message {message.message_id}",
        data={"message": message.to_dict(), "desk_response": desk_response.to_dict()},
    )


def plan(
    desk: str,
    text: str,
    semantic_draft_file: str = "",
    *,
    provider_semantic: bool = False,
    planner_provider: str = "",
    planner_model: str = "",
) -> CliResult:
    try:
        workflow_plan = AgentRuntime().preview_workflow_plan(
            desk=desk,
            content=text,
            semantic_planner=semantic_planner_from_cli(
                semantic_draft_file=semantic_draft_file,
                provider_semantic=provider_semantic,
                planner_provider=planner_provider,
                planner_model=planner_model,
            ),
        )
    except ValueError as exc:
        return CliResult(False, "agent plan", {"desk": desk}, "Agent workflow plan invalid", [str(exc)])
    return CliResult(
        ok=True,
        command="agent plan",
        message=f"Planned {len(workflow_plan['actions'])} agent action(s)",
        data={"plan": workflow_plan},
    )


def actions(session_id: str = "", status: str = "", desk: str = "", risk_level: str = "") -> CliResult:
    runtime = AgentRuntime()
    rows = runtime.list_actions(
        session_id or None,
        status=status or None,
        desk=desk or None,
        risk_level=risk_level or None,
    )
    return CliResult(
        ok=True,
        command="agent actions",
        message=f"{len(rows)} agent action(s)",
        data={
            "actions": rows,
            "total": len(rows),
            "filters": {
                "session_id": session_id,
                "status": status,
                "desk": desk,
                "risk_level": risk_level,
            },
        },
    )


def expire_actions(session_id: str = "") -> CliResult:
    result = AgentRuntime().expire_actions(session_id=session_id or None)
    return CliResult(
        ok=True,
        command="agent expire",
        message=f"Expired {result['expired']} agent action(s)",
        data={"result": result},
    )


def reports(session_id: str = "") -> CliResult:
    result = AgentRuntime().list_reports(session_id or None)
    return CliResult(
        ok=True,
        command="agent reports",
        message=f"{result['total']} agent report(s)",
        data=result,
    )


def generate_report(kind: str, session_id: str) -> CliResult:
    try:
        report = AgentRuntime().generate_report(session_id=session_id, kind=kind)
    except KeyError as exc:
        return CliResult(False, "agent report", {"session_id": session_id}, "Agent session missing", [str(exc)])
    except ValueError as exc:
        return CliResult(False, "agent report", {"kind": kind}, "Agent report invalid", [str(exc)])
    return CliResult(
        ok=True,
        command="agent report",
        message=f"Generated {report['kind']} report",
        data={"report": report},
    )


def run_report_rhythm(
    session_id: str,
    *,
    force: bool = False,
    notify: bool = False,
    notification_channels: list[str] | None = None,
    dry_run_notifications: bool = False,
) -> CliResult:
    try:
        rhythm = AgentRuntime().run_report_rhythm(
            session_id=session_id,
            force=force,
            notify=notify,
            notification_channels=notification_channels,
            dry_run_notifications=dry_run_notifications,
        )
    except KeyError as exc:
        return CliResult(False, "agent rhythm", {"session_id": session_id}, "Agent session missing", [str(exc)])
    return CliResult(
        ok=True,
        command="agent rhythm",
        message=f"Generated {rhythm['generated_count']} report(s), skipped {rhythm['skipped_count']} report(s)",
        data={"rhythm": rhythm},
    )


def run_scheduled_report_rhythm(
    *,
    force: bool = False,
    notify: bool = False,
    notification_channels: list[str] | None = None,
    dry_run_notifications: bool = False,
) -> CliResult:
    schedule = AgentRuntime().run_scheduled_report_rhythm(
        force=force,
        notify=notify,
        notification_channels=notification_channels,
        dry_run_notifications=dry_run_notifications,
    )
    return CliResult(
        ok=schedule["status"] == "ready",
        command="agent rhythm",
        message=(
            f"Scheduled {schedule['session_count']} session(s), "
            f"generated {schedule['generated_count']} report(s), failed {schedule['failed_count']} session(s)"
        ),
        data={"schedule": schedule},
        errors=[] if schedule["status"] == "ready" else [f"failed_sessions:{schedule['failed_count']}"],
    )


def notify_report(report_id: str, *, channels: list[str] | None = None, dry_run: bool = False) -> CliResult:
    try:
        notification = AgentRuntime().notify_report(report_id, channels=channels, dry_run=dry_run)
    except KeyError as exc:
        return CliResult(False, "agent notify report", {"report_id": report_id}, "Agent report missing", [str(exc)])
    except ValueError as exc:
        return CliResult(False, "agent notify report", {"report_id": report_id}, "Agent notification invalid", [str(exc)])
    ok = notification["status"] in {"sent", "dry_run", "partial"}
    return CliResult(
        ok=ok,
        command="agent notify report",
        message=f"Report notification {notification['status']}",
        data={"notification": notification},
        errors=[] if ok else [f"notification_status:{notification['status']}"],
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


def work_orders(session_id: str = "") -> CliResult:
    result = AgentRuntime().list_work_orders(session_id or None)
    return CliResult(
        ok=True,
        command="agent work-orders",
        message=f"{result['total']} engineering work order(s)",
        data=result,
    )


def create_work_order(
    *,
    session_id: str,
    title: str,
    summary: str,
    impact: str,
    affected_files: list[str] | None = None,
    suggested_verification: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> CliResult:
    try:
        work_order = AgentRuntime().create_work_order(
            session_id=session_id,
            title=title,
            summary=summary,
            impact=impact,
            affected_files=affected_files,
            suggested_verification=suggested_verification,
            evidence_refs=evidence_refs,
        )
    except KeyError as exc:
        return CliResult(False, "agent work-order create", {"session_id": session_id}, "Agent session missing", [str(exc)])
    except ValueError as exc:
        return CliResult(False, "agent work-order create", {"session_id": session_id}, "Agent work order invalid", [str(exc)])
    return CliResult(
        ok=True,
        command="agent work-order create",
        message=f"Created engineering work order {work_order['work_order_id']}",
        data={"work_order": work_order},
    )


def update_work_order(work_order_id: str, *, status: str, resolution: str = "") -> CliResult:
    try:
        work_order = AgentRuntime().update_work_order_status(
            work_order_id,
            status=status,
            resolution=resolution,
        )
    except KeyError as exc:
        return CliResult(
            False,
            "agent work-order update",
            {"work_order_id": work_order_id},
            "Agent work order missing",
            [str(exc)],
        )
    except ValueError as exc:
        return CliResult(
            False,
            "agent work-order update",
            {"work_order_id": work_order_id, "status": status},
            "Agent work order update invalid",
            [str(exc)],
        )
    return CliResult(
        ok=True,
        command="agent work-order update",
        message=f"Updated engineering work order {work_order['work_order_id']}",
        data={"work_order": work_order},
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
    runs = runtime.list_runs(action_id, include_events=True)
    return CliResult(
        ok=True,
        command="agent action show",
        message=f"Agent action {action_id}",
        data={"action": action, "runs": runs, "paper_reconciliations": runtime.paper_reconciliations_for_action(action_id)},
    )


def run_action(action_id: str) -> CliResult:
    runtime = AgentRuntime()
    try:
        run = runtime.dispatch_action(action_id)
    except KeyError as exc:
        return CliResult(False, "agent run", {"action_id": action_id}, "Agent action missing", [str(exc)])
    ok = run.status == "succeeded"
    run_payload = runtime.get_run(run.run_id) or run.to_dict()
    return CliResult(
        ok=ok,
        command="agent run",
        message=f"Agent run {run.status}",
        data={"run": run_payload},
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


def policies() -> CliResult:
    rows = AgentRuntime().list_approval_policies()
    return CliResult(
        ok=True,
        command="agent policies",
        message=f"{len(rows)} approval policy row(s)",
        data={"policies": rows, "total": len(rows)},
    )


def live_readiness() -> CliResult:
    health = AgentRuntime().live_readiness()
    return CliResult(
        ok=True,
        command="agent live readiness",
        message=f"Live broker readiness: {health['mode']}",
        data={"health": health},
    )


def live_environment() -> CliResult:
    environment = AgentRuntime().live_environment()
    return CliResult(
        ok=True,
        command="agent live environment",
        message=f"Live broker environment: {environment['status']}",
        data={"environment": environment},
    )


def live_smoke() -> CliResult:
    smoke = AgentRuntime().run_live_smoke()
    ok = smoke["status"] in {"ready", "blocked"}
    return CliResult(
        ok=ok,
        command="agent live smoke",
        message=f"Live broker smoke: {smoke['status']}",
        data={"smoke": smoke},
        errors=[] if ok else [str(smoke.get("error") or smoke["status"])],
    )


def live_preview(
    *,
    symbol: str,
    side: str,
    quantity: int,
    limit_price: float,
    strategy: str,
    reason: str,
    evidence_refs: list[str],
) -> CliResult:
    preview = AgentRuntime().preview_live_order(
        {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": "limit",
            "limit_price": limit_price,
            "strategy": strategy,
            "reason": reason,
            "evidence_refs": evidence_refs,
        }
    )
    return CliResult(
        ok=True,
        command="agent live preview",
        message=f"Live order preview: {preview['status']}",
        data={"preview": preview},
    )


def live_propose(
    *,
    session_id: str,
    symbol: str,
    side: str,
    quantity: int,
    limit_price: float,
    strategy: str,
    reason: str,
    evidence_refs: list[str],
) -> CliResult:
    try:
        proposal = AgentRuntime().propose_live_order(
            session_id=session_id,
            intent={
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": "limit",
                "limit_price": limit_price,
                "strategy": strategy,
                "reason": reason,
                "evidence_refs": evidence_refs,
            },
        )
    except KeyError as exc:
        return CliResult(False, "agent live propose", {"session_id": session_id}, "Agent session missing", [str(exc)])
    return CliResult(
        ok=True,
        command="agent live propose",
        message=f"Live order proposal: {proposal['status']}",
        data={"proposal": proposal},
    )


def live_submit(action_id: str) -> CliResult:
    try:
        submission = AgentRuntime().submit_live_order_action(action_id)
    except KeyError as exc:
        return CliResult(False, "agent live submit", {"action_id": action_id}, "Agent action missing", [str(exc)])
    ok = submission["status"] == "succeeded"
    return CliResult(
        ok=ok,
        command="agent live submit",
        message=f"Live order submit: {submission['status']}",
        data={"submission": submission},
        errors=[] if ok else [submission["run"]["stderr_summary"] or submission["status"]],
    )


def live_kill_switch_status() -> CliResult:
    kill_switch = AgentRuntime().live_kill_switch_status()
    return CliResult(
        ok=True,
        command="agent live kill-switch status",
        message=f"Live kill switch: {kill_switch['status']}",
        data={"kill_switch": kill_switch},
    )


def live_kill_switch_activate(reason: str) -> CliResult:
    kill_switch = AgentRuntime().activate_live_kill_switch(reason=reason)
    return CliResult(
        ok=True,
        command="agent live kill-switch activate",
        message=f"Live kill switch activated; canceled {kill_switch['canceled_count']} action(s)",
        data={"kill_switch": kill_switch},
    )


def live_kill_switch_deactivate(reason: str) -> CliResult:
    kill_switch = AgentRuntime().deactivate_live_kill_switch(reason=reason)
    return CliResult(
        ok=True,
        command="agent live kill-switch deactivate",
        message="Live kill switch deactivated",
        data={"kill_switch": kill_switch},
    )


def live_reconcile(session_id: str = "") -> CliResult:
    reconciliation = AgentRuntime().run_live_reconciliation(session_id=session_id or None)
    ok = reconciliation["status"] in {"ready", "partial"}
    return CliResult(
        ok=ok,
        command="agent live reconcile",
        message=(
            f"Live reconciliation {reconciliation['status']}: "
            f"{reconciliation['reconciled_count']} reconciled, "
            f"{reconciliation['skipped_count']} skipped"
        ),
        data={"reconciliation": reconciliation},
        errors=[] if ok else [str(reconciliation["status"])],
    )


def live_monitor(session_id: str = "") -> CliResult:
    monitor = AgentRuntime().run_live_monitor(session_id=session_id or None)
    ok = monitor["status"] in {"ready", "partial", "blocked"}
    return CliResult(
        ok=ok,
        command="agent live monitor",
        message=(
            f"Live monitor {monitor['status']}: "
            f"readiness={monitor['readiness'].get('mode', 'unknown')}, "
            f"reconciliation={monitor['reconciliation'].get('status', 'unknown')}"
        ),
        data={"monitor": monitor},
        errors=[] if ok else [str(monitor["status"])],
    )


def paper_propose(
    *,
    session_id: str,
    symbol: str,
    side: str,
    quantity: int,
    limit_price: float,
    strategy: str,
    reason: str,
    evidence_refs: list[str],
) -> CliResult:
    try:
        proposal = AgentRuntime().propose_paper_order(
            session_id=session_id,
            intent={
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": "limit",
                "limit_price": limit_price,
                "strategy": strategy,
                "reason": reason,
                "evidence_refs": evidence_refs,
            },
        )
    except KeyError as exc:
        return CliResult(False, "agent paper propose", {"session_id": session_id}, "Agent session missing", [str(exc)])
    return CliResult(
        ok=True,
        command="agent paper propose",
        message=f"Paper order proposal: {proposal['status']}",
        data={"proposal": proposal},
    )


def paper_submit(action_id: str) -> CliResult:
    try:
        submission = AgentRuntime().submit_paper_order_action(action_id)
    except KeyError as exc:
        return CliResult(False, "agent paper submit", {"action_id": action_id}, "Agent action missing", [str(exc)])
    ok = submission["status"] == "succeeded"
    return CliResult(
        ok=ok,
        command="agent paper submit",
        message=f"Paper order submit: {submission['status']}",
        data={"submission": submission},
        errors=[] if ok else [submission["run"]["stderr_summary"] or submission["status"]],
    )


def paper_cancel(action_id: str, reason: str) -> CliResult:
    try:
        cancellation = AgentRuntime().cancel_paper_order_action(action_id, reason=reason)
    except KeyError as exc:
        return CliResult(False, "agent paper cancel", {"action_id": action_id}, "Agent action missing", [str(exc)])
    ok = cancellation["status"] == "canceled"
    return CliResult(
        ok=ok,
        command="agent paper cancel",
        message=f"Paper order cancel: {cancellation['status']}",
        data={"cancellation": cancellation},
        errors=[] if ok else [cancellation["run"]["stderr_summary"] or cancellation["status"]],
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
