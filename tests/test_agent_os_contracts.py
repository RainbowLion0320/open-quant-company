import json
from subprocess import CompletedProcess
from pathlib import Path

from fastapi.testclient import TestClient


def test_agent_runtime_creates_session_message_and_action(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Daily CEO Brief", default_desk="reporting")
    message = runtime.add_message(
        session.session_id,
        role="ceo",
        desk="reporting",
        content="今天系统该做什么？",
    )
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Repair missing stock_limit_list.",
        parameters={"dimension": "stock_limit_list"},
        expected_effect="Write one repaired DataHub partition if approved.",
    )

    assert session.status == "active"
    assert message.message_id.startswith("agt_msg_")
    assert action.status == "approval_required"
    assert action.approval_required is True

    loaded = runtime.get_session(session.session_id)
    assert loaded is not None
    assert loaded["session"]["title"] == "Daily CEO Brief"
    assert loaded["messages"][0]["content"] == "今天系统该做什么？"
    assert loaded["actions"][0]["risk_level"] == "write_data"
    reset_datahub()


def test_agent_approval_policy_blocks_state_changing_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.approval import approval_required_for_risk
    from agent_os.runtime import AgentRuntime

    assert approval_required_for_risk("read_only") is False
    assert approval_required_for_risk("dry_run") is False
    assert approval_required_for_risk("write_data") is True
    assert approval_required_for_risk("paper_order") is True
    assert approval_required_for_risk("live_order") is True
    assert approval_required_for_risk("code_change") is True

    runtime = AgentRuntime()
    session = runtime.create_session(title="Approval test")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="execution",
        action_type="paper_order",
        risk_level="paper_order",
        summary="Buy preview",
        parameters={"symbol": "600000.SH"},
        expected_effect="Would submit a PaperBroker order after approval.",
    )

    approved = runtime.approve_action(action.action_id, decided_by="ceo")

    assert approved.status == "approved"
    assert approved.approval_decision["decision"] == "approved"
    assert runtime.get_action(action.action_id)["approval_decision"]["decided_by"] == "ceo"
    reset_datahub()


def test_agent_evidence_resolver_reports_missing_and_fresh_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.evidence import EvidenceResolver
    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    artifact = tmp_path / "runtime" / "artifacts" / "lifecycle" / "latest.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps({"status": "ok"}, ensure_ascii=False), encoding="utf-8")

    evidence = runtime.create_evidence(
        kind="artifact",
        label="Lifecycle latest",
        uri=str(artifact),
        summary="Lifecycle readiness latest artifact.",
    )

    fresh = EvidenceResolver().resolve(evidence.evidence_id)
    missing = EvidenceResolver().resolve("ev_missing")

    assert fresh["status"] == "fresh"
    assert fresh["evidence"]["hash"].startswith("sha256:")
    assert missing["status"] == "missing_evidence"
    reset_datahub()


def test_agent_cli_creates_and_lists_sessions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli

    create_code = run_cli(["agent", "session", "create", "--title", "CEO Brief", "--json"])
    create_payload = json.loads(capsys.readouterr().out)
    list_code = run_cli(["agent", "sessions", "--json"])
    list_payload = json.loads(capsys.readouterr().out)

    assert create_code == 0
    assert create_payload["ok"] is True
    assert create_payload["data"]["session"]["title"] == "CEO Brief"
    assert list_code == 0
    assert list_payload["data"]["sessions"][0]["title"] == "CEO Brief"
    reset_datahub()


def test_agent_api_reads_local_ledger_without_running_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="API session", default_desk="data")
    runtime.add_message(session.session_id, role="ceo", desk="data", content="检查数据缺口")

    client = TestClient(create_app())
    sessions = client.get("/api/agent/sessions")
    detail = client.get(f"/api/agent/sessions/{session.session_id}")
    desks = client.get("/api/agent/desks")

    assert sessions.status_code == 200
    assert sessions.json()["sessions"][0]["title"] == "API session"
    assert detail.status_code == 200
    assert detail.json()["messages"][0]["content"] == "检查数据缺口"
    assert desks.status_code == 200
    assert {desk["desk_id"] for desk in desks.json()["desks"]} >= {"data", "research", "risk"}
    reset_datahub()


def test_agent_runtime_records_run_and_tool_registry_uses_fixed_command_arrays(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from agent_os.tools import AgentToolRegistry

    registry = AgentToolRegistry()
    health_tool = registry.get("astroq.health")
    assert health_tool is not None
    health_command = registry.command_for("astroq.health")
    assert Path(health_command[0]).name == "astroq"
    assert health_command[0] != "astroq"
    assert health_command[1:] == ["health", "--json"]

    try:
        registry.command_for("astroq.data.repair", {"table": "x; rm -rf /"})
    except ValueError as exc:
        assert "requires explicit approval" in str(exc)
    else:
        raise AssertionError("write-capable templated command should not be available without an approved action")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Run ledger")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="health_check",
        risk_level="read_only",
        summary="Check health",
    )
    run = runtime.record_run(
        action_id=action.action_id,
        tool_name="astroq.health",
        command=registry.command_for("astroq.health"),
        status="succeeded",
        return_code=0,
        stdout_summary="ok",
        stderr_summary="",
    )

    loaded = runtime.get_run(run.run_id)
    assert loaded["tool_name"] == "astroq.health"
    assert Path(loaded["command"][0]).name == "astroq"
    assert loaded["command"][1:] == ["health", "--json"]
    assert runtime.get_session(session.session_id)["runs"][0]["run_id"] == run.run_id
    reset_datahub()


def test_agent_dispatch_runs_read_only_tool_and_updates_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Dispatch read-only")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Run health check",
        parameters={"tool_id": "astroq.health"},
        expected_effect="Records health status in the run ledger.",
    )

    run = runtime.dispatch_action(action.action_id, runner=fake_run)

    assert len(calls) == 1
    assert Path(calls[0][0]).name == "astroq"
    assert calls[0][0] != "astroq"
    assert calls[0][1:] == ["health", "--json"]
    assert run.status == "succeeded"
    assert run.return_code == 0
    assert json.loads(run.stdout_summary)["ok"] is True
    assert runtime.get_action(action.action_id)["status"] == "succeeded"
    assert runtime.get_session(session.session_id)["runs"][0]["run_id"] == run.run_id
    reset_datahub()


def test_agent_dispatch_blocks_unapproved_state_changing_action_without_running(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout="should not run", stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Blocked write")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Repair stock_limit_list",
        parameters={"tool_id": "astroq.data.repair", "table": "stock_limit_list"},
        expected_effect="Would write repaired data if approved.",
    )

    run = runtime.dispatch_action(action.action_id, runner=fake_run)

    assert calls == []
    assert run.status == "blocked"
    assert "approval" in run.stderr_summary
    assert runtime.get_action(action.action_id)["status"] == "approval_required"
    reset_datahub()


def test_agent_runtime_rejects_desk_tool_outside_allowed_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Desk permission proposal")

    try:
        runtime.propose_action(
            session_id=session.session_id,
            desk="research",
            action_type="data_status",
            risk_level="read_only",
            summary="Research desk should not run Data Desk tools.",
            parameters={"tool_id": "astroq.data.status"},
        )
    except PermissionError as exc:
        assert "research" in str(exc)
        assert "astroq.data.status" in str(exc)
    else:
        raise AssertionError("desk should not be allowed to propose tools outside its scope")
    reset_datahub()


def test_agent_dispatch_blocks_ledger_action_when_tool_scope_is_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout="should not run", stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Dispatch invalid desk scope")
    runtime.ledger.insert_action(
        {
            "action_id": "act_external_bad_scope",
            "session_id": session.session_id,
            "desk": "research",
            "action_type": "data_status",
            "risk_level": "read_only",
            "status": "proposed",
            "summary": "Externally inserted action with an invalid tool scope.",
            "parameters": {"tool_id": "astroq.data.status"},
            "expected_effect": "Should be blocked before command dispatch.",
            "evidence_refs": [],
            "approval_required": False,
            "approval_decision": None,
            "created_at": "2026-06-14T00:00:00Z",
            "updated_at": "2026-06-14T00:00:00Z",
        }
    )

    run = runtime.dispatch_action("act_external_bad_scope", runner=fake_run)

    assert calls == []
    assert run.status == "blocked"
    assert "not allowed" in run.stderr_summary
    assert runtime.get_action("act_external_bad_scope")["status"] == "blocked"
    reset_datahub()


def test_agent_dispatch_allows_tool_when_desk_scope_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout='{"data": true}', stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Dispatch valid desk scope")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="data_status",
        risk_level="read_only",
        summary="Data desk checks local data health.",
        parameters={"tool_id": "astroq.data.status"},
    )

    run = runtime.dispatch_action(action.action_id, runner=fake_run)

    assert len(calls) == 1
    assert calls[0][1:] == ["data", "status", "--json"]
    assert run.status == "succeeded"
    reset_datahub()


def test_agent_cli_action_show_and_api_run_detail(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Action show")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="risk",
        action_type="lifecycle_check",
        risk_level="read_only",
        summary="Check lifecycle",
    )
    run = runtime.record_run(
        action_id=action.action_id,
        tool_name="astroq.lifecycle.check",
        command=[".venv/bin/astroq", "lifecycle", "check", "--json"],
        status="succeeded",
        return_code=0,
        stdout_summary="blocked",
        stderr_summary="",
    )

    code = run_cli(["agent", "action", "show", action.action_id, "--json"])
    payload = json.loads(capsys.readouterr().out)
    res = TestClient(create_app()).get(f"/api/agent/runs/{run.run_id}")

    assert code == 0
    assert payload["data"]["action"]["summary"] == "Check lifecycle"
    assert payload["data"]["runs"][0]["run_id"] == run.run_id
    assert res.status_code == 200
    assert res.json()["run"]["stdout_summary"] == "blocked"
    reset_datahub()


def test_agent_cli_and_api_dispatch_action_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    def fake_run(command, **kwargs):
        return CompletedProcess(command, 0, stdout='{"cli": true}', stderr="")

    monkeypatch.setattr("agent_os.runtime.subprocess.run", fake_run)

    runtime = AgentRuntime()
    session = runtime.create_session(title="Dispatch API")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Run health",
        parameters={"tool_id": "astroq.health"},
    )

    code = run_cli(["agent", "run", action.action_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)

    action2 = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Run health again",
        parameters={"tool_id": "astroq.health"},
    )
    api_res = TestClient(create_app()).post(f"/api/agent/actions/{action2.action_id}/run")

    assert code == 0
    assert cli_payload["data"]["run"]["status"] == "succeeded"
    assert api_res.status_code == 200
    assert api_res.json()["run"]["status"] == "succeeded"
    reset_datahub()


def test_desk_response_records_structured_reply_and_handoff(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Strategy blocker review", default_desk="research")
    ceo_message = runtime.add_message(
        session.session_id,
        role="ceo",
        desk="research",
        content="为什么策略被阻断，是否是数据问题？",
    )

    response = runtime.respond_as_desk(
        session_id=session.session_id,
        source_message_id=ceo_message.message_id,
        desk="research",
        answer="策略证据缺口需要先由 Data Desk 确认数据覆盖。",
        confidence=0.74,
        blockers=["missing_score_panel"],
        handoffs=[{"target_desk": "data", "reason": "确认 strategy evidence 的数据覆盖缺口"}],
    )

    loaded = runtime.get_session(session.session_id)
    handoffs = runtime.list_handoffs(session.session_id)

    assert response.message.role == "desk_agent"
    assert response.answer.startswith("策略证据缺口")
    assert response.confidence == 0.74
    assert response.blockers == ["missing_score_panel"]
    assert response.handoffs[0]["target_desk"] == "data"
    assert any(message["message_id"] == response.message.message_id for message in loaded["messages"])
    assert loaded["handoffs"][0]["source_desk"] == "research"
    assert handoffs[0]["status"] == "open"
    reset_datahub()


def test_desk_response_rejects_invalid_handoff_target(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Invalid handoff", default_desk="execution")
    message = runtime.add_message(session.session_id, role="ceo", desk="execution", content="需要改代码吗？")

    try:
        runtime.respond_as_desk(
            session_id=session.session_id,
            source_message_id=message.message_id,
            desk="execution",
            answer="Execution Desk 不能直接交给不存在的 desk。",
            handoffs=[{"target_desk": "engineering", "reason": "not allowed for execution"}],
        )
    except ValueError as exc:
        assert "handoff" in str(exc)
    else:
        raise AssertionError("invalid handoff target should fail")
    reset_datahub()


def test_agent_cli_and_api_list_handoffs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Handoff API", default_desk="reporting")
    message = runtime.add_message(session.session_id, role="ceo", desk="reporting", content="今天哪些 desk 要处理？")
    runtime.respond_as_desk(
        session_id=session.session_id,
        source_message_id=message.message_id,
        desk="reporting",
        answer="需要 Data Desk 检查数据阻断。",
        handoffs=[{"target_desk": "data", "reason": "数据阻断需要确认"}],
    )

    code = run_cli(["agent", "handoffs", "--session", session.session_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).get(f"/api/agent/handoffs?session_id={session.session_id}")

    assert code == 0
    assert cli_payload["data"]["handoffs"][0]["target_desk"] == "data"
    assert api_res.status_code == 200
    assert api_res.json()["handoffs"][0]["reason"] == "数据阻断需要确认"
    reset_datahub()


def test_agent_runtime_resolves_handoff_with_audit_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Resolve handoff", default_desk="reporting")
    message = runtime.add_message(session.session_id, role="ceo", desk="reporting", content="处理交接")
    response = runtime.respond_as_desk(
        session_id=session.session_id,
        source_message_id=message.message_id,
        desk="reporting",
        answer="交给 Data Desk。",
        handoffs=[{"target_desk": "data", "reason": "确认数据缺口"}],
    )
    handoff_id = response.handoffs[0]["handoff_id"]

    resolved = runtime.resolve_handoff(handoff_id, resolved_by="ceo")

    assert resolved["handoff_id"] == handoff_id
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"]
    assert runtime.list_handoffs(session.session_id)[0]["status"] == "resolved"

    try:
        runtime.resolve_handoff("handoff_missing")
    except KeyError as exc:
        assert "handoff_missing" in str(exc)
    else:
        raise AssertionError("missing handoff should fail")
    reset_datahub()


def test_agent_cli_and_api_resolve_handoff(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Resolve Handoff API", default_desk="reporting")
    message = runtime.add_message(session.session_id, role="ceo", desk="reporting", content="处理交接")
    first = runtime.respond_as_desk(
        session_id=session.session_id,
        source_message_id=message.message_id,
        desk="reporting",
        answer="需要 Data Desk。",
        handoffs=[{"target_desk": "data", "reason": "数据阻断"}],
    ).handoffs[0]
    second = runtime.respond_as_desk(
        session_id=session.session_id,
        source_message_id=message.message_id,
        desk="reporting",
        answer="需要 Research Desk。",
        handoffs=[{"target_desk": "research", "reason": "策略证据"}],
    ).handoffs[0]

    cli_code = run_cli(["agent", "handoff", "resolve", first["handoff_id"], "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(f"/api/agent/handoffs/{second['handoff_id']}/resolve")

    assert cli_code == 0
    assert cli_payload["data"]["handoff"]["status"] == "resolved"
    assert api_res.status_code == 200
    assert api_res.json()["handoff"]["status"] == "resolved"
    assert runtime.list_handoffs(session.session_id)[0]["status"] == "resolved"
    reset_datahub()
