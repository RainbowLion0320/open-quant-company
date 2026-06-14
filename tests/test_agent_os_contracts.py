import json

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
    assert health_tool.command == ["astroq", "health", "--json"]
    assert registry.command_for("astroq.health") == ["astroq", "health", "--json"]

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
    assert loaded["command"] == ["astroq", "health", "--json"]
    assert runtime.get_session(session.session_id)["runs"][0]["run_id"] == run.run_id
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
        command=["astroq", "lifecycle", "check", "--json"],
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
