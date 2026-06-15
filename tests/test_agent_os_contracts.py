import json
import sys
import types
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


def test_agent_actions_support_session_status_desk_and_risk_filters(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    target_session = runtime.create_session(title="Filtered actions")
    other_session = runtime.create_session(title="Other actions")
    runtime.propose_action(
        session_id=target_session.session_id,
        desk="data",
        action_type="data_status",
        risk_level="read_only",
        summary="Inspect data status",
        parameters={"tool_id": "astroq.data.status"},
    )
    write_action = runtime.propose_action(
        session_id=target_session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Repair missing data",
        parameters={"tool_id": "astroq.data.repair", "dimension": "stock_limit_list"},
    )
    runtime.propose_action(
        session_id=target_session.session_id,
        desk="research",
        action_type="strategy_catalog",
        risk_level="read_only",
        summary="Inspect strategies",
        parameters={"tool_id": "astroq.strategy.catalog"},
    )
    runtime.propose_action(
        session_id=other_session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Other repair",
        parameters={"tool_id": "astroq.data.repair", "dimension": "stock_valuation"},
    )

    runtime_filtered = runtime.list_actions(
        session_id=target_session.session_id,
        status="approval_required",
        desk="data",
        risk_level="write_data",
    )
    cli_code = run_cli(
        [
            "agent",
            "actions",
            "--session",
            target_session.session_id,
            "--status",
            "approval_required",
            "--desk",
            "data",
            "--risk-level",
            "write_data",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).get(
        "/api/agent/actions",
        params={
            "session_id": target_session.session_id,
            "status": "approval_required",
            "desk": "data",
            "risk_level": "write_data",
        },
    )

    assert [row["action_id"] for row in runtime_filtered] == [write_action.action_id]
    assert cli_code == 0
    assert cli_payload["data"]["total"] == 1
    assert cli_payload["data"]["actions"][0]["action_id"] == write_action.action_id
    assert api_res.status_code == 200
    assert api_res.json()["total"] == 1
    assert api_res.json()["actions"][0]["action_id"] == write_action.action_id
    reset_datahub()


def test_agent_runtime_cli_and_api_update_session_metadata(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Original", default_desk="reporting", tags=["daily"])

    updated = runtime.update_session(
        session.session_id,
        title="Runtime renamed",
        status="archived",
        tags=["review", "risk"],
    )

    assert updated.title == "Runtime renamed"
    assert updated.status == "archived"
    assert updated.tags == ["review", "risk"]
    assert updated.updated_at >= session.updated_at

    cli_code = run_cli(
        [
            "agent",
            "session",
            "update",
            session.session_id,
            "--title",
            "CLI renamed",
            "--status",
            "active",
            "--tag",
            "ops",
            "--tag",
            "daily",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).patch(
        f"/api/agent/sessions/{session.session_id}",
        json={"title": "API renamed", "status": "blocked", "tags": ["ceo", "blocked"]},
    )

    assert cli_code == 0
    assert cli_payload["data"]["session"]["title"] == "CLI renamed"
    assert cli_payload["data"]["session"]["status"] == "active"
    assert cli_payload["data"]["session"]["tags"] == ["ops", "daily"]
    assert api_res.status_code == 200
    assert api_res.json()["session"]["title"] == "API renamed"
    assert api_res.json()["session"]["status"] == "blocked"
    assert api_res.json()["session"]["tags"] == ["ceo", "blocked"]
    reset_datahub()


def test_agent_session_stream_snapshot_and_sse_once_api(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Streaming session")
    message = runtime.add_message(
        session.session_id,
        role="ceo",
        desk="reporting",
        content="给我一个实时状态",
    )
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="reporting",
        action_type="lifecycle_check",
        risk_level="read_only",
        summary="Read lifecycle",
        parameters={"tool_id": "astroq.lifecycle.check"},
    )
    run = runtime.record_run(
        action_id=action.action_id,
        tool_name="astroq.lifecycle.check",
        command=["astroq", "lifecycle", "check", "--json"],
        status="succeeded",
        return_code=0,
        stdout_summary="ok",
        stderr_summary="",
    )

    snapshot = runtime.session_stream_snapshot(session.session_id)

    assert snapshot["status"] == "ready"
    assert snapshot["session_id"] == session.session_id
    assert snapshot["counts"]["messages"] == 1
    assert snapshot["counts"]["actions"] == 1
    assert snapshot["counts"]["runs"] == 1
    assert snapshot["latest"]["message_id"] == message.message_id
    assert snapshot["latest"]["action_id"] == action.action_id
    assert snapshot["latest"]["run_id"] == run.run_id
    assert snapshot["signature"]

    with TestClient(create_app()).stream("GET", f"/api/agent/sessions/{session.session_id}/stream?once=true") as response:
        body = response.read().decode("utf-8")

    event_payload = json.loads(body.split("data: ", 1)[1].strip())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: session_snapshot" in body
    assert event_payload["session_id"] == session.session_id
    assert event_payload["counts"]["actions"] == 1
    reset_datahub()


def test_agent_run_stream_snapshot_and_sse_once_api(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Run stream")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Health",
        parameters={"tool_id": "astroq.health"},
    )
    run = runtime.record_run(
        action_id=action.action_id,
        tool_name="astroq.health",
        command=["astroq", "health", "--json"],
        status="succeeded",
        return_code=0,
        stdout_summary="ok",
        stderr_summary="",
    )
    runtime.record_run_event(
        run.run_id,
        action_id=action.action_id,
        event_type="artifact",
        status="succeeded",
        message="Artifact written",
        payload={"artifact": "health"},
    )

    snapshot = runtime.run_stream_snapshot(run.run_id)

    assert snapshot["status"] == "ready"
    assert snapshot["run_id"] == run.run_id
    assert snapshot["action_id"] == action.action_id
    assert snapshot["counts"]["events"] >= 2
    assert snapshot["latest"]["event_type"] == "artifact"
    assert snapshot["latest"]["event_id"]
    assert snapshot["signature"]

    with TestClient(create_app()).stream("GET", f"/api/agent/runs/{run.run_id}/stream?once=true") as response:
        body = response.read().decode("utf-8")

    event_payload = json.loads(body.split("data: ", 1)[1].strip())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: run_snapshot" in body
    assert event_payload["run_id"] == run.run_id
    assert event_payload["counts"]["events"] >= 2
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


def test_agent_approval_policies_are_explicit_runtime_cli_api_contracts(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.approval import ALL_RISK_LEVELS
    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime_policies = AgentRuntime().list_approval_policies()
    by_risk = {policy["risk_level"]: policy for policy in runtime_policies}

    cli_code = run_cli(["agent", "policies", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).get("/api/agent/policies")

    assert set(by_risk) == ALL_RISK_LEVELS
    assert by_risk["read_only"]["default_decision"] == "auto_run"
    assert by_risk["read_only"]["approval_required"] is False
    assert by_risk["dry_run"]["default_decision"] == "auto_run"
    assert by_risk["write_data"]["default_decision"] == "approval_required"
    assert by_risk["write_config"]["required_role"] == "ceo"
    assert by_risk["run_backtest"]["expires_after_seconds"] > 0
    assert by_risk["paper_order"]["approval_required"] is True
    assert by_risk["live_order"]["reason"]
    assert by_risk["code_change"]["default_decision"] == "work_order_required"
    assert all(policy["policy_id"] == f"agent_policy.{policy['risk_level']}" for policy in runtime_policies)
    assert all("reason" in policy and policy["reason"] for policy in runtime_policies)
    assert cli_code == 0
    assert cli_payload["data"]["total"] == len(ALL_RISK_LEVELS)
    assert api_res.status_code == 200
    assert api_res.json()["total"] == len(ALL_RISK_LEVELS)
    reset_datahub()


def test_engineering_work_orders_are_auditable_runtime_cli_api_contracts(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Engineering review", default_desk="engineering")
    evidence = runtime.create_evidence(
        kind="web_route",
        label="AST diagnostics",
        uri="/system?tab=ast",
        summary="AST duplicate implementation diagnostics.",
    )
    work_order = runtime.create_work_order(
        session_id=session.session_id,
        title="Deduplicate strategy scoring helpers",
        summary="AST diagnostics found repeated scoring helper shape.",
        impact="Reduces duplicate implementation risk without Web runtime code edits.",
        affected_files=["research/strategy_scoring.py", "tests/test_strategy_scoring.py"],
        suggested_verification=[
            ".venv/bin/python -m pytest tests/test_strategy_scoring.py -q",
            ".venv/bin/astroq architecture ast --json",
        ],
        evidence_refs=[evidence.evidence_id],
    )

    assert work_order["work_order_id"].startswith("wo_")
    assert work_order["status"] == "open"
    assert work_order["desk"] == "engineering"
    assert work_order["affected_files"] == ["research/strategy_scoring.py", "tests/test_strategy_scoring.py"]
    assert work_order["suggested_verification"][0].endswith("tests/test_strategy_scoring.py -q")
    assert work_order["evidence_refs"] == [evidence.evidence_id]
    assert work_order["created_by"] == "engineering_desk"
    assert runtime.list_work_orders(session.session_id)["total"] == 1
    assert runtime.memory_snapshot()["summary"]["work_order_count"] == 1

    updated_work_order = runtime.update_work_order_status(
        work_order["work_order_id"],
        status="resolved",
        resolution="Deduplication was moved to a Codex implementation task.",
    )

    assert updated_work_order["status"] == "resolved"
    assert updated_work_order["resolution"] == "Deduplication was moved to a Codex implementation task."
    assert updated_work_order["resolved_at"]

    cli_code = run_cli(
        [
            "agent",
            "work-order",
            "create",
            "--session",
            session.session_id,
            "--title",
            "CLI work order",
            "--summary",
            "Create a CLI-visible engineering task.",
            "--impact",
            "Keeps repo edits outside Web runtime.",
            "--file",
            "agent_os/runtime.py",
            "--verify",
            ".venv/bin/python -m pytest tests/test_agent_os_contracts.py -q",
            "--evidence",
            evidence.evidence_id,
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    cli_work_order_id = cli_payload["data"]["work_order"]["work_order_id"]
    list_code = run_cli(["agent", "work-orders", "--session", session.session_id, "--json"])
    list_payload = json.loads(capsys.readouterr().out)
    update_cli_code = run_cli(
        [
            "agent",
            "work-order",
            "update",
            cli_work_order_id,
            "--status",
            "in_progress",
            "--resolution",
            "Accepted by Codex.",
            "--json",
        ]
    )
    update_cli_payload = json.loads(capsys.readouterr().out)

    api_res = TestClient(create_app()).post(
        "/api/agent/work-orders",
        json={
            "session_id": session.session_id,
            "title": "API work order",
            "summary": "Create an API-visible engineering task.",
            "impact": "Codex or a human handles source edits outside the Web runtime.",
            "affected_files": ["web/frontend/src/views/CEOOffice.vue"],
            "suggested_verification": ["npm run typecheck"],
            "evidence_refs": [evidence.evidence_id],
        },
    )
    api_work_order_id = api_res.json()["work_order"]["work_order_id"]
    api_update = TestClient(create_app()).patch(
        f"/api/agent/work-orders/{api_work_order_id}",
        json={"status": "canceled", "resolution": "Merged into another work order."},
    )
    api_list = TestClient(create_app()).get(f"/api/agent/work-orders?session_id={session.session_id}")

    assert cli_code == 0
    assert cli_payload["data"]["work_order"]["title"] == "CLI work order"
    assert cli_payload["data"]["work_order"]["status"] == "open"
    assert list_code == 0
    assert list_payload["data"]["total"] == 2
    assert update_cli_code == 0
    assert update_cli_payload["data"]["work_order"]["status"] == "in_progress"
    assert update_cli_payload["data"]["work_order"]["resolution"] == "Accepted by Codex."
    assert update_cli_payload["data"]["work_order"]["resolved_at"] is None
    assert api_res.status_code == 200
    assert api_res.json()["work_order"]["title"] == "API work order"
    assert api_update.status_code == 200
    assert api_update.json()["work_order"]["status"] == "canceled"
    assert api_update.json()["work_order"]["resolved_at"]
    assert api_list.status_code == 200
    assert api_list.json()["total"] == 3
    reset_datahub()


def test_engineering_code_request_creates_work_order_and_safe_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Engineering bug triage", default_desk="engineering")

    result = runtime.submit_ceo_message(
        session.session_id,
        desk="engineering",
        content=(
            "agent_os/runtime.py 这里像有个 bug，请开一个工单给 Codex，"
            "不要在 Web runtime 里直接改代码，验证 tests/test_agent_os_contracts.py"
        ),
    )
    response = result["desk_response"]
    actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]
    work_orders = runtime.list_work_orders(session.session_id)["work_orders"]

    assert len(work_orders) == 1
    work_order = work_orders[0]
    assert work_order["status"] == "open"
    assert work_order["desk"] == "engineering"
    assert "agent_os/runtime.py" in work_order["affected_files"]
    assert "tests/test_agent_os_contracts.py" in work_order["affected_files"]
    assert ".venv/bin/python -m pytest tests/test_agent_os_contracts.py -q" in work_order["suggested_verification"]
    assert work_order["evidence_refs"]
    assert set(work_order["evidence_refs"]).issubset(set(response.evidence_refs))
    assert {action["parameters"]["tool_id"] for action in actions} == {
        "astroq.architecture.ast",
        "astroq.test.design",
    }
    assert all(action["risk_level"] == "read_only" for action in actions)
    assert all(action["status"] == "proposed" for action in actions)
    assert "工单" in response.answer or "work order" in response.answer.lower()
    assert runtime.memory_snapshot()["summary"]["work_order_count"] == 1
    reset_datahub()


def test_safe_workflow_runs_engineering_work_order_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Engineering safe workflow", default_desk="engineering")
    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="engineering",
        content="请给 web/frontend/src/views/CeoOffice.vue 的 UI 问题开工单，验证 web/frontend/src/views/CeoOffice.vue",
    )

    result = runtime.run_session_read_only_actions(session.session_id, runner=fake_run)
    work_orders = runtime.list_work_orders(session.session_id)["work_orders"]

    assert result["status"] == "ready"
    assert result["run_count"] == 2
    assert result["skipped_count"] == 0
    assert {run["action_id"] for run in result["runs"]} == set(routed["desk_response"].proposed_actions)
    assert {tuple(command[1:]) for command in calls} == {
        ("architecture", "ast", "--json"),
        ("test", "design", "--json"),
    }
    assert len(work_orders) == 1
    assert work_orders[0]["status"] == "open"
    assert "web/frontend/src/views/CeoOffice.vue" in work_orders[0]["affected_files"]
    assert "cd web/frontend && npm run typecheck" in work_orders[0]["suggested_verification"]
    reset_datahub()


def test_agent_live_readiness_defaults_disabled_and_never_falls_back_to_paper(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from broker.live.qmt import MiniQmtLiveBroker

    direct = MiniQmtLiveBroker(enabled=False).health()
    runtime_health = AgentRuntime().live_readiness()

    assert direct["broker"] == "miniqmt"
    assert direct["mode"] == "live_disabled"
    assert direct["enabled"] is False
    assert direct["paper_fallback"] is False
    assert direct["kill_switch"] is True
    assert "live_disabled" in direct["blockers"]
    assert runtime_health["mode"] == "live_disabled"
    assert runtime_health["paper_fallback"] is False
    reset_datahub()


def test_agent_live_readiness_enabled_missing_sdk_blocks_without_import_crash():
    from broker.live.qmt import MiniQmtLiveBroker

    health = MiniQmtLiveBroker(enabled=True, import_checker=lambda _name: None).health()

    assert health["mode"] == "blocked"
    assert health["enabled"] is True
    assert health["sdk_available"] is False
    assert health["paper_fallback"] is False
    assert any(reason.startswith("missing_sdk") for reason in health["blockers"])


def test_agent_live_environment_validation_reports_terminal_and_account_checks():
    from broker.live.qmt import MiniQmtLiveBroker

    class ValidatingGateway:
        def validate_environment(self, *, account_id: str) -> dict[str, object]:
            return {
                "status": "validated",
                "account_id": account_id,
                "account_snapshot": {"cash": 100000.0},
                "position_count": 1,
                "open_order_count": 0,
                "trade_count": 0,
            }

    broker = MiniQmtLiveBroker(
        enabled=True,
        import_checker=lambda _name: object(),
        logged_in=True,
        account_id="1234567890",
        permissions=["query", "trade"],
        kill_switch=True,
        sdk_gateway=ValidatingGateway(),
        sdk_gateway_config={"userdata_path": "/tmp/qmt-userdata", "session_id": 42},
    )

    validation = broker.validate_environment()

    assert validation["status"] == "validated"
    assert validation["broker"] == "miniqmt"
    assert validation["paper_fallback"] is False
    assert validation["checks"]["sdk_modules"]["status"] == "passed"
    assert validation["checks"]["account"]["status"] == "passed"
    assert validation["checks"]["userdata_path"]["status"] == "passed"
    assert validation["checks"]["gateway"]["status"] == "passed"
    assert validation["checks"]["terminal_session"]["status"] == "passed"
    assert validation["account_id_masked"] == "12******90"


def test_agent_live_readiness_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    cli_code = run_cli(["agent", "live", "readiness", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).get("/api/agent/live/readiness")

    assert cli_code == 0
    assert cli_payload["data"]["health"]["mode"] == "live_disabled"
    assert cli_payload["data"]["health"]["paper_fallback"] is False
    assert api_res.status_code == 200
    assert api_res.json()["health"]["mode"] == "live_disabled"
    assert api_res.json()["health"]["paper_fallback"] is False
    reset_datahub()


def test_agent_live_environment_validation_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    cli_code = run_cli(["agent", "live", "environment", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).get("/api/agent/live/environment")

    assert cli_code == 0
    assert cli_payload["data"]["environment"]["status"] == "blocked"
    assert cli_payload["data"]["environment"]["paper_fallback"] is False
    assert "live_disabled" in cli_payload["data"]["environment"]["blockers"]
    assert api_res.status_code == 200
    assert api_res.json()["environment"]["status"] == "blocked"
    assert api_res.json()["environment"]["paper_fallback"] is False
    reset_datahub()


def test_agent_live_smoke_cli_and_api_fail_closed_without_submission(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    cli_code = run_cli(["agent", "live", "smoke", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post("/api/agent/live/smoke")

    assert cli_code == 0
    assert cli_payload["data"]["smoke"]["status"] == "blocked"
    assert cli_payload["data"]["smoke"]["health"]["mode"] == "live_disabled"
    assert cli_payload["data"]["smoke"]["submitted"] is False
    assert cli_payload["data"]["smoke"]["paper_fallback"] is False
    assert cli_payload["data"]["smoke"]["broker_reconciliation"] == {}
    assert Path(cli_payload["data"]["smoke"]["evidence"]["uri"]).exists()
    assert api_res.status_code == 200
    assert api_res.json()["smoke"]["status"] == "blocked"
    assert api_res.json()["smoke"]["submitted"] is False
    assert api_res.json()["smoke"]["paper_fallback"] is False
    reset_datahub()


def test_agent_live_smoke_ready_broker_reads_reconciliation_without_submit(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    class FakeLiveBroker:
        def __init__(self):
            self.reconcile_calls = 0
            self.submit_calls = 0
            self.reconcile_acks = []

        def health(self):
            return {
                "broker": "miniqmt",
                "mode": "live_ready",
                "enabled": True,
                "sdk_available": True,
                "logged_in": True,
                "account_id_masked": "****1234",
                "permissions": ["query", "trade"],
                "blockers": [],
                "paper_fallback": False,
            }

        def reconcile(self, ack):
            self.reconcile_calls += 1
            self.reconcile_acks.append(dict(ack))
            return {
                "status": "needs_review",
                "as_of": "2026-06-16T00:00:00Z",
                "positions_matched": False,
                "cash_matched": True,
                "open_orders": [],
                "fills": [],
                "mismatches": [{"reason": "project_ledger_comparison_not_configured"}],
                "recommended_actions": ["review_live_reconciliation_mismatches"],
                "paper_fallback": False,
            }

        def submit_order(self, *args, **kwargs):
            self.submit_calls += 1
            raise AssertionError("live smoke must not submit orders")

    broker = FakeLiveBroker()
    smoke = AgentRuntime().run_live_smoke(broker=broker)

    assert smoke["status"] == "ready"
    assert smoke["submitted"] is False
    assert smoke["paper_fallback"] is False
    assert smoke["broker_reconciliation"]["status"] == "needs_review"
    assert smoke["broker_reconciliation_status"] == "needs_review"
    assert broker.reconcile_calls == 1
    assert broker.submit_calls == 0
    assert broker.reconcile_acks == [{"smoke_test": True, "broker_order_id": ""}]
    assert Path(smoke["artifact_path"]).exists()
    assert Path(smoke["evidence"]["uri"]).exists()
    reset_datahub()


def test_agent_live_order_preview_blocks_when_readiness_not_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    preview = AgentRuntime().preview_live_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "CEO preview only",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {
                "current_symbol_notional": 0.0,
                "max_position_pct": 0.2,
                "max_total_exposure_pct": 0.7,
                "daily_order_count": 1,
                "max_daily_orders": 5,
                "tradable": True,
                "data_freshness_status": "fresh",
                "broker_account_consistent": True,
                "current_drawdown_pct": 0.04,
                "max_drawdown_pct": 0.12,
                "portfolio_var_pct": 0.025,
                "max_portfolio_var_pct": 0.06,
                "portfolio_cvar_pct": 0.04,
                "max_portfolio_cvar_pct": 0.09,
                "current_sector_notional": 8_000.0,
                "max_sector_exposure_pct": 0.25,
                "intraday_limit_state": "normal",
            },
        }
    )

    assert preview["status"] == "blocked"
    assert preview["approval_required"] is True
    assert preview["paper_fallback"] is False
    assert preview["submitted"] is False
    assert preview["risk_gate"]["passed"] is False
    assert "live_disabled" in preview["risk_gate"]["blockers"]
    reset_datahub()


def test_agent_live_order_preview_passes_with_ready_fake_broker_and_cash_gate():
    from broker.live.qmt import MiniQmtLiveBroker

    broker = MiniQmtLiveBroker(
        enabled=True,
        import_checker=lambda _name: object(),
        logged_in=True,
        permissions=["query", "trade"],
        account_id="1234567890",
        account={"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
        sdk_gateway_factory="",
    )
    preview = broker.preview_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "CEO preview only",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {
                "current_symbol_notional": 0.0,
                "max_position_pct": 0.2,
                "max_total_exposure_pct": 0.7,
                "daily_order_count": 1,
                "max_daily_orders": 5,
                "tradable": True,
                "data_freshness_status": "fresh",
                "broker_account_consistent": True,
                "current_drawdown_pct": 0.04,
                "max_drawdown_pct": 0.12,
                "portfolio_var_pct": 0.025,
                "max_portfolio_var_pct": 0.06,
                "portfolio_cvar_pct": 0.04,
                "max_portfolio_cvar_pct": 0.09,
                "current_sector_notional": 8_000.0,
                "max_sector_exposure_pct": 0.9,
                "intraday_limit_state": "normal",
            },
        }
    )
    blocked = broker.preview_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 20_000,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "Too large",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {
                "current_symbol_notional": 0.0,
                "max_position_pct": 0.9,
                "max_total_exposure_pct": 1.0,
                "daily_order_count": 1,
                "max_daily_orders": 5,
                "tradable": True,
                "data_freshness_status": "fresh",
                "broker_account_consistent": True,
                "current_drawdown_pct": 0.04,
                "max_drawdown_pct": 0.12,
                "portfolio_var_pct": 0.025,
                "max_portfolio_var_pct": 0.06,
                "portfolio_cvar_pct": 0.04,
                "max_portfolio_cvar_pct": 0.09,
                "current_sector_notional": 8_000.0,
                "max_sector_exposure_pct": 0.25,
                "intraday_limit_state": "normal",
            },
        }
    )

    assert preview["status"] == "preview_ready"
    assert preview["approval_required"] is True
    assert preview["paper_fallback"] is False
    assert preview["submitted"] is False
    assert preview["intent"]["symbol"] == "600000.SH"
    assert preview["estimated_cash_effect"] < 0
    assert preview["estimated_position_effect"]["symbol"] == "600000.SH"
    assert preview["risk_gate"]["passed"] is True
    assert preview["health"]["mode"] == "live_ready"
    assert blocked["status"] == "blocked"
    assert blocked["risk_gate"]["passed"] is False
    assert "insufficient_cash" in blocked["risk_gate"]["blockers"]


def test_agent_live_order_preview_enforces_extended_risk_snapshot():
    from broker.live.qmt import MiniQmtLiveBroker

    broker = MiniQmtLiveBroker(
        enabled=True,
        import_checker=lambda _name: object(),
        logged_in=True,
        permissions=["query", "trade"],
        account_id="1234567890",
        account={"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
        sdk_gateway_factory="",
    )
    preview = broker.preview_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "full risk snapshot",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {
                "current_symbol_notional": 2_000.0,
                "max_position_pct": 0.2,
                "max_total_exposure_pct": 0.7,
                "daily_order_count": 1,
                "max_daily_orders": 5,
                "tradable": True,
                "data_freshness_status": "fresh",
                "broker_account_consistent": True,
                "current_drawdown_pct": 0.04,
                "max_drawdown_pct": 0.12,
                "portfolio_var_pct": 0.025,
                "max_portfolio_var_pct": 0.06,
                "portfolio_cvar_pct": 0.04,
                "max_portfolio_cvar_pct": 0.09,
                "current_sector_notional": 8_000.0,
                "max_sector_exposure_pct": 0.25,
                "intraday_limit_state": "normal",
            },
        }
    )
    blocked = broker.preview_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 2_000,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "violates extended risk",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {
                "current_symbol_notional": 15_000.0,
                "max_position_pct": 0.2,
                "max_total_exposure_pct": 0.3,
                "daily_order_count": 5,
                "max_daily_orders": 5,
                "tradable": False,
                "data_freshness_status": "stale",
                "broker_account_consistent": False,
                "current_drawdown_pct": 0.04,
                "max_drawdown_pct": 0.12,
                "portfolio_var_pct": 0.025,
                "max_portfolio_var_pct": 0.06,
                "portfolio_cvar_pct": 0.04,
                "max_portfolio_cvar_pct": 0.09,
                "current_sector_notional": 8_000.0,
                "max_sector_exposure_pct": 0.25,
                "intraday_limit_state": "normal",
            },
        }
    )

    check_names = {check["name"] for check in preview["risk_gate"]["checks"]}
    assert {
        "position_concentration",
        "total_exposure",
        "daily_order_count",
        "tradability",
        "data_freshness",
        "broker_account_consistency",
    } <= check_names
    assert preview["risk_gate"]["passed"] is True
    assert blocked["risk_gate"]["passed"] is False
    assert "position_concentration_limit" in blocked["risk_gate"]["blockers"]
    assert "total_exposure_limit" in blocked["risk_gate"]["blockers"]
    assert "daily_order_limit" in blocked["risk_gate"]["blockers"]
    assert "not_tradable" in blocked["risk_gate"]["blockers"]
    assert "data_freshness_stale" in blocked["risk_gate"]["blockers"]
    assert "broker_account_inconsistent" in blocked["risk_gate"]["blockers"]


def test_agent_live_order_preview_enforces_portfolio_grade_risk_snapshot():
    from broker.live.qmt import MiniQmtLiveBroker

    broker = MiniQmtLiveBroker(
        enabled=True,
        import_checker=lambda _name: object(),
        logged_in=True,
        permissions=["query", "trade"],
        account_id="1234567890",
        account={"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
        sdk_gateway_factory="",
    )
    base_snapshot = {
        "current_symbol_notional": 2_000.0,
        "max_position_pct": 0.2,
        "max_total_exposure_pct": 0.7,
        "daily_order_count": 1,
        "max_daily_orders": 5,
        "tradable": True,
        "data_freshness_status": "fresh",
        "broker_account_consistent": True,
    }
    preview = broker.preview_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "portfolio-grade live risk snapshot",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {
                **base_snapshot,
                "current_drawdown_pct": 0.04,
                "max_drawdown_pct": 0.12,
                "portfolio_var_pct": 0.025,
                "max_portfolio_var_pct": 0.06,
                "portfolio_cvar_pct": 0.04,
                "max_portfolio_cvar_pct": 0.09,
                "current_sector_notional": 8_000.0,
                "max_sector_exposure_pct": 0.25,
                "intraday_limit_state": "normal",
            },
        }
    )
    blocked = broker.preview_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "portfolio-grade live risk breach",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {
                **base_snapshot,
                "current_drawdown_pct": 0.15,
                "max_drawdown_pct": 0.12,
                "portfolio_var_pct": 0.08,
                "max_portfolio_var_pct": 0.06,
                "portfolio_cvar_pct": 0.11,
                "max_portfolio_cvar_pct": 0.09,
                "current_sector_notional": 35_000.0,
                "max_sector_exposure_pct": 0.25,
                "intraday_limit_state": "limit_up",
            },
        }
    )
    missing = broker.preview_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "missing portfolio-grade live risk snapshot",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": base_snapshot,
        }
    )

    check_names = {check["name"] for check in preview["risk_gate"]["checks"]}
    assert {
        "drawdown_state",
        "portfolio_var",
        "portfolio_cvar",
        "sector_concentration",
        "intraday_limit_state",
    } <= check_names
    assert preview["risk_gate"]["passed"] is True
    assert blocked["risk_gate"]["passed"] is False
    assert "drawdown_limit" in blocked["risk_gate"]["blockers"]
    assert "portfolio_var_limit" in blocked["risk_gate"]["blockers"]
    assert "portfolio_cvar_limit" in blocked["risk_gate"]["blockers"]
    assert "sector_concentration_limit" in blocked["risk_gate"]["blockers"]
    assert "intraday_limit_state_blocked" in blocked["risk_gate"]["blockers"]
    assert missing["risk_gate"]["passed"] is False
    assert "missing_portfolio_risk_snapshot" in missing["risk_gate"]["blockers"]


def test_miniqmt_live_broker_uses_explicit_sdk_gateway_for_audited_submit_and_reconcile():
    from broker.live.qmt import MiniQmtLiveBroker

    class FakeSdkGateway:
        def __init__(self):
            self.submissions = []
            self.reconciliations = []

        def submit_order(self, intent, *, approval_id, account_id):
            self.submissions.append({"intent": intent, "approval_id": approval_id, "account_id": account_id})
            return {
                "broker_order_id": "QMT_0001",
                "broker_status": "accepted",
                "account_id": account_id,
                "secret_token": "should-not-leak",
            }

        def reconcile(self, ack, *, account_id):
            self.reconciliations.append({"ack": ack, "account_id": account_id})
            return {
                "positions_matched": True,
                "cash_matched": True,
                "open_orders": [
                    {
                        "broker_order_id": ack["broker_order_id"],
                        "status": "accepted",
                        "account_id": account_id,
                        "secret_token": "reconcile-secret",
                    }
                ],
                "fills": [
                    {
                        "broker_order_id": ack["broker_order_id"],
                        "quantity": ack["intent"]["quantity"],
                        "account_id": account_id,
                    }
                ],
                "mismatches": [],
            }

    gateway = FakeSdkGateway()
    broker = MiniQmtLiveBroker(
        enabled=True,
        import_checker=lambda _name: object(),
        logged_in=True,
        permissions=["query", "trade"],
        account_id="1234567890",
        account={"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
        sdk_gateway=gateway,
    )
    intent = {
        "symbol": "600000.SH",
        "side": "buy",
        "quantity": 100,
        "order_type": "limit",
        "limit_price": 10.0,
        "strategy": "manual",
        "reason": "approved gateway submit",
        "evidence_refs": ["ev_demo"],
        "risk_snapshot": {
            "current_symbol_notional": 2_000.0,
            "max_position_pct": 0.2,
            "max_total_exposure_pct": 0.7,
            "daily_order_count": 1,
            "max_daily_orders": 5,
            "tradable": True,
            "data_freshness_status": "fresh",
            "broker_account_consistent": True,
            "current_drawdown_pct": 0.04,
            "max_drawdown_pct": 0.12,
            "portfolio_var_pct": 0.025,
            "max_portfolio_var_pct": 0.06,
            "portfolio_cvar_pct": 0.04,
            "max_portfolio_cvar_pct": 0.09,
            "current_sector_notional": 8_000.0,
            "max_sector_exposure_pct": 0.25,
            "intraday_limit_state": "normal",
        },
    }

    submitted = broker.submit_order(intent, approval_id="approval_1")
    reconciled = broker.reconcile(submitted)

    assert submitted["status"] == "submitted"
    assert submitted["submitted"] is True
    assert submitted["broker_order_id"] == "QMT_0001"
    assert submitted["broker_status"] == "accepted"
    assert submitted["paper_fallback"] is False
    assert submitted["ledger_id"] == "approval_1"
    assert submitted["raw_response_hash"].startswith("sha256:")
    assert submitted["raw_response_masked"]["account_id"] == "12******90"
    assert submitted["raw_response_masked"]["secret_token"] == "***"
    assert "1234567890" not in json.dumps(submitted["raw_response_masked"])
    assert "should-not-leak" not in json.dumps(submitted["raw_response_masked"])
    assert gateway.submissions == [
        {"intent": submitted["intent"], "approval_id": "approval_1", "account_id": "1234567890"}
    ]
    assert reconciled["status"] == "matched"
    assert reconciled["positions_matched"] is True
    assert reconciled["cash_matched"] is True
    assert reconciled["paper_fallback"] is False
    assert reconciled["recommended_actions"] == []
    assert reconciled["raw_response_hash"].startswith("sha256:")
    assert "1234567890" not in json.dumps(reconciled)
    assert "reconcile-secret" not in json.dumps(reconciled)
    assert gateway.reconciliations[0]["account_id"] == "1234567890"


def test_miniqmt_live_broker_loads_sdk_gateway_from_settings_factory(tmp_path, monkeypatch):
    from core.settings import clear_settings_cache

    module_path = tmp_path / "fake_qmt_gateway_config.py"
    module_path.write_text(
        """
class ConfiguredGateway:
    def __init__(self, *, config, account_id, broker):
        self.config = dict(config)
        self.account_id = account_id
        self.broker = broker
        self.submitted = []
        self.reconciled = []

    def submit_order(self, intent, *, approval_id, account_id):
        self.submitted.append({"intent": intent, "approval_id": approval_id, "account_id": account_id})
        return {
            "broker_order_id": "CFG_QMT_0001",
            "broker_status": "accepted",
            "account_id": account_id,
            "client_name": self.config["client_name"],
        }

    def reconcile(self, ack, *, account_id):
        self.reconciled.append({"ack": ack, "account_id": account_id})
        return {
            "positions_matched": True,
            "cash_matched": True,
            "open_orders": [{"broker_order_id": ack["broker_order_id"], "status": "accepted"}],
            "fills": [],
            "mismatches": [],
        }


def build_gateway(*, config, account_id, broker):
    return ConfiguredGateway(config=config, account_id=account_id, broker=broker)
""",
        encoding="utf-8",
    )
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """
execution:
  live:
    enabled: true
    broker: miniqmt
    logged_in: true
    account_id: "1234567890"
    permissions: ["query", "trade"]
    account:
      cash: 100000
      total_asset: 120000
      market_value: 20000
    kill_switch: true
    sdk_gateway_factory: fake_qmt_gateway_config:build_gateway
    sdk_gateway_config:
      client_name: ci-qmt
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASTROLABE_SETTINGS", str(settings_path))
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("fake_qmt_gateway_config", None)
    clear_settings_cache()

    from broker.live.qmt import MiniQmtLiveBroker

    broker = MiniQmtLiveBroker(import_checker=lambda _name: object())
    intent = {
        "symbol": "600000.SH",
        "side": "buy",
        "quantity": 100,
        "order_type": "limit",
        "limit_price": 10.0,
        "strategy": "manual",
        "reason": "configured gateway submit",
        "evidence_refs": ["ev_demo"],
        "risk_snapshot": {
            "current_symbol_notional": 2_000.0,
            "max_position_pct": 0.2,
            "max_total_exposure_pct": 0.7,
            "daily_order_count": 1,
            "max_daily_orders": 5,
            "tradable": True,
            "data_freshness_status": "fresh",
            "broker_account_consistent": True,
            "current_drawdown_pct": 0.04,
            "max_drawdown_pct": 0.12,
            "portfolio_var_pct": 0.025,
            "max_portfolio_var_pct": 0.06,
            "portfolio_cvar_pct": 0.04,
            "max_portfolio_cvar_pct": 0.09,
            "current_sector_notional": 8_000.0,
            "max_sector_exposure_pct": 0.25,
            "intraday_limit_state": "normal",
        },
    }

    health = broker.health()
    submitted = broker.submit_order(intent, approval_id="approval_config")
    reconciled = broker.reconcile(submitted)

    assert health["mode"] == "live_ready"
    assert health["sdk_gateway_configured"] is True
    assert health["sdk_gateway_error"] == ""
    assert broker.sdk_gateway.config == {"client_name": "ci-qmt"}
    assert submitted["status"] == "submitted"
    assert submitted["broker_order_id"] == "CFG_QMT_0001"
    assert submitted["raw_response_masked"]["account_id"] == "12******90"
    assert submitted["raw_response_masked"]["client_name"] == "ci-qmt"
    assert broker.sdk_gateway.submitted[0]["approval_id"] == "approval_config"
    assert reconciled["status"] == "matched"
    assert broker.sdk_gateway.reconciled[0]["account_id"] == "1234567890"
    clear_settings_cache()


def test_miniqmt_live_broker_blocks_when_configured_sdk_gateway_factory_fails(tmp_path, monkeypatch):
    from core.settings import clear_settings_cache

    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """
execution:
  live:
    enabled: true
    broker: miniqmt
    logged_in: true
    account_id: "1234567890"
    permissions: ["query", "trade"]
    account:
      cash: 100000
      total_asset: 120000
      market_value: 20000
    kill_switch: true
    sdk_gateway_factory: missing_qmt_gateway:build_gateway
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASTROLABE_SETTINGS", str(settings_path))
    clear_settings_cache()

    from broker.live.qmt import MiniQmtLiveBroker

    broker = MiniQmtLiveBroker(import_checker=lambda _name: object())
    health = broker.health()
    submitted = broker.submit_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "factory failure blocks",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {},
        },
        approval_id="approval_config_failure",
    )

    assert health["mode"] == "blocked"
    assert "sdk_gateway_load_failed" in health["blockers"]
    assert health["sdk_gateway_configured"] is False
    assert health["sdk_gateway_error"].startswith("ModuleNotFoundError:")
    assert submitted["status"] == "blocked"
    assert submitted["error"] == "live_sdk_gateway_unavailable"
    assert submitted["broker_status"] == "gateway_unavailable"
    assert submitted["paper_fallback"] is False
    clear_settings_cache()


def test_miniqmt_live_broker_default_xtquant_factory_requires_user_data_path(tmp_path, monkeypatch):
    from core.settings import clear_settings_cache

    xtquant = types.ModuleType("xtquant")
    xttrader = types.ModuleType("xtquant.xttrader")
    xttype = types.ModuleType("xtquant.xttype")
    xtconstant = types.ModuleType("xtquant.xtconstant")
    xttrader.XtQuantTrader = object
    xttype.StockAccount = object
    xtconstant.FIX_PRICE = 11
    xtquant.xttrader = xttrader
    xtquant.xttype = xttype
    xtquant.xtconstant = xtconstant
    monkeypatch.setitem(sys.modules, "xtquant", xtquant)
    monkeypatch.setitem(sys.modules, "xtquant.xttrader", xttrader)
    monkeypatch.setitem(sys.modules, "xtquant.xttype", xttype)
    monkeypatch.setitem(sys.modules, "xtquant.xtconstant", xtconstant)

    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """
execution:
  live:
    enabled: true
    broker: miniqmt
    logged_in: true
    account_id: "1234567890"
    permissions: ["query", "trade"]
    account:
      cash: 100000
      total_asset: 120000
      market_value: 20000
    kill_switch: true
    sdk_modules: []
    sdk_gateway_factory: broker.live.xtquant_gateway:build_gateway
    sdk_gateway_config:
      userdata_path: ''
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASTROLABE_SETTINGS", str(settings_path))
    clear_settings_cache()

    from broker.live.qmt import MiniQmtLiveBroker

    health = MiniQmtLiveBroker(import_checker=lambda _name: object()).health()

    assert health["mode"] == "blocked"
    assert "sdk_gateway_load_failed" in health["blockers"]
    assert health["sdk_gateway_configured"] is False
    assert "userdata_path" in health["sdk_gateway_error"]
    clear_settings_cache()


def test_agent_live_preview_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    cli_code = run_cli(
        [
            "agent",
            "live",
            "preview",
            "--symbol",
            "600000.SH",
            "--side",
            "buy",
            "--quantity",
            "100",
            "--limit-price",
            "10",
            "--strategy",
            "manual",
            "--reason",
            "preview",
            "--evidence",
            "ev_demo",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(
        "/api/agent/live/preview",
        json={
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "preview",
            "evidence_refs": ["ev_demo"],
        },
    )

    assert cli_code == 0
    assert cli_payload["data"]["preview"]["status"] == "blocked"
    assert cli_payload["data"]["preview"]["paper_fallback"] is False
    assert api_res.status_code == 200
    assert api_res.json()["preview"]["status"] == "blocked"
    assert api_res.json()["preview"]["submitted"] is False
    reset_datahub()


def test_agent_live_order_submission_requires_approval_reruns_preview_and_reconciles(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    class FakeLiveBroker:
        def __init__(self):
            self.preview_calls = 0
            self.submit_calls = 0
            self.reconcile_calls = 0
            self.reconcile_acks = []

        def preview_order(self, intent):
            self.preview_calls += 1
            normalized = {
                "symbol": str(intent["symbol"]).upper(),
                "side": intent["side"],
                "quantity": int(intent["quantity"]),
                "order_type": "limit",
                "limit_price": float(intent["limit_price"]),
                "strategy": intent.get("strategy", "manual"),
                "reason": intent.get("reason", ""),
                "evidence_refs": list(intent.get("evidence_refs", [])),
                "risk_snapshot": dict(intent.get("risk_snapshot", {})),
            }
            return {
                "status": "preview_ready",
                "broker": "miniqmt",
                "intent": normalized,
                "approval_required": True,
                "paper_fallback": False,
                "submitted": False,
                "risk_gate": {"passed": True, "blockers": [], "checks": [{"name": "fake_live_ready", "passed": True}]},
                "health": {"mode": "live_ready", "paper_fallback": False},
                "account_snapshot": {"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
                "estimated_cash_effect": -1005.0,
                "estimated_position_effect": {"symbol": normalized["symbol"], "quantity_delta": 100.0},
            }

        def submit_order(self, intent, approval_id):
            self.submit_calls += 1
            return {
                "status": "submitted",
                "broker_order_id": "LIVE_0001",
                "submitted_at": "2026-06-15T00:00:00Z",
                "broker_status": "accepted",
                "raw_response_hash": "sha256:demo",
                "ledger_id": approval_id,
                "submitted": True,
            }

        def reconcile(self, ack):
            self.reconcile_calls += 1
            self.reconcile_acks.append(dict(ack))
            return {
                "status": "matched",
                "as_of": "2026-06-15T00:00:01Z",
                "positions_matched": True,
                "cash_matched": True,
                "open_orders": [{"broker_order_id": ack["broker_order_id"], "status": "accepted"}],
                "fills": [],
                "mismatches": [],
                "recommended_actions": [],
            }

    broker = FakeLiveBroker()
    runtime = AgentRuntime()
    session = runtime.create_session(title="Live submit control", default_desk="execution")
    intent = {
        "symbol": "600000.SH",
        "side": "buy",
        "quantity": 100,
        "order_type": "limit",
        "limit_price": 10.0,
        "strategy": "manual",
        "reason": "approved live submit",
        "evidence_refs": ["ev_demo"],
        "risk_snapshot": {
            "current_symbol_notional": 0.0,
            "current_symbol_quantity": 50.0,
            "max_position_pct": 0.2,
            "max_total_exposure_pct": 0.7,
            "daily_order_count": 1,
            "max_daily_orders": 5,
            "tradable": True,
            "data_freshness_status": "fresh",
            "broker_account_consistent": True,
        },
    }
    proposal = runtime.propose_live_order(session_id=session.session_id, intent=intent, broker=broker)

    assert proposal["status"] == "approval_required"
    assert proposal["preview"]["paper_fallback"] is False
    assert proposal["action"]["action_type"] == "live_order"
    assert proposal["action"]["risk_level"] == "live_order"
    assert proposal["action"]["status"] == "approval_required"
    assert Path(proposal["evidence"]["uri"]).exists()

    blocked_submission = runtime.submit_live_order_action(proposal["action"]["action_id"], broker=broker)
    assert blocked_submission["status"] == "blocked"
    assert "approval required" in blocked_submission["run"]["stderr_summary"]
    assert broker.submit_calls == 0

    runtime.approve_action(proposal["action"]["action_id"], decided_by="ceo")
    submitted = runtime.submit_live_order_action(proposal["action"]["action_id"], broker=broker)

    assert broker.preview_calls == 2
    assert broker.submit_calls == 1
    assert broker.reconcile_calls == 1
    project_snapshot = broker.reconcile_acks[0]["project_snapshot"]
    assert project_snapshot["cash"] == 98_995.0
    assert project_snapshot["positions"] == [{"symbol": "600000.SH", "quantity": 150.0}]
    assert project_snapshot["orders"][0]["broker_order_id"] == "LIVE_0001"
    assert project_snapshot["missing"] == []
    assert submitted["status"] == "succeeded"
    assert submitted["ack"]["broker_order_id"] == "LIVE_0001"
    assert submitted["ack"]["project_snapshot"] == project_snapshot
    assert submitted["run"]["tool_name"] == "live.live_order.submit"
    assert submitted["run"]["artifact_refs"]
    assert submitted["reconciliation"]["status"] == "submitted"
    assert submitted["reconciliation"]["broker_reconciliation"]["status"] == "matched"
    assert submitted["reconciliation"]["paper_fallback"] is False
    assert submitted["evidence"]["label"] == "Live order reconciliation"
    assert Path(submitted["evidence"]["uri"]).exists()
    assert runtime.get_action(proposal["action"]["action_id"])["status"] == "succeeded"
    reset_datahub()


def test_agent_live_kill_switch_cancels_queue_and_blocks_live_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    class FakeLiveBroker:
        def __init__(self):
            self.preview_calls = 0
            self.submit_calls = 0
            self.reconcile_calls = 0

        def preview_order(self, intent):
            self.preview_calls += 1
            normalized = {
                "symbol": str(intent["symbol"]).upper(),
                "side": intent["side"],
                "quantity": int(intent["quantity"]),
                "order_type": "limit",
                "limit_price": float(intent["limit_price"]),
                "strategy": intent.get("strategy", "manual"),
                "reason": intent.get("reason", ""),
                "evidence_refs": list(intent.get("evidence_refs", [])),
                "risk_snapshot": dict(intent.get("risk_snapshot", {})),
            }
            return {
                "status": "preview_ready",
                "broker": "miniqmt",
                "intent": normalized,
                "approval_required": True,
                "paper_fallback": False,
                "submitted": False,
                "risk_gate": {"passed": True, "blockers": [], "checks": [{"name": "fake_live_ready", "passed": True}]},
                "health": {"mode": "live_ready", "paper_fallback": False},
                "account_snapshot": {"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
            }

        def submit_order(self, intent, approval_id):
            self.submit_calls += 1
            return {
                "status": "submitted",
                "broker_order_id": "LIVE_0002",
                "broker_status": "accepted",
                "submitted": True,
                "ledger_id": approval_id,
            }

        def reconcile(self, ack):
            self.reconcile_calls += 1
            return {"status": "matched", "mismatches": [], "open_orders": []}

    broker = FakeLiveBroker()
    runtime = AgentRuntime()
    session = runtime.create_session(title="Live kill switch", default_desk="execution")
    intent = {
        "symbol": "600000.SH",
        "side": "buy",
        "quantity": 100,
        "order_type": "limit",
        "limit_price": 10.0,
        "strategy": "manual",
        "reason": "kill switch coverage",
        "evidence_refs": ["ev_demo"],
        "risk_snapshot": {"tradable": True, "data_freshness_status": "fresh", "broker_account_consistent": True},
    }
    proposal = runtime.propose_live_order(session_id=session.session_id, intent=intent, broker=broker)

    activated = runtime.activate_live_kill_switch(reason="CEO emergency stop")

    assert proposal["status"] == "approval_required"
    assert broker.preview_calls == 1
    assert activated["status"] == "active"
    assert activated["active"] is True
    assert activated["reason"] == "CEO emergency stop"
    assert activated["canceled_count"] == 1
    assert activated["canceled_actions"][0]["action_id"] == proposal["action"]["action_id"]
    assert runtime.get_action(proposal["action"]["action_id"])["status"] == "canceled"
    assert Path(activated["artifact_path"]).exists()
    assert activated["evidence"]["label"] == "Live kill switch"

    blocked_proposal = runtime.propose_live_order(session_id=session.session_id, intent=intent, broker=broker)

    assert blocked_proposal["status"] == "blocked"
    assert blocked_proposal["action"] is None
    assert blocked_proposal["preview"]["status"] == "blocked"
    assert "live_kill_switch_active" in blocked_proposal["preview"]["risk_gate"]["blockers"]
    assert broker.preview_calls == 1

    manual_action = runtime.propose_action(
        session_id=session.session_id,
        desk="execution",
        action_type="live_order",
        risk_level="live_order",
        summary="Approved action should still be blocked by kill switch",
        parameters={"live_order_intent": intent, "live_order_preview": proposal["preview"]},
        expected_effect="Would submit only if kill switch is inactive.",
        evidence_refs=[],
    )
    runtime.approve_action(manual_action.action_id, decided_by="ceo")
    blocked_submit = runtime.submit_live_order_action(manual_action.action_id, broker=broker)

    assert blocked_submit["status"] == "blocked"
    assert "live_kill_switch_active" in blocked_submit["run"]["stderr_summary"]
    assert "live_kill_switch_active" in blocked_submit["preview"]["risk_gate"]["blockers"]
    assert runtime.get_action(manual_action.action_id)["status"] == "blocked"
    assert broker.preview_calls == 1
    assert broker.submit_calls == 0
    assert broker.reconcile_calls == 0

    status = runtime.live_kill_switch_status()
    assert status["active"] is True
    assert status["reason"] == "CEO emergency stop"

    deactivated = runtime.deactivate_live_kill_switch(reason="Incident resolved")
    assert deactivated["status"] == "inactive"
    assert runtime.live_kill_switch_status()["active"] is False
    reset_datahub()


def test_agent_live_kill_switch_requests_broker_cancel_for_submitted_live_orders(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    class FakeLiveBroker:
        def __init__(self):
            self.cancel_calls = []
            self.reconcile_calls = 0

        def preview_order(self, intent):
            normalized = {
                "symbol": str(intent["symbol"]).upper(),
                "side": intent["side"],
                "quantity": int(intent["quantity"]),
                "order_type": "limit",
                "limit_price": float(intent["limit_price"]),
                "strategy": intent.get("strategy", "manual"),
                "reason": intent.get("reason", ""),
                "evidence_refs": list(intent.get("evidence_refs", [])),
                "risk_snapshot": dict(intent.get("risk_snapshot", {})),
            }
            return {
                "status": "preview_ready",
                "broker": "miniqmt",
                "intent": normalized,
                "approval_required": True,
                "paper_fallback": False,
                "submitted": False,
                "risk_gate": {"passed": True, "blockers": [], "checks": []},
                "health": {"mode": "live_ready", "paper_fallback": False},
                "account_snapshot": {"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
            }

        def submit_order(self, intent, approval_id):
            return {
                "status": "submitted",
                "broker_order_id": "LIVE_CANCEL_0001",
                "broker_status": "accepted",
                "submitted": True,
                "ledger_id": approval_id,
                "intent": dict(intent),
            }

        def reconcile(self, ack):
            self.reconcile_calls += 1
            return {"status": "matched", "mismatches": [], "open_orders": [{"broker_order_id": ack["broker_order_id"]}]}

        def cancel_order(self, ack, *, reason):
            self.cancel_calls.append({"ack": dict(ack), "reason": reason})
            return {
                "status": "canceled",
                "broker_order_id": ack["broker_order_id"],
                "broker_status": "cancel_requested",
                "paper_fallback": False,
            }

    broker = FakeLiveBroker()
    runtime = AgentRuntime()
    session = runtime.create_session(title="Broker kill switch", default_desk="execution")
    intent = {
        "symbol": "600000.SH",
        "side": "buy",
        "quantity": 100,
        "order_type": "limit",
        "limit_price": 10.0,
        "strategy": "manual",
        "reason": "submitted order must be canceled at broker",
        "evidence_refs": ["ev_demo"],
        "risk_snapshot": {"tradable": True, "data_freshness_status": "fresh", "broker_account_consistent": True},
    }
    proposal = runtime.propose_live_order(session_id=session.session_id, intent=intent, broker=broker)
    runtime.approve_action(proposal["action"]["action_id"], decided_by="ceo")
    submitted = runtime.submit_live_order_action(proposal["action"]["action_id"], broker=broker)

    activated = runtime.activate_live_kill_switch(reason="CEO emergency stop", broker=broker)

    assert submitted["status"] == "succeeded"
    assert runtime.get_action(proposal["action"]["action_id"])["status"] == "succeeded"
    assert broker.cancel_calls == [
        {
            "ack": submitted["ack"],
            "reason": "CEO emergency stop",
        }
    ]
    assert activated["status"] == "active"
    assert activated["canceled_count"] == 0
    assert activated["broker_canceled_count"] == 1
    assert activated["broker_cancel_failed_count"] == 0
    assert activated["broker_cancellations"][0]["action_id"] == proposal["action"]["action_id"]
    assert activated["broker_cancellations"][0]["order_id"] == "LIVE_CANCEL_0001"
    assert activated["broker_cancellations"][0]["status"] == "canceled"
    assert activated["broker_cancellations"][0]["paper_fallback"] is False
    artifact = json.loads(Path(activated["artifact_path"]).read_text(encoding="utf-8"))
    assert artifact["broker_canceled_count"] == 1
    assert artifact["broker_cancellations"][0]["order_id"] == "LIVE_CANCEL_0001"
    assert activated["evidence"]["label"] == "Live kill switch"
    reset_datahub()


def test_agent_live_kill_switch_records_unsupported_broker_cancel_without_fake_success(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    class FakeLiveBroker:
        def preview_order(self, intent):
            return {
                "status": "preview_ready",
                "broker": "miniqmt",
                "intent": {
                    "symbol": str(intent["symbol"]).upper(),
                    "side": intent["side"],
                    "quantity": int(intent["quantity"]),
                    "order_type": "limit",
                    "limit_price": float(intent["limit_price"]),
                    "strategy": "manual",
                    "reason": "unsupported cancel",
                    "evidence_refs": ["ev_demo"],
                    "risk_snapshot": {"tradable": True, "data_freshness_status": "fresh", "broker_account_consistent": True},
                },
                "approval_required": True,
                "paper_fallback": False,
                "submitted": False,
                "risk_gate": {"passed": True, "blockers": [], "checks": []},
                "health": {"mode": "live_ready", "paper_fallback": False},
                "account_snapshot": {"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
            }

        def submit_order(self, intent, approval_id):
            return {
                "status": "submitted",
                "broker_order_id": "LIVE_UNSUPPORTED_0001",
                "broker_status": "accepted",
                "submitted": True,
                "ledger_id": approval_id,
            }

        def reconcile(self, ack):
            return {"status": "matched", "mismatches": [], "open_orders": [{"broker_order_id": ack["broker_order_id"]}]}

    broker = FakeLiveBroker()
    runtime = AgentRuntime()
    session = runtime.create_session(title="Unsupported broker cancel", default_desk="execution")
    proposal = runtime.propose_live_order(
        session_id=session.session_id,
        intent={
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "unsupported cancel",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {"tradable": True, "data_freshness_status": "fresh", "broker_account_consistent": True},
        },
        broker=broker,
    )
    runtime.approve_action(proposal["action"]["action_id"], decided_by="ceo")
    runtime.submit_live_order_action(proposal["action"]["action_id"], broker=broker)

    activated = runtime.activate_live_kill_switch(reason="CEO emergency stop", broker=broker)

    assert activated["broker_canceled_count"] == 0
    assert activated["broker_cancel_failed_count"] == 1
    assert activated["broker_cancellations"][0]["status"] == "blocked"
    assert activated["broker_cancellations"][0]["reason"] == "broker_cancel_not_supported"
    assert activated["broker_cancellations"][0]["order_id"] == "LIVE_UNSUPPORTED_0001"
    assert activated["broker_cancellations"][0]["paper_fallback"] is False
    reset_datahub()


def test_agent_live_kill_switch_invalid_state_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    state_path = Path(runtime.live_kill_switch_status()["state_path"])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{broken-json", encoding="utf-8")

    status = runtime.live_kill_switch_status()
    preview = runtime.preview_live_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "invalid kill switch state must not fail open",
            "evidence_refs": ["ev_demo"],
        }
    )

    assert status["status"] == "invalid"
    assert status["active"] is True
    assert status["read_error"] == "invalid_live_kill_switch_state"
    assert preview["status"] == "blocked"
    assert "live_kill_switch_active" in preview["risk_gate"]["blockers"]
    reset_datahub()


def test_agent_live_order_proposal_and_submit_cli_api_fail_closed_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Live CLI/API", default_desk="execution")
    cli_propose_code = run_cli(
        [
            "agent",
            "live",
            "propose",
            "--session",
            session.session_id,
            "--symbol",
            "600000.SH",
            "--side",
            "buy",
            "--quantity",
            "100",
            "--limit-price",
            "10",
            "--strategy",
            "manual",
            "--reason",
            "default disabled",
            "--evidence",
            "ev_demo",
            "--json",
        ]
    )
    cli_proposal = json.loads(capsys.readouterr().out)
    api_proposal_res = TestClient(create_app()).post(
        "/api/agent/live/proposals",
        json={
            "session_id": session.session_id,
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "default disabled",
            "evidence_refs": ["ev_demo"],
        },
    )
    cli_action = runtime.propose_action(
        session_id=session.session_id,
        desk="execution",
        action_type="live_order",
        risk_level="live_order",
        summary="CLI live submit should fail closed",
        parameters={
            "live_order_intent": {
                "symbol": "600000.SH",
                "side": "buy",
                "quantity": 100,
                "order_type": "limit",
                "limit_price": 10.0,
                "strategy": "manual",
                "reason": "default disabled",
                "evidence_refs": ["ev_demo"],
            }
        },
        expected_effect="Would submit only through MiniQMT/QMT if readiness and risk gates pass.",
        evidence_refs=["ev_demo"],
    )
    api_action = runtime.propose_action(
        session_id=session.session_id,
        desk="execution",
        action_type="live_order",
        risk_level="live_order",
        summary="API live submit should fail closed",
        parameters={
            "live_order_intent": {
                "symbol": "600001.SH",
                "side": "buy",
                "quantity": 100,
                "order_type": "limit",
                "limit_price": 10.0,
                "strategy": "manual",
                "reason": "default disabled",
                "evidence_refs": ["ev_demo"],
            }
        },
        expected_effect="Would submit only through MiniQMT/QMT if readiness and risk gates pass.",
        evidence_refs=["ev_demo"],
    )
    runtime.approve_action(cli_action.action_id, decided_by="ceo")
    runtime.approve_action(api_action.action_id, decided_by="ceo")

    cli_submit_code = run_cli(["agent", "live", "submit", cli_action.action_id, "--json"])
    cli_submit = json.loads(capsys.readouterr().out)
    api_submit_res = TestClient(create_app()).post(f"/api/agent/live/actions/{api_action.action_id}/submit")

    assert cli_propose_code == 0
    assert cli_proposal["data"]["proposal"]["status"] == "blocked"
    assert cli_proposal["data"]["proposal"]["action"] is None
    assert cli_proposal["data"]["proposal"]["preview"]["paper_fallback"] is False
    assert api_proposal_res.status_code == 200
    assert api_proposal_res.json()["proposal"]["status"] == "blocked"
    assert api_proposal_res.json()["proposal"]["preview"]["risk_gate"]["passed"] is False
    assert cli_submit_code == 1
    assert cli_submit["data"]["submission"]["status"] == "blocked"
    assert cli_submit["data"]["submission"]["run"]["tool_name"] == "live.live_order.submit"
    assert cli_submit["data"]["submission"]["reconciliation"]["paper_fallback"] is False
    assert api_submit_res.status_code == 200
    assert api_submit_res.json()["submission"]["status"] == "blocked"
    assert api_submit_res.json()["submission"]["reconciliation"]["paper_fallback"] is False
    reset_datahub()


def test_agent_live_kill_switch_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    cli_status_code = run_cli(["agent", "live", "kill-switch", "status", "--json"])
    cli_status = json.loads(capsys.readouterr().out)
    cli_activate_code = run_cli(
        ["agent", "live", "kill-switch", "activate", "--reason", "manual test stop", "--json"]
    )
    cli_activated = json.loads(capsys.readouterr().out)
    api_status_res = TestClient(create_app()).get("/api/agent/live/kill-switch")
    api_deactivate_res = TestClient(create_app()).post(
        "/api/agent/live/kill-switch/deactivate",
        json={"reason": "manual test resolved"},
    )

    assert cli_status_code == 0
    assert cli_status["data"]["kill_switch"]["active"] is False
    assert cli_activate_code == 0
    assert cli_activated["data"]["kill_switch"]["active"] is True
    assert cli_activated["data"]["kill_switch"]["reason"] == "manual test stop"
    assert api_status_res.status_code == 200
    assert api_status_res.json()["kill_switch"]["active"] is True
    assert api_deactivate_res.status_code == 200
    assert api_deactivate_res.json()["kill_switch"]["active"] is False
    assert api_deactivate_res.json()["kill_switch"]["reason"] == "manual test resolved"
    reset_datahub()


def test_agent_live_reconciliation_runner_scans_submitted_live_orders(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    class FakeLiveBroker:
        def __init__(self):
            self.preview_calls = 0
            self.submit_calls = 0
            self.reconcile_calls = 0
            self.reconcile_acks = []

        def preview_order(self, intent):
            self.preview_calls += 1
            normalized = {
                "symbol": str(intent["symbol"]).upper(),
                "side": intent["side"],
                "quantity": int(intent["quantity"]),
                "order_type": "limit",
                "limit_price": float(intent["limit_price"]),
                "strategy": intent.get("strategy", "manual"),
                "reason": intent.get("reason", ""),
                "evidence_refs": list(intent.get("evidence_refs", [])),
                "risk_snapshot": dict(intent.get("risk_snapshot", {})),
            }
            return {
                "status": "preview_ready",
                "broker": "miniqmt",
                "intent": normalized,
                "approval_required": True,
                "paper_fallback": False,
                "submitted": False,
                "risk_gate": {"passed": True, "blockers": [], "checks": [{"name": "fake_live_ready", "passed": True}]},
                "health": {"mode": "live_ready", "paper_fallback": False},
                "account_snapshot": {"cash": 50_000.0, "total_asset": 55_000.0, "market_value": 5_000.0},
                "estimated_cash_effect": -1002.0,
                "estimated_position_effect": {"symbol": normalized["symbol"], "quantity_delta": 100.0},
            }

        def submit_order(self, intent, approval_id):
            self.submit_calls += 1
            return {
                "status": "submitted",
                "broker_order_id": "LIVE_RECON_0001",
                "broker_status": "accepted",
                "submitted": True,
                "ledger_id": approval_id,
            }

        def reconcile(self, ack):
            self.reconcile_calls += 1
            self.reconcile_acks.append(dict(ack))
            return {
                "status": "matched",
                "as_of": "2026-06-15T00:00:02Z",
                "open_orders": [{"broker_order_id": ack["broker_order_id"], "status": "accepted"}],
                "fills": [],
                "mismatches": [],
                "recommended_actions": [],
            }

    broker = FakeLiveBroker()
    runtime = AgentRuntime()
    session = runtime.create_session(title="Live reconciliation", default_desk="execution")
    intent = {
        "symbol": "600000.SH",
        "side": "buy",
        "quantity": 100,
        "order_type": "limit",
        "limit_price": 10.0,
        "strategy": "manual",
        "reason": "reconciliation coverage",
        "evidence_refs": ["ev_demo"],
        "risk_snapshot": {"current_symbol_quantity": 10.0},
    }
    proposal = runtime.propose_live_order(session_id=session.session_id, intent=intent, broker=broker)
    runtime.approve_action(proposal["action"]["action_id"], decided_by="ceo")
    submitted = runtime.submit_live_order_action(proposal["action"]["action_id"], broker=broker)
    pending = runtime.propose_action(
        session_id=session.session_id,
        desk="execution",
        action_type="live_order",
        risk_level="live_order",
        summary="Unsubmitted live order should be skipped",
        parameters={"live_order_intent": intent},
        expected_effect="Would submit only after approval.",
    )

    reconciliation = runtime.run_live_reconciliation(session_id=session.session_id, broker=broker)

    assert submitted["status"] == "succeeded"
    assert broker.reconcile_calls == 2
    assert broker.reconcile_acks[0]["project_snapshot"] == broker.reconcile_acks[1]["project_snapshot"]
    assert broker.reconcile_acks[1]["project_snapshot"]["cash"] == 48_998.0
    assert broker.reconcile_acks[1]["project_snapshot"]["positions"] == [{"symbol": "600000.SH", "quantity": 110.0}]
    assert reconciliation["status"] == "ready"
    assert reconciliation["action_count"] == 2
    assert reconciliation["reconciled_count"] == 1
    assert reconciliation["skipped_count"] == 1
    items_by_action = {item["action_id"]: item for item in reconciliation["items"]}
    assert items_by_action[proposal["action"]["action_id"]]["broker_reconciliation"]["status"] == "matched"
    assert items_by_action[pending.action_id]["status"] == "skipped"
    assert items_by_action[pending.action_id]["reason"] == "no_submitted_live_order"
    assert reconciliation["evidence"]["label"] == "Live scheduled reconciliation"
    assert Path(reconciliation["path"]).exists()
    reset_datahub()


def test_agent_live_monitor_tick_writes_readiness_and_reconciliation_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    class FakeLiveBroker:
        def __init__(self):
            self.reconcile_acks = []

        def health(self):
            return {
                "broker": "miniqmt",
                "mode": "live_ready",
                "enabled": True,
                "sdk_available": True,
                "logged_in": True,
                "account_id_masked": "****1234",
                "permissions": ["query", "trade"],
                "blockers": [],
                "paper_fallback": False,
            }

        def preview_order(self, intent):
            normalized = {
                "symbol": str(intent["symbol"]).upper(),
                "side": intent["side"],
                "quantity": int(intent["quantity"]),
                "order_type": "limit",
                "limit_price": float(intent["limit_price"]),
                "strategy": intent.get("strategy", "manual"),
                "reason": intent.get("reason", ""),
                "evidence_refs": list(intent.get("evidence_refs", [])),
                "risk_snapshot": dict(intent.get("risk_snapshot", {})),
            }
            return {
                "status": "preview_ready",
                "broker": "miniqmt",
                "intent": normalized,
                "approval_required": True,
                "paper_fallback": False,
                "submitted": False,
                "risk_gate": {"passed": True, "blockers": [], "checks": []},
                "health": {"mode": "live_ready", "paper_fallback": False},
                "account_snapshot": {"cash": 100_000.0, "total_asset": 120_000.0, "market_value": 20_000.0},
            }

        def submit_order(self, intent, approval_id):
            return {
                "status": "submitted",
                "broker_order_id": "LIVE_MONITOR_0001",
                "broker_status": "accepted",
                "submitted": True,
                "ledger_id": approval_id,
            }

        def reconcile(self, ack):
            self.reconcile_acks.append(dict(ack))
            return {
                "status": "matched",
                "positions_matched": True,
                "cash_matched": True,
                "open_orders": [{"broker_order_id": ack["broker_order_id"], "status": "accepted"}],
                "fills": [],
                "mismatches": [],
                "recommended_actions": [],
                "paper_fallback": False,
            }

    broker = FakeLiveBroker()
    runtime = AgentRuntime()
    session = runtime.create_session(title="Live monitor", default_desk="execution")
    proposal = runtime.propose_live_order(
        session_id=session.session_id,
        intent={
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "monitor reconciliation",
            "evidence_refs": ["ev_demo"],
            "risk_snapshot": {"tradable": True, "data_freshness_status": "fresh", "broker_account_consistent": True},
        },
        broker=broker,
    )
    runtime.approve_action(proposal["action"]["action_id"], decided_by="ceo")
    runtime.submit_live_order_action(proposal["action"]["action_id"], broker=broker)

    monitor = runtime.run_live_monitor(session_id=session.session_id, broker=broker)

    assert monitor["status"] == "ready"
    assert monitor["readiness"]["mode"] == "live_ready"
    assert monitor["kill_switch"]["active"] is False
    assert monitor["reconciliation"]["reconciled_count"] == 1
    assert monitor["reconciliation"]["items"][0]["order_id"] == "LIVE_MONITOR_0001"
    assert monitor["paper_fallback"] is False
    assert broker.reconcile_acks[-1]["broker_order_id"] == "LIVE_MONITOR_0001"
    assert Path(monitor["path"]).exists()
    assert monitor["evidence"]["label"] == "Live monitor tick"
    artifact = json.loads(Path(monitor["path"]).read_text(encoding="utf-8"))
    assert artifact["reconciliation"]["path"] == monitor["reconciliation"]["path"]
    assert artifact["readiness"]["mode"] == "live_ready"
    reset_datahub()


def test_agent_live_reconciliation_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    cli_code = run_cli(["agent", "live", "reconcile", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post("/api/agent/live/reconciliation")

    assert cli_code == 0
    assert cli_payload["data"]["reconciliation"]["status"] == "ready"
    assert cli_payload["data"]["reconciliation"]["action_count"] == 0
    assert api_res.status_code == 200
    assert api_res.json()["reconciliation"]["status"] == "ready"
    assert api_res.json()["reconciliation"]["action_count"] == 0
    reset_datahub()


def test_agent_live_monitor_cli_and_api_are_cron_callable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    cli_code = run_cli(["agent", "live", "monitor", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post("/api/agent/live/monitor")

    assert cli_code == 0
    assert cli_payload["data"]["monitor"]["status"] == "blocked"
    assert cli_payload["data"]["monitor"]["readiness"]["mode"] == "live_disabled"
    assert cli_payload["data"]["monitor"]["reconciliation"]["action_count"] == 0
    assert cli_payload["data"]["monitor"]["paper_fallback"] is False
    assert Path(cli_payload["data"]["monitor"]["path"]).exists()
    assert api_res.status_code == 200
    assert api_res.json()["monitor"]["status"] == "blocked"
    assert api_res.json()["monitor"]["readiness"]["mode"] == "live_disabled"
    assert api_res.json()["monitor"]["paper_fallback"] is False
    reset_datahub()


def test_paper_order_preview_does_not_submit_or_mutate_broker_state():
    from broker import PaperBroker

    broker = PaperBroker(initial_cash=50_000.0, enable_risk=True)
    broker.set_prices({"000001": 10.0})

    preview = broker.preview_order(
        {
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "preview only",
            "evidence_refs": ["ev_demo"],
        }
    )
    blocked = broker.preview_order(
        {
            "symbol": "000001",
            "side": "buy",
            "quantity": 10_000,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "too large",
            "evidence_refs": ["ev_demo"],
        }
    )

    assert preview["status"] == "preview_ready"
    assert preview["submitted"] is False
    assert preview["approval_required"] is True
    assert preview["risk_gate"]["passed"] is True
    assert preview["estimated_cash_effect"] < 0
    assert broker.get_orders() == []
    assert broker.get_balance().cash == 50_000.0
    assert blocked["status"] == "blocked"
    assert blocked["risk_gate"]["passed"] is False
    assert "insufficient_cash" in blocked["risk_gate"]["blockers"]


def test_agent_paper_order_submission_requires_approval_reruns_preview_and_writes_reconciliation(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from broker import PaperBroker

    broker = PaperBroker(initial_cash=50_000.0, enable_risk=True)
    broker.set_prices({"000001": 10.0})
    runtime = AgentRuntime()
    session = runtime.create_session(title="Paper order control", default_desk="execution")

    proposal = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "CEO approval card only",
            "evidence_refs": ["ev_demo"],
        },
        broker=broker,
    )
    action = proposal["action"]
    blocked_submission = runtime.submit_paper_order_action(action["action_id"], broker=broker)
    runtime.approve_action(action["action_id"], decided_by="ceo")
    approved_submission = runtime.submit_paper_order_action(action["action_id"], broker=broker)
    run = approved_submission["run"]
    reconciliation = approved_submission["reconciliation"]

    assert proposal["status"] == "approval_required"
    assert proposal["preview"]["status"] == "preview_ready"
    assert action["risk_level"] == "paper_order"
    assert action["status"] == "approval_required"
    assert action["approval_required"] is True
    assert action["evidence_refs"]
    assert action["parameters"]["paper_order_preview"]["submitted"] is False
    assert "separate approved execution implementation" not in action["expected_effect"]
    assert "re-runs PaperBroker preview/risk gates" in action["expected_effect"]
    assert blocked_submission["status"] == "blocked"
    assert "approval required" in blocked_submission["run"]["stderr_summary"]
    assert approved_submission["status"] == "succeeded"
    assert run["status"] == "succeeded"
    assert run["tool_name"] == "paper.paper_order.submit"
    assert run["artifact_refs"]
    assert reconciliation["status"] == "submitted"
    assert reconciliation["order_id"].startswith("PAPER_")
    assert reconciliation["preview"]["status"] == "preview_ready"
    assert reconciliation["account_after"]["cash"] < 50_000.0
    assert broker.get_orders()[0].order_id == reconciliation["order_id"]
    assert broker.get_balance().cash < 50_000.0
    assert runtime.get_action(action["action_id"])["status"] == "succeeded"
    reset_datahub()


def test_agent_paper_order_submission_reblocks_stale_preview_without_submitting(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from broker import PaperBroker

    broker = PaperBroker(initial_cash=50_000.0, enable_risk=True)
    broker.set_prices({"000001": 10.0})
    runtime = AgentRuntime()
    session = runtime.create_session(title="Paper stale preview", default_desk="execution")
    proposal = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "will become stale",
            "evidence_refs": ["ev_demo"],
        },
        broker=broker,
    )
    runtime.approve_action(proposal["action"]["action_id"], decided_by="ceo")
    broker._cash = 0.0

    blocked = runtime.submit_paper_order_action(proposal["action"]["action_id"], broker=broker)

    assert blocked["status"] == "blocked"
    assert blocked["preview"]["status"] == "blocked"
    assert "insufficient_cash" in blocked["preview"]["risk_gate"]["blockers"]
    assert blocked["run"]["status"] == "blocked"
    assert blocked["run"]["artifact_refs"]
    assert broker.get_orders() == []
    assert runtime.get_action(proposal["action"]["action_id"])["status"] == "blocked"
    reset_datahub()


def test_agent_paper_order_proposal_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Paper order CLI/API", default_desk="execution")
    cli_code = run_cli(
        [
            "agent",
            "paper",
            "propose",
            "--session",
            session.session_id,
            "--symbol",
            "000001",
            "--side",
            "buy",
            "--quantity",
            "100",
            "--limit-price",
            "10",
            "--strategy",
            "manual",
            "--reason",
            "approval card",
            "--evidence",
            "ev_demo",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(
        "/api/agent/paper/proposals",
        json={
            "session_id": session.session_id,
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "approval card",
            "evidence_refs": ["ev_demo"],
        },
    )

    assert cli_code == 0
    assert cli_payload["data"]["proposal"]["status"] == "approval_required"
    assert cli_payload["data"]["proposal"]["action"]["status"] == "approval_required"
    assert cli_payload["data"]["proposal"]["preview"]["submitted"] is False
    assert api_res.status_code == 200
    assert api_res.json()["proposal"]["status"] == "approval_required"
    assert api_res.json()["proposal"]["action"]["risk_level"] == "paper_order"
    reset_datahub()


def test_agent_paper_order_submit_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Paper submit CLI/API", default_desk="execution")
    cli_proposal = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "cli submit",
            "evidence_refs": ["ev_demo"],
        },
    )
    api_proposal = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000002",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "api submit",
            "evidence_refs": ["ev_demo"],
        },
    )
    runtime.approve_action(cli_proposal["action"]["action_id"], decided_by="ceo")
    runtime.approve_action(api_proposal["action"]["action_id"], decided_by="ceo")

    cli_code = run_cli(["agent", "paper", "submit", cli_proposal["action"]["action_id"], "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(f"/api/agent/paper/actions/{api_proposal['action']['action_id']}/submit")

    assert cli_code == 0
    assert cli_payload["data"]["submission"]["status"] == "succeeded"
    assert cli_payload["data"]["submission"]["reconciliation"]["order_id"].startswith("PAPER_")
    assert api_res.status_code == 200
    assert api_res.json()["submission"]["status"] == "succeeded"
    assert api_res.json()["submission"]["run"]["artifact_refs"]
    reset_datahub()


def test_agent_paper_order_cancel_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Paper cancel CLI/API", default_desk="execution")
    cli_proposal = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "cli cancel",
            "evidence_refs": ["ev_demo"],
        },
    )
    api_proposal = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000002",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "api cancel",
            "evidence_refs": ["ev_demo"],
        },
    )

    cli_code = run_cli(
        [
            "agent",
            "paper",
            "cancel",
            cli_proposal["action"]["action_id"],
            "--reason",
            "CLI paper cancel",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(
        f"/api/agent/paper/actions/{api_proposal['action']['action_id']}/cancel",
        json={"reason": "API paper cancel"},
    )

    assert cli_code == 0
    assert cli_payload["data"]["cancellation"]["status"] == "canceled"
    assert cli_payload["data"]["cancellation"]["run"]["tool_name"] == "paper.paper_order.cancel"
    assert cli_payload["data"]["cancellation"]["reconciliation"]["status"] == "queued_action_canceled"
    assert api_res.status_code == 200
    assert api_res.json()["cancellation"]["status"] == "canceled"
    assert api_res.json()["cancellation"]["reconciliation"]["cancel_reason"] == "API paper cancel"
    assert runtime.get_action(cli_proposal["action"]["action_id"])["status"] == "canceled"
    assert runtime.get_action(api_proposal["action"]["action_id"])["status"] == "canceled"
    reset_datahub()


def test_agent_action_api_includes_paper_reconciliation_summaries(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from broker import PaperBroker
    from web.api.app import create_app

    broker = PaperBroker(initial_cash=50_000.0, enable_risk=True)
    broker.set_prices({"000001": 10.0})
    runtime = AgentRuntime()
    session = runtime.create_session(title="Paper reconciliation detail", default_desk="execution")
    proposal = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "api detail",
            "evidence_refs": ["ev_demo"],
        },
        broker=broker,
    )
    runtime.approve_action(proposal["action"]["action_id"], decided_by="ceo")
    runtime.submit_paper_order_action(proposal["action"]["action_id"], broker=broker)

    api_detail = TestClient(create_app()).get(f"/api/agent/actions/{proposal['action']['action_id']}")

    assert api_detail.status_code == 200
    reconciliations = api_detail.json()["paper_reconciliations"]
    assert len(reconciliations) == 1
    assert reconciliations[0]["status"] == "submitted"
    assert reconciliations[0]["order_id"].startswith("PAPER_")
    assert reconciliations[0]["account_after"]["cash"] < 50_000.0
    assert reconciliations[0]["evidence_id"].startswith("ev_")
    assert reconciliations[0]["path"].endswith(".json")
    reset_datahub()


def test_agent_paper_order_cancel_records_queue_and_broker_cancellation_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from broker import PaperBroker
    from broker.fill_models import FillModel, MatchResult

    class PartialFill(FillModel):
        def evaluate(self, requested_shares, side, market_price, symbol="", ctx=None):
            return MatchResult(
                filled_shares=40,
                fill_price=market_price,
                status="partial_filled",
                reason="test partial fill",
            )

    runtime = AgentRuntime()
    session = runtime.create_session(title="Paper cancel semantics", default_desk="execution")
    queued_broker = PaperBroker(initial_cash=50_000.0, enable_risk=True)
    queued_broker.set_prices({"000001": 10.0})
    queued = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "queued cancel",
            "evidence_refs": ["ev_demo"],
        },
        broker=queued_broker,
    )

    queued_cancel = runtime.cancel_paper_order_action(
        queued["action"]["action_id"],
        broker=queued_broker,
        reason="CEO withdrew approval request",
    )

    assert queued_cancel["status"] == "canceled"
    assert queued_cancel["run"]["tool_name"] == "paper.paper_order.cancel"
    assert queued_cancel["reconciliation"]["status"] == "queued_action_canceled"
    assert queued_cancel["reconciliation"]["order_id"] == ""
    assert queued_cancel["run"]["artifact_refs"]
    assert queued_broker.get_orders() == []
    assert runtime.get_action(queued["action"]["action_id"])["status"] == "canceled"

    active_broker = PaperBroker(initial_cash=50_000.0, enable_risk=True, fill_model=PartialFill())
    active_broker.set_prices({"000002": 10.0})
    submitted = runtime.propose_paper_order(
        session_id=session.session_id,
        intent={
            "symbol": "000002",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
            "reason": "submitted cancel",
            "evidence_refs": ["ev_demo"],
        },
        broker=active_broker,
    )
    action_id = submitted["action"]["action_id"]
    runtime.approve_action(action_id, decided_by="ceo")
    submission = runtime.submit_paper_order_action(action_id, broker=active_broker)

    broker_cancel = runtime.cancel_paper_order_action(
        action_id,
        broker=active_broker,
        reason="CEO cancels remaining shares",
    )

    assert submission["status"] == "succeeded"
    assert active_broker.get_orders()[0].status == "cancelled"
    assert broker_cancel["status"] == "canceled"
    assert broker_cancel["run"]["status"] == "succeeded"
    assert broker_cancel["reconciliation"]["status"] == "order_canceled"
    assert broker_cancel["reconciliation"]["order_id"] == submission["reconciliation"]["order_id"]
    assert broker_cancel["reconciliation"]["orders_after"][0]["status"] == "cancelled"
    assert runtime.get_action(action_id)["status"] == "succeeded"
    assert [item["status"] for item in runtime.paper_reconciliations_for_action(action_id)][:2] == [
        "order_canceled",
        "submitted",
    ]
    reset_datahub()


def test_agent_actions_expire_before_approval_or_dispatch(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    now = {"value": "2026-06-14T00:00:00Z"}
    monkeypatch.setattr("agent_os.runtime._now", lambda: now["value"])
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Action expiry")
    write_action = runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Repair stale data",
        parameters={"tool_id": "astroq.data.repair", "table": "stock_limit_list"},
    )
    read_action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Health check",
        parameters={"tool_id": "astroq.health"},
    )

    assert write_action.expires_at == "2026-06-14T00:15:00Z"
    assert read_action.expires_at == "2026-06-14T00:15:00Z"

    now["value"] = "2026-06-14T00:16:00Z"
    expired = runtime.expire_actions()

    assert expired["expired"] == 2
    assert {row["action_id"] for row in expired["actions"]} == {write_action.action_id, read_action.action_id}
    assert runtime.get_action(write_action.action_id)["status"] == "expired"

    try:
        runtime.approve_action(write_action.action_id)
    except ValueError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("expired action should not be approved")

    run = runtime.dispatch_action(read_action.action_id, runner=fake_run)

    assert calls == []
    assert run.status == "blocked"
    assert "expired" in run.stderr_summary
    assert runtime.get_action(read_action.action_id)["status"] == "expired"
    reset_datahub()


def test_agent_cli_and_api_expire_actions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    now = {"value": "2026-06-14T00:00:00Z"}
    monkeypatch.setattr("agent_os.runtime._now", lambda: now["value"])
    runtime = AgentRuntime()
    session = runtime.create_session(title="Expire CLI API")
    cli_action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="CLI expiry",
        parameters={"tool_id": "astroq.health"},
    )
    api_action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="API expiry",
        parameters={"tool_id": "astroq.health"},
    )

    now["value"] = "2026-06-14T00:16:00Z"
    cli_code = run_cli(["agent", "expire", "--session", session.session_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)

    now["value"] = "2026-06-14T00:00:00Z"
    fresh_action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="API second expiry",
        parameters={"tool_id": "astroq.health"},
    )
    now["value"] = "2026-06-14T00:16:00Z"
    api_res = TestClient(create_app()).post("/api/agent/actions/expire", json={"session_id": session.session_id})

    assert cli_code == 0
    assert cli_payload["data"]["result"]["expired"] == 2
    assert {row["action_id"] for row in cli_payload["data"]["result"]["actions"]} == {
        cli_action.action_id,
        api_action.action_id,
    }
    assert api_res.status_code == 200
    assert api_res.json()["result"]["expired"] == 1
    assert api_res.json()["result"]["actions"][0]["action_id"] == fresh_action.action_id
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


def test_agent_evidence_snapshots_survive_source_mutation_and_deletion(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.evidence import EvidenceResolver
    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    artifact = tmp_path / "runtime" / "artifacts" / "lifecycle" / "latest.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"status": "original"}\n', encoding="utf-8")

    evidence = runtime.create_evidence(
        kind="artifact",
        label="Lifecycle original",
        uri=str(artifact),
        summary="Lifecycle readiness source artifact.",
    )
    snapshot_path = Path(evidence.snapshot_uri)
    source_hash = evidence.hash

    artifact.write_text('{"status": "mutated"}\n', encoding="utf-8")
    changed = EvidenceResolver().resolve(evidence.evidence_id)
    artifact.unlink()
    missing_source = EvidenceResolver().resolve(evidence.evidence_id)

    assert source_hash.startswith("sha256:")
    assert snapshot_path.exists()
    assert snapshot_path.read_text(encoding="utf-8") == '{"status": "original"}\n'
    assert "/agent/evidence/" in evidence.snapshot_uri
    assert changed["status"] == "source_changed"
    assert changed["evidence"]["hash"] == source_hash
    assert changed["evidence"]["current_hash"] != source_hash
    assert changed["snapshot"]["uri"] == evidence.snapshot_uri
    assert changed["snapshot"]["hash"] == source_hash
    assert missing_source["status"] == "source_missing"
    assert missing_source["evidence"]["evidence_id"] == evidence.evidence_id
    assert missing_source["snapshot"]["uri"] == evidence.snapshot_uri
    reset_datahub()


def test_agent_reports_generate_artifacts_and_cite_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.evidence import EvidenceResolver
    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Daily CEO Brief", default_desk="reporting")
    lifecycle = runtime.create_evidence(
        kind="web_route",
        label="Lifecycle readiness",
        uri="/system?tab=lifecycle",
        summary="Lifecycle readiness is blocked by missing strategy evidence.",
    )
    runtime.add_message(
        session.session_id,
        role="desk_agent",
        desk="reporting",
        content="Lifecycle readiness needs CEO attention.",
        evidence_refs=[lifecycle.evidence_id],
    )

    report = runtime.generate_report(session_id=session.session_id, kind="daily_brief")

    report_path = Path(report["path"])
    markdown_path = Path(report["markdown_path"])
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    evidence_resolution = EvidenceResolver().resolve(report["evidence_id"])

    assert report["kind"] == "daily_brief"
    assert report["title"] == "Daily CEO Brief"
    assert report_path.exists()
    assert markdown_path.exists()
    assert str(report_path).endswith(".json")
    assert str(markdown_path).endswith(".md")
    assert payload["session_id"] == session.session_id
    assert payload["evidence_refs"] == [lifecycle.evidence_id]
    assert payload["missing_evidence"] == []
    assert payload["sections"][0]["evidence_refs"] == [lifecycle.evidence_id]
    assert "Lifecycle readiness needs CEO attention." in markdown_path.read_text(encoding="utf-8")
    assert evidence_resolution["status"] == "fresh"
    assert evidence_resolution["evidence"]["kind"] == "report"
    assert evidence_resolution["snapshot"] is not None

    listed = runtime.list_reports(session.session_id)

    assert listed["total"] == 1
    assert listed["reports"][0]["report_id"] == report["report_id"]
    assert listed["reports"][0]["evidence_id"] == report["evidence_id"]
    reset_datahub()


def test_agent_reports_aggregate_system_artifact_context(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    artifact_payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 2, "ready": 4},
            "blockers": [{"dimension": "macro_gdp", "reason": "source_not_updated"}],
        },
        "data-sources/latest.json": {
            "summary": {"source_count": 8, "capability_count": 300, "project_integrated_count": 42},
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "production": 3, "blocked": 9},
        },
        "architecture/ast/latest.json": {
            "summary": {"issue_count": 1, "severity_counts": {"P1": 1}},
        },
        "tests/design/latest.json": {
            "summary": {"case_count": 180, "risk_count": 14, "design_risk_count": 3},
        },
    }
    for relative, payload in artifact_payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Aggregated CEO Brief", default_desk="reporting")
    report = runtime.generate_report(session_id=session.session_id, kind="daily_brief")

    payload = json.loads(Path(report["path"]).read_text(encoding="utf-8"))
    sections = {section["section_id"]: section for section in payload["sections"]}
    context = payload["artifact_context"]

    assert "artifact_readiness" in sections
    assert "artifact_findings" in sections
    assert "semantic_synthesis" in sections
    assert "domain_scorecard" in sections
    assert context["available_count"] == 5
    assert context["missing_count"] >= 1
    assert context["synthesis"]["status"] == "blocked"
    assert context["synthesis"]["root_cause_count"] >= 2
    scorecard = context["domain_scorecard"]
    scorecard_by_desk = {row["desk"]: row for row in scorecard["desks"]}
    assert scorecard["overall_status"] == "blocked"
    assert list(scorecard_by_desk) == ["data", "research", "risk", "execution", "engineering", "reporting"]
    assert scorecard_by_desk["risk"]["status"] == "blocked"
    assert scorecard_by_desk["risk"]["recommended_command"] == "astroq lifecycle check --json"
    assert scorecard_by_desk["data"]["recommended_command"] == "astroq data sources diff-registry --json"
    assert scorecard_by_desk["execution"]["status"] == "blocked"
    assert "lifecycle_blocker" in scorecard_by_desk["execution"]["root_causes"]
    assert "source_narratives" in sections
    source_narratives = context["source_narratives"]
    narratives_by_key = {row["key"]: row for row in source_narratives["items"]}
    assert source_narratives["overall_status"] == "blocked"
    assert narratives_by_key["lifecycle"]["owner_desk"] == "risk"
    assert narratives_by_key["lifecycle"]["status"] == "blocked"
    assert narratives_by_key["lifecycle"]["recommended_command"] == "astroq lifecycle check --json"
    assert "macro_gdp" in narratives_by_key["lifecycle"]["evidence_summary"]
    assert narratives_by_key["data_sources"]["owner_desk"] == "data"
    assert narratives_by_key["data_sources"]["status"] == "attention"
    assert narratives_by_key["data_sources"]["recommended_command"] == "astroq data sources diff-registry --json"
    assert narratives_by_key["strategy_competition"]["owner_desk"] == "research"
    assert narratives_by_key["strategy_competition"]["status"] == "blocked"
    assert any(item["key"] == "lifecycle" and item["status"] == "available" for item in context["items"])
    assert any(item["key"] == "codegraph" and item["status"] == "missing" for item in context["items"])
    assert "macro_gdp" in sections["artifact_findings"]["body"]
    assert "source_not_updated" in sections["artifact_findings"]["body"]
    assert "macro_gdp" in sections["semantic_synthesis"]["body"]
    assert "strategy_evidence_blocked" in sections["semantic_synthesis"]["body"]
    assert "data_source_gap" in sections["semantic_synthesis"]["body"]
    assert "strategy_competition" in sections["artifact_readiness"]["body"]
    assert "Risk: blocked" in sections["domain_scorecard"]["body"]
    assert "lifecycle [Risk]: blocked" in sections["source_narratives"]["body"]
    assert "data_sources [Data]: attention" in sections["source_narratives"]["body"]
    assert "data-sources/latest.json" in sections["artifact_readiness"]["body"]
    assert "codegraph" in sections["artifact_readiness"]["body"]
    assert "artifact_context" in payload
    assert "macro_gdp" in Path(report["markdown_path"]).read_text(encoding="utf-8")
    reset_datahub()


def test_agent_reports_synthesize_cross_session_trends_from_history(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 1},
            "blockers": [{"dimension": "macro_gdp", "reason": "source_not_updated"}],
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 9},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    first = runtime.create_session(title="First CEO brief", default_desk="reporting")
    second = runtime.create_session(title="Second CEO brief", default_desk="reporting")
    runtime.generate_report(session_id=first.session_id, kind="daily_brief")
    report = runtime.generate_report(session_id=second.session_id, kind="daily_brief")

    payload = json.loads(Path(report["path"]).read_text(encoding="utf-8"))
    sections = {section["section_id"]: section for section in payload["sections"]}
    trend = payload["artifact_context"]["trend_synthesis"]

    assert "trend_synthesis" in sections
    assert trend["status"] == "attention"
    assert trend["history_report_count"] == 1
    assert trend["recurring_root_cause_count"] >= 2
    assert {row["cause"] for row in trend["recurring_root_causes"]} >= {
        "lifecycle_blocker",
        "strategy_evidence_blocked",
    }
    assert all(row["total_count"] >= 2 for row in trend["recurring_root_causes"])
    assert "lifecycle_blocker" in sections["trend_synthesis"]["body"]
    assert "Repeated root cause" in sections["trend_synthesis"]["body"]
    reset_datahub()


def test_agent_reports_build_artifact_specific_timelines_from_history(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    lifecycle = artifact_root / "lifecycle/latest.json"
    strategy = artifact_root / "tournaments/strategy_competition_latest.json"
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    strategy.parent.mkdir(parents=True, exist_ok=True)
    lifecycle.write_text(
        json.dumps(
            {
                "status": "blocked",
                "summary": {"blocked": 1, "ready": 4},
                "blockers": [{"dimension": "macro_gdp", "reason": "source_not_updated"}],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    strategy.write_text(
        json.dumps({"summary": {"total": 12, "blocked": 5}}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    runtime = AgentRuntime()
    first = runtime.create_session(title="First timeline brief", default_desk="reporting")
    second = runtime.create_session(title="Second timeline brief", default_desk="reporting")
    runtime.generate_report(session_id=first.session_id, kind="daily_brief")

    lifecycle.write_text(
        json.dumps({"status": "ready", "summary": {"blocked": 0, "ready": 6}}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    strategy.write_text(
        json.dumps({"summary": {"total": 12, "blocked": 0, "production": 4}}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    report = runtime.generate_report(session_id=second.session_id, kind="daily_brief")

    payload = json.loads(Path(report["path"]).read_text(encoding="utf-8"))
    sections = {section["section_id"]: section for section in payload["sections"]}
    timelines = payload["artifact_context"]["artifact_timeline_synthesis"]
    by_key = {row["key"]: row for row in timelines["items"]}

    assert "artifact_timelines" in sections
    assert timelines["status"] == "changed"
    assert timelines["history_report_count"] == 1
    assert by_key["lifecycle"]["changed"] is True
    assert by_key["lifecycle"]["summary_changed"] is True
    assert by_key["lifecycle"]["previous_finding_count"] == 1
    assert by_key["lifecycle"]["current_finding_count"] == 0
    assert by_key["strategy_competition"]["changed"] is True
    assert "lifecycle: changed" in sections["artifact_timelines"]["body"]
    reset_datahub()


def test_agent_reports_build_causal_chain_synthesis_from_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 2, "ready": 4},
            "blockers": [
                {"dimension": "macro_gdp", "reason": "source_not_updated"},
                {"dimension": "stock_limit_list", "reason": "rate_limited"},
            ],
        },
        "data-sources/latest.json": {
            "summary": {
                "source_count": 8,
                "capability_count": 300,
                "project_integrated_count": 42,
                "capability_unmapped_count": 21,
            },
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 9, "insufficient_alpha_evidence": 7},
        },
        "architecture/ast/latest.json": {
            "summary": {"issue_count": 2, "severity_counts": {"P1": 1, "P2": 1}},
        },
        "tests/design/latest.json": {
            "summary": {"case_count": 180, "risk_count": 14, "design_risk_count": 3},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Causal CEO Brief", default_desk="reporting")
    report = runtime.generate_report(session_id=session.session_id, kind="daily_brief")

    payload = json.loads(Path(report["path"]).read_text(encoding="utf-8"))
    sections = {section["section_id"]: section for section in payload["sections"]}
    causal = payload["artifact_context"]["causal_chain_synthesis"]

    assert "causal_chain_synthesis" in sections
    assert causal["status"] == "blocked"
    assert causal["chain_count"] >= 2
    chain_ids = {chain["chain_id"] for chain in causal["chains"]}
    assert "data_readiness_to_strategy_block" in chain_ids
    assert "engineering_quality_to_release_risk" in chain_ids
    strategy_chain = next(chain for chain in causal["chains"] if chain["chain_id"] == "data_readiness_to_strategy_block")
    assert strategy_chain["severity"] == "P0"
    assert strategy_chain["owner_desks"] == ["data", "research", "risk"]
    assert strategy_chain["nodes"] == ["data_source_gap", "lifecycle_blocker", "strategy_evidence_blocked"]
    assert "macro_gdp" in strategy_chain["evidence"]
    assert "stock_limit_list" in strategy_chain["evidence"]
    assert "Do not promote" in strategy_chain["next_action"]
    assert "data_readiness_to_strategy_block" in sections["causal_chain_synthesis"]["body"]
    assert "data_source_gap -> lifecycle_blocker -> strategy_evidence_blocked" in sections["causal_chain_synthesis"]["body"]
    assert "causal_chain_synthesis" in Path(report["markdown_path"]).read_text(encoding="utf-8")
    reset_datahub()


def test_agent_reports_escalate_recurring_causal_chains_from_history(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 2, "ready": 4},
            "blockers": [
                {"dimension": "macro_gdp", "reason": "source_not_updated"},
                {"dimension": "stock_limit_list", "reason": "rate_limited"},
            ],
        },
        "data-sources/latest.json": {
            "summary": {
                "source_count": 8,
                "capability_count": 300,
                "project_integrated_count": 42,
                "capability_unmapped_count": 21,
            },
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 9, "insufficient_alpha_evidence": 7},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    first = runtime.create_session(title="First causal brief", default_desk="reporting")
    second = runtime.create_session(title="Second causal brief", default_desk="reporting")
    third = runtime.create_session(title="Third causal brief", default_desk="reporting")
    runtime.generate_report(session_id=first.session_id, kind="daily_brief")
    runtime.generate_report(session_id=second.session_id, kind="daily_brief")
    report = runtime.generate_report(session_id=third.session_id, kind="daily_brief")

    payload = json.loads(Path(report["path"]).read_text(encoding="utf-8"))
    sections = {section["section_id"]: section for section in payload["sections"]}
    causal = payload["artifact_context"]["causal_chain_synthesis"]
    chain = next(chain for chain in causal["chains"] if chain["chain_id"] == "data_readiness_to_strategy_block")

    assert causal["recurring_chain_count"] >= 1
    assert chain["history"]["recurring"] is True
    assert chain["history"]["max_total_count"] >= 3
    assert set(chain["history"]["recurring_causes"]) >= {
        "lifecycle_blocker",
        "strategy_evidence_blocked",
    }
    assert chain["escalation"] == "recurring_blocker"
    assert "standing owner review" in chain["next_action"]
    assert "Recurring causal chain" in sections["causal_chain_synthesis"]["body"]
    assert "3 report(s)" in sections["causal_chain_synthesis"]["body"]
    reset_datahub()


def test_agent_report_notification_env_only_writes_audit_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "secret-chat")
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    sent: list[tuple[str, dict]] = []

    def fake_sender(channel: str, payload: dict) -> dict:
        sent.append((channel, payload))
        return {"ok": True, "status_code": 200, "provider_message_id": "fake-message"}

    runtime = AgentRuntime()
    session = runtime.create_session(title="Notify CEO", default_desk="reporting")
    runtime.add_message(session.session_id, role="desk_agent", desk="reporting", content="需要 CEO 注意。")
    report = runtime.generate_report(session_id=session.session_id, kind="daily_brief")

    notification = runtime.notify_report(report["report_id"], channels=["telegram"], sender=fake_sender)
    blocked = runtime.notify_report(report["report_id"], channels=["feishu"], sender=fake_sender)

    assert notification["status"] == "sent"
    assert notification["report_id"] == report["report_id"]
    assert notification["sent_count"] == 1
    assert notification["failed_count"] == 0
    assert notification["channels"][0]["channel"] == "telegram"
    assert notification["channels"][0]["status"] == "sent"
    assert notification["channels"][0]["missing_env"] == []
    assert sent == [("telegram", sent[0][1])]
    assert sent[0][1]["title"] == "Daily CEO Brief"
    assert report["summary"] in sent[0][1]["body"]
    assert notification["evidence"]["label"] == "Agent report notification"
    assert Path(notification["path"]).exists()
    audit_text = Path(notification["path"]).read_text(encoding="utf-8")
    assert "secret-token" not in audit_text
    assert "secret-chat" not in audit_text
    assert "TELEGRAM_BOT_TOKEN" in audit_text
    assert blocked["status"] == "blocked"
    assert blocked["channels"][0]["status"] == "missing_secret"
    assert blocked["channels"][0]["missing_env"] == ["FEISHU_WEBHOOK_URL"]
    assert len(sent) == 1
    reset_datahub()


def test_agent_report_notification_cli_and_api_dry_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Notify CLI/API", default_desk="reporting")
    report = runtime.generate_report(session_id=session.session_id, kind="daily_brief")

    cli_code = run_cli(
        [
            "agent",
            "notify",
            "report",
            report["report_id"],
            "--channel",
            "telegram",
            "--dry-run",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(
        f"/api/agent/reports/{report['report_id']}/notify",
        json={"channels": ["wechat"], "dry_run": True},
    )

    assert cli_code == 0
    assert cli_payload["data"]["notification"]["status"] == "dry_run"
    assert cli_payload["data"]["notification"]["channels"][0]["status"] == "dry_run"
    assert Path(cli_payload["data"]["notification"]["path"]).exists()
    assert api_res.status_code == 200
    assert api_res.json()["notification"]["status"] == "dry_run"
    assert api_res.json()["notification"]["channels"][0]["channel"] == "wechat"
    assert Path(api_res.json()["notification"]["path"]).exists()
    reset_datahub()


def test_agent_report_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Reports API", default_desk="reporting")

    cli_code = run_cli(["agent", "report", "data_quality", "--session", session.session_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_client = TestClient(create_app())
    api_create = api_client.post("/api/agent/reports", json={"kind": "risk_review", "session_id": session.session_id})
    api_list = api_client.get(f"/api/agent/reports?session_id={session.session_id}")

    assert cli_code == 0
    assert cli_payload["data"]["report"]["kind"] == "data_quality_review"
    assert {section["section_id"] for section in cli_payload["data"]["report"]["sections"]} >= {"data_quality_evidence"}
    assert Path(cli_payload["data"]["report"]["path"]).exists()
    assert api_create.status_code == 200
    assert api_create.json()["report"]["kind"] == "risk_review"
    assert {section["section_id"] for section in api_create.json()["report"]["sections"]} >= {"risk_readiness"}
    assert Path(api_create.json()["report"]["path"]).exists()
    assert api_list.status_code == 200
    assert api_list.json()["total"] == 2
    assert {row["kind"] for row in api_list.json()["reports"]} == {"data_quality_review", "risk_review"}
    reset_datahub()


def test_agent_reports_support_dedicated_operating_rhythm_templates(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Operating rhythm", default_desk="reporting")
    lifecycle = runtime.create_evidence(
        kind="web_route",
        label="Lifecycle readiness",
        uri="/system?tab=lifecycle",
        summary="Lifecycle readiness has one risk blocker.",
    )
    codegraph = runtime.create_evidence(
        kind="web_route",
        label="CodeGraph diagnostics",
        uri="/system?tab=codegraph",
        summary="Engineering diagnostics ready.",
    )
    runtime.add_message(
        session.session_id,
        role="desk_agent",
        desk="risk",
        content="Risk Desk flags one open blocker.",
        evidence_refs=[lifecycle.evidence_id],
    )
    engineering_action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="work_order",
        risk_level="read_only",
        summary="Review CodeGraph architecture finding",
        evidence_refs=[codegraph.evidence_id],
    )
    runtime.record_run(
        action_id=engineering_action.action_id,
        tool_name="qa.engineering.digest",
        command=["qa", "engineering"],
        status="succeeded",
        return_code=0,
        stdout_summary="Engineering diagnostic recorded.",
        stderr_summary="",
        artifact_refs=[codegraph.evidence_id],
    )
    runtime.create_work_order(
        session_id=session.session_id,
        title="Investigate CodeGraph architecture finding",
        summary="Engineering Desk captured a concrete follow-up task.",
        impact="Keeps repository edits outside the Web runtime.",
        affected_files=["agent_os/runtime.py"],
        suggested_verification=[".venv/bin/python -m pytest tests/test_agent_os_contracts.py -q"],
        evidence_refs=[codegraph.evidence_id],
    )

    expected_sections = {
        "data_quality_review": "data_quality_evidence",
        "risk_review": "risk_readiness",
        "execution_reconciliation": "execution_reconciliation",
        "engineering_digest": "engineering_work_orders",
        "release_audit": "release_audit",
    }
    generated = {kind: runtime.generate_report(session_id=session.session_id, kind=kind) for kind in expected_sections}

    assert set(generated) == set(expected_sections)
    for kind, section_id in expected_sections.items():
        report = generated[kind]
        section_ids = {section["section_id"] for section in report["sections"]}
        assert report["kind"] == kind
        assert section_id in section_ids
        assert report["evidence_refs"]
        assert Path(report["path"]).exists()
        assert section_id in Path(report["path"]).read_text(encoding="utf-8")
    assert "Investigate CodeGraph architecture finding" in Path(generated["engineering_digest"]["path"]).read_text(encoding="utf-8")

    reset_datahub()


def test_agent_report_rhythm_generates_due_templates_and_skips_fresh_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Operating rhythm runner", default_desk="reporting")

    first = runtime.run_report_rhythm(session_id=session.session_id)
    second = runtime.run_report_rhythm(session_id=session.session_id)
    forced = runtime.run_report_rhythm(session_id=session.session_id, force=True)

    assert first["status"] == "ready"
    assert first["generated_count"] == 8
    assert first["skipped_count"] == 0
    assert {item["kind"] for item in first["items"]} == {
        "daily_brief",
        "weekly_review",
        "audit_pack",
        "data_quality_review",
        "risk_review",
        "execution_reconciliation",
        "engineering_digest",
        "release_audit",
    }
    assert all(item["status"] == "generated" for item in first["items"])
    assert Path(first["path"]).exists()
    assert first["evidence"]["kind"] == "ledger"
    assert Path(first["evidence"]["snapshot_uri"]).exists()

    assert second["generated_count"] == 0
    assert second["skipped_count"] == 8
    assert all(item["status"] == "skipped" for item in second["items"])
    assert all(item["reason"] == "not_due" for item in second["items"])
    assert Path(second["path"]).exists()

    assert forced["generated_count"] == 8
    assert forced["force"] is True
    assert all(item["reason"] == "force" for item in forced["items"])
    assert runtime.list_reports(session.session_id)["total"] == 16
    reset_datahub()


def test_agent_report_rhythm_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Rhythm API", default_desk="reporting")

    cli_code = run_cli(["agent", "rhythm", "--session", session.session_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_client = TestClient(create_app())
    api_rhythm = api_client.post("/api/agent/reports/rhythm", json={"session_id": session.session_id, "force": True})

    assert cli_code == 0
    assert cli_payload["data"]["rhythm"]["generated_count"] == 8
    assert cli_payload["data"]["rhythm"]["skipped_count"] == 0
    assert Path(cli_payload["data"]["rhythm"]["path"]).exists()
    assert api_rhythm.status_code == 200
    assert api_rhythm.json()["rhythm"]["generated_count"] == 8
    assert api_rhythm.json()["rhythm"]["force"] is True
    assert Path(api_rhythm.json()["rhythm"]["path"]).exists()
    reset_datahub()


def test_agent_scheduled_report_rhythm_runs_active_sessions_and_writes_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    first = runtime.create_session(title="Active reporting A", default_desk="reporting")
    second = runtime.create_session(title="Active reporting B", default_desk="reporting")
    archived = runtime.create_session(title="Archived reporting", default_desk="reporting")
    runtime.update_session(archived.session_id, status="archived")

    scheduled = runtime.run_scheduled_report_rhythm()

    assert scheduled["status"] == "ready"
    assert scheduled["session_count"] == 2
    assert scheduled["generated_count"] == 16
    assert scheduled["skipped_count"] == 0
    assert {item["session_id"] for item in scheduled["sessions"]} == {first.session_id, second.session_id}
    assert scheduled["evidence"]["label"] == "Agent scheduled report rhythm"
    assert Path(scheduled["path"]).exists()
    assert runtime.list_reports(first.session_id)["total"] == 8
    assert runtime.list_reports(second.session_id)["total"] == 8
    assert runtime.list_reports(archived.session_id)["total"] == 0
    reset_datahub()


def test_agent_scheduled_report_rhythm_cli_and_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    first = runtime.create_session(title="Scheduled rhythm CLI", default_desk="reporting")
    second = runtime.create_session(title="Scheduled rhythm API", default_desk="reporting")

    cli_code = run_cli(["agent", "rhythm", "--all-active", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post("/api/agent/reports/rhythm/scheduled", json={"force": True})

    assert cli_code == 0
    assert cli_payload["data"]["schedule"]["session_count"] == 2
    assert cli_payload["data"]["schedule"]["generated_count"] == 16
    assert Path(cli_payload["data"]["schedule"]["path"]).exists()
    assert api_res.status_code == 200
    assert api_res.json()["schedule"]["force"] is True
    assert api_res.json()["schedule"]["session_count"] == 2
    assert api_res.json()["schedule"]["generated_count"] == 16
    assert {item["session_id"] for item in api_res.json()["schedule"]["sessions"]} == {first.session_id, second.session_id}
    reset_datahub()


def test_agent_evidence_resolver_returns_safe_web_route_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.evidence import EvidenceResolver
    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    local_route = runtime.create_evidence(
        kind="web_route",
        label="Lifecycle view",
        uri="/system?tab=lifecycle",
        summary="Open lifecycle readiness detail.",
    )
    external_route = runtime.create_evidence(
        kind="web_route",
        label="External route",
        uri="https://example.com/not-local",
        summary="External links must not become CEO Office navigation.",
    )

    local = EvidenceResolver().resolve(local_route.evidence_id)
    external = EvidenceResolver().resolve(external_route.evidence_id)

    assert local["status"] == "fresh"
    assert local["navigation"]["kind"] == "web_route"
    assert local["navigation"]["href"] == "/system?tab=lifecycle"
    assert local["navigation"]["label"] == "Lifecycle view"
    assert external["navigation"] is None
    reset_datahub()


def test_agent_evidence_resolver_returns_safe_file_and_code_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.evidence import EvidenceResolver
    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    code = runtime.create_evidence(
        kind="code",
        label="Agent runtime route",
        uri="agent_os/runtime.py:356",
        summary="Code location for AgentRuntime.create_evidence.",
    )
    file_evidence = runtime.create_evidence(
        kind="file",
        label="Agent guide",
        uri="AGENTS.md",
        summary="Agent operating guide.",
    )
    outside_file = tmp_path / "outside-secret.txt"
    outside_file.write_text("do not navigate outside repo", encoding="utf-8")
    outside_existing = runtime.create_evidence(
        kind="file",
        label="Existing external file",
        uri=str(outside_file),
        summary="Existing external files can be snapshotted but not navigated.",
    )
    unsafe = runtime.create_evidence(
        kind="file",
        label="Unsafe external file",
        uri="../outside-secret.txt",
        summary="Should not produce local file navigation.",
    )

    resolved_code = EvidenceResolver().resolve(code.evidence_id)
    resolved_file = EvidenceResolver().resolve(file_evidence.evidence_id)
    resolved_outside_existing = EvidenceResolver().resolve(outside_existing.evidence_id)
    resolved_unsafe = EvidenceResolver().resolve(unsafe.evidence_id)

    assert resolved_code["status"] == "fresh"
    assert resolved_code["navigation"] == {
        "kind": "code",
        "path": "agent_os/runtime.py",
        "line": "356",
        "href": "/system?tab=codegraph&file=agent_os%2Fruntime.py&line=356",
        "label": "Agent runtime route",
    }
    assert resolved_code["evidence"]["hash"].startswith("sha256:")
    assert resolved_file["status"] == "fresh"
    assert resolved_file["navigation"]["kind"] == "file"
    assert resolved_file["navigation"]["path"] == "AGENTS.md"
    assert resolved_file["navigation"]["href"] == "/system?tab=codegraph&file=AGENTS.md"
    assert resolved_outside_existing["status"] == "fresh"
    assert resolved_outside_existing["evidence"]["hash"].startswith("sha256:")
    assert resolved_outside_existing["navigation"] is None
    assert resolved_unsafe["navigation"] is None
    reset_datahub()


def test_agent_evidence_resolver_returns_safe_cli_and_api_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.evidence import EvidenceResolver
    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    cli = runtime.create_evidence(
        kind="cli_command",
        label="Lifecycle CLI",
        uri="astroq lifecycle check --json",
        summary="CLI command that reproduces lifecycle readiness evidence.",
    )
    local_venv_cli = runtime.create_evidence(
        kind="cli_command",
        label="Local astroq CLI",
        uri=".venv/bin/astroq docs check --json",
        summary="Local virtualenv astroq command.",
    )
    local_api = runtime.create_evidence(
        kind="api_endpoint",
        label="Agent desks API",
        uri="/api/agent/desks",
        summary="Local API endpoint for desk registry evidence.",
    )
    unsafe_cli = runtime.create_evidence(
        kind="cli_command",
        label="Unsafe CLI",
        uri="astroq lifecycle check --json; rm -rf var",
        summary="Shell syntax must not become a runnable command.",
    )
    unsafe_path_cli = runtime.create_evidence(
        kind="cli_command",
        label="Unsafe path CLI",
        uri="/tmp/astroq docs check --json",
        summary="Unexpected astroq executable paths must not become runnable commands.",
    )
    external_api = runtime.create_evidence(
        kind="api_endpoint",
        label="External API",
        uri="https://example.com/api/agent/desks",
        summary="External URLs must not become local API navigation.",
    )

    resolved_cli = EvidenceResolver().resolve(cli.evidence_id)
    resolved_local_venv_cli = EvidenceResolver().resolve(local_venv_cli.evidence_id)
    resolved_api = EvidenceResolver().resolve(local_api.evidence_id)
    resolved_unsafe_cli = EvidenceResolver().resolve(unsafe_cli.evidence_id)
    resolved_unsafe_path_cli = EvidenceResolver().resolve(unsafe_path_cli.evidence_id)
    resolved_external_api = EvidenceResolver().resolve(external_api.evidence_id)

    assert resolved_cli["status"] == "fresh"
    assert resolved_cli["navigation"] == {
        "kind": "cli_command",
        "command": "astroq lifecycle check --json",
        "argv": ["astroq", "lifecycle", "check", "--json"],
        "label": "Lifecycle CLI",
    }
    assert resolved_local_venv_cli["navigation"]["argv"] == [".venv/bin/astroq", "docs", "check", "--json"]
    assert resolved_api["status"] == "fresh"
    assert resolved_api["navigation"] == {
        "kind": "api_endpoint",
        "method": "GET",
        "href": "/api/agent/desks",
        "label": "Agent desks API",
    }
    assert resolved_unsafe_cli["navigation"] is None
    assert resolved_unsafe_path_cli["navigation"] is None
    assert resolved_external_api["navigation"] is None
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


def test_agent_runtime_routes_ceo_message_to_deterministic_desk_response(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Daily CEO Brief", default_desk="reporting")

    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="reporting",
        content="今天系统该做什么？",
    )

    ceo_message = routed["message"]
    desk_response = routed["desk_response"]
    loaded = runtime.get_session(session.session_id)
    actions = [runtime.get_action(action_id) for action_id in desk_response.proposed_actions]
    evidence_rows = [runtime.ledger.get_evidence(evidence_id) for evidence_id in desk_response.evidence_refs]
    handoff_targets = {handoff["target_desk"] for handoff in desk_response.handoffs}

    assert ceo_message.role == "ceo"
    assert desk_response.message.role == "desk_agent"
    assert desk_response.message.desk == "reporting"
    assert "Reporting Desk" in desk_response.answer
    assert desk_response.confidence >= 0.6
    assert len(actions) == 3
    assert {action["risk_level"] for action in actions} == {"read_only"}
    assert {action["parameters"]["tool_id"] for action in actions} == {
        "astroq.data.status",
        "astroq.strategy.catalog",
        "astroq.lifecycle.check",
    }
    assert {action["desk"] for action in actions} == {"data", "research", "risk"}
    assert {action["status"] for action in actions} == {"proposed"}
    assert {evidence["kind"] for evidence in evidence_rows} == {"web_route"}
    assert {evidence["uri"] for evidence in evidence_rows} == {"/datahub", "/strategy-lab", "/system?tab=lifecycle"}
    assert handoff_targets >= {"data", "research", "risk"}
    assert loaded["messages"][0]["message_id"] == ceo_message.message_id
    assert loaded["messages"][1]["message_id"] == desk_response.message.message_id
    assert {action["action_id"] for action in loaded["actions"]} >= set(desk_response.proposed_actions)
    assert {handoff["target_desk"] for handoff in loaded["handoffs"]} >= {"data", "research", "risk"}
    reset_datahub()


def test_agent_desk_response_exposes_structured_reasoning_context(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Reasoned CEO review", default_desk="reporting")
    existing_evidence = runtime.create_evidence(
        kind="web_route",
        label="Existing system context",
        uri="/system?tab=lifecycle",
        summary="Existing lifecycle evidence before the CEO asks a new question.",
    )
    runtime.propose_action(
        session_id=session.session_id,
        desk="risk",
        action_type="lifecycle_check",
        risk_level="read_only",
        summary="Existing lifecycle read",
        parameters={"tool_id": "astroq.lifecycle.check"},
        expected_effect="Existing safe read.",
        evidence_refs=[existing_evidence.evidence_id],
    )
    runtime.create_work_order(
        session_id=session.session_id,
        title="Existing data issue",
        summary="Existing work order before the CEO asks a new question.",
        impact="Shows the desk response can cite open work context.",
        evidence_refs=[existing_evidence.evidence_id],
    )

    preview = runtime.preview_workflow_plan(
        desk="reporting",
        content="查数据源 registry diff，策略 OOS IC/ICIR，lifecycle gate 和 execution dry-run",
    )
    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="reporting",
        content="查数据源 registry diff，策略 OOS IC/ICIR，lifecycle gate 和 execution dry-run",
    )
    response = routed["desk_response"]
    reasoning_by_kind = {row["kind"]: row for row in response.reasoning}

    assert preview["reasoning"]
    assert {row["kind"] for row in preview["reasoning"]} >= {"intent_match", "tool_plan", "safety"}
    assert reasoning_by_kind["intent_match"]["planning_mode"] == "dynamic_multi_intent"
    assert reasoning_by_kind["tool_plan"]["tool_count"] >= 4
    assert reasoning_by_kind["safety"]["approval_required_count"] == 0
    assert reasoning_by_kind["session_context"]["open_work_order_count"] >= 1
    assert reasoning_by_kind["session_context"]["active_action_count"] >= 1
    reset_datahub()


def test_agent_follow_up_uses_session_state_for_adaptive_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Adaptive CEO follow-up", default_desk="reporting")
    evidence = runtime.create_evidence(
        kind="web_route",
        label="Existing data repair evidence",
        uri="/datahub",
        summary="Existing Data Desk repair evidence.",
    )
    runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Repair stock_limit_list after CEO approval.",
        parameters={"tool_id": "astroq.data.repair", "table": "stock_limit_list"},
        expected_effect="Writes repaired partitions only after explicit approval.",
        evidence_refs=[evidence.evidence_id],
    )
    source = runtime.add_message(
        session.session_id,
        role="ceo",
        desk="reporting",
        content="已有 Data handoff 需要继续跟进。",
    )
    runtime.respond_as_desk(
        session_id=session.session_id,
        source_message_id=source.message_id,
        desk="reporting",
        answer="需要 Data Desk 跟进。",
        handoffs=[{"target_desk": "data", "reason": "Open data repair handoff."}],
        evidence_refs=[evidence.evidence_id],
    )
    runtime.create_work_order(
        session_id=session.session_id,
        title="Review live risk docs",
        summary="Existing engineering follow-up.",
        impact="Shows adaptive planning can see open Engineering Desk work.",
        affected_files=["broker/live/qmt.py"],
        suggested_verification=["pytest tests/test_agent_os_contracts.py"],
        evidence_refs=[evidence.evidence_id],
    )

    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="reporting",
        content="继续推进这些未完成事项，下一步先做什么？",
    )
    response = routed["desk_response"]
    reasoning_by_kind = {row["kind"]: row for row in response.reasoning}
    actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]
    tool_ids = [action["parameters"]["tool_id"] for action in actions]

    assert reasoning_by_kind["intent_match"]["planning_mode"] == "adaptive_session"
    assert reasoning_by_kind["session_backlog"]["approval_required_count"] >= 1
    assert reasoning_by_kind["session_backlog"]["open_handoff_count"] >= 1
    assert reasoning_by_kind["session_backlog"]["open_work_order_count"] >= 1
    assert set(tool_ids) >= {
        "astroq.data.repair.dry_run",
        "astroq.architecture.ast",
        "astroq.test.design",
    }
    assert all(action["risk_level"] in {"read_only", "dry_run"} for action in actions)
    assert all(action["status"] == "proposed" for action in actions)
    assert any(handoff["target_desk"] == "data" for handoff in response.handoffs)
    assert any(handoff["target_desk"] == "engineering" for handoff in response.handoffs)
    assert "session" in response.answer.lower() or "未完成" in response.answer
    reset_datahub()


def test_agent_cli_and_api_message_return_desk_response(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Message routing", default_desk="reporting")

    cli_code = run_cli(
        [
            "agent",
            "message",
            "--session",
            session.session_id,
            "--desk",
            "reporting",
            "--text",
            "给我一份日常简报",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(
        f"/api/agent/sessions/{session.session_id}/messages",
        json={"role": "ceo", "desk": "data", "content": "检查一下数据缺口"},
    )

    assert cli_code == 0
    assert cli_payload["data"]["message"]["role"] == "ceo"
    assert cli_payload["data"]["desk_response"]["message"]["role"] == "desk_agent"
    assert cli_payload["data"]["desk_response"]["proposed_actions"]
    assert api_res.status_code == 200
    assert api_res.json()["message"]["role"] == "ceo"
    assert api_res.json()["desk_response"]["message"]["desk"] == "data"
    assert api_res.json()["desk_response"]["evidence_refs"]
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

    repair_command = registry.command_for("astroq.data.repair", {"table": "stock_limit_list"}, approved=True)
    assert repair_command[1:] == ["data", "repair", "stock_limit_list", "--json"]
    try:
        registry.command_for("astroq.data.repair", {"table": "x; rm -rf /"}, approved=True)
    except ValueError as exc:
        assert "invalid command parameter" in str(exc)
    else:
        raise AssertionError("unsafe command parameter should not be bound")

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


def test_agent_tool_registry_covers_all_declared_desk_tools():
    from agent_os.desks import list_desks
    from agent_os.tools import AgentToolRegistry

    registry = AgentToolRegistry()

    for desk in list_desks():
        for tool_id in desk["allowed_tools"]:
            tool = registry.get(tool_id)
            assert tool is not None, f"{desk['desk_id']} declares missing tool {tool_id}"
            assert desk["desk_id"] in tool.desk_scopes

    sources_command = registry.command_for("astroq.data.sources")
    diff_command = registry.command_for("astroq.data.sources.diff_registry")
    repair_dry_run = registry.command_for("astroq.data.repair.dry_run", {"table": "stock_limit_list"})
    compete_command = registry.command_for("astroq.strategy.compete")
    backtest_dry_run = registry.command_for("astroq.backtest.run.dry_run")
    test_design_command = registry.command_for("astroq.test.design")
    docs_command = registry.command_for("astroq.docs.check")

    assert sources_command[1:] == ["data", "sources", "--json"]
    assert diff_command[1:] == ["data", "sources", "diff-registry", "--json"]
    assert repair_dry_run[1:] == ["data", "repair", "stock_limit_list", "--dry-run", "--json"]
    assert compete_command[1:] == ["strategy", "compete", "--json"]
    assert backtest_dry_run[1:] == ["backtest", "run", "--dry-run", "--json"]
    assert test_design_command[1:] == ["test", "design", "--json"]
    assert docs_command[1:] == ["docs", "check", "--json"]


def test_agent_desk_workflow_routes_ceo_intent_to_specific_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Desk intent routing")

    data_result = runtime.submit_ceo_message(
        session.session_id,
        desk="data",
        content="检查数据源能力和项目 registry 有哪些差异",
    )
    research_result = runtime.submit_ceo_message(
        session.session_id,
        desk="research",
        content="让12个策略公平竞争，看 OOS 和 IC/ICIR 证据",
    )
    engineering_result = runtime.submit_ceo_message(
        session.session_id,
        desk="engineering",
        content="测试设计是否合理，帮我看 test design 风险",
    )
    docs_result = runtime.submit_ceo_message(
        session.session_id,
        desk="engineering",
        content="文档里有没有旧描述，跑一次 docs check",
    )

    data_action = runtime.get_action(data_result["desk_response"].proposed_actions[0])
    research_action = runtime.get_action(research_result["desk_response"].proposed_actions[0])
    engineering_action = runtime.get_action(engineering_result["desk_response"].proposed_actions[0])
    docs_action = runtime.get_action(docs_result["desk_response"].proposed_actions[0])

    assert data_action["parameters"]["tool_id"] == "astroq.data.sources.diff_registry"
    assert research_action["parameters"]["tool_id"] == "astroq.strategy.compete"
    assert engineering_action["parameters"]["tool_id"] == "astroq.test.design"
    assert docs_action["parameters"]["tool_id"] == "astroq.docs.check"
    assert "source capability" in data_result["desk_response"].answer.lower()
    assert "IC/ICIR" in research_result["desk_response"].answer
    assert "test design" in engineering_result["desk_response"].answer.lower()
    assert "docs check" in docs_result["desk_response"].answer.lower()
    reset_datahub()


def test_agent_workflow_plan_preview_is_side_effect_free_runtime_cli_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    before_summary = runtime.memory_snapshot()["summary"]

    preview = runtime.preview_workflow_plan(
        desk="data",
        content="补一下 stock_limit_list 这张表，先演练再等我审批正式写入",
    )
    after_summary = runtime.memory_snapshot()["summary"]
    cli_code = run_cli(
        [
            "agent",
            "plan",
            "--desk",
            "data",
            "--text",
            "补一下 stock_limit_list 这张表，先演练再等我审批正式写入",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(
        "/api/agent/plans",
        json={"desk": "data", "content": "补一下 stock_limit_list 这张表，先演练再等我审批正式写入"},
    )

    assert before_summary == after_summary
    assert preview["status"] == "ready"
    assert preview["side_effects"]["ledger_writes"] is False
    assert [action["tool_id"] for action in preview["actions"]] == [
        "astroq.data.repair.dry_run",
        "astroq.data.repair",
    ]
    assert [action["status_preview"] for action in preview["actions"]] == ["proposed", "approval_required"]
    assert preview["actions"][1]["approval_required"] is True
    assert preview["actions"][1]["parameters"]["table"] == "stock_limit_list"
    assert cli_code == 0
    assert cli_payload["data"]["plan"]["actions"][1]["status_preview"] == "approval_required"
    assert api_res.status_code == 200
    assert api_res.json()["plan"]["actions"][1]["tool_id"] == "astroq.data.repair"
    reset_datahub()


def test_agent_dynamic_workflow_plan_orchestrates_mixed_ceo_request(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 1},
            "blockers": [{"dimension": "stock_limit_list", "reason": "rate_limited"}],
        },
        "data-sources/latest.json": {
            "summary": {"capability_unmapped_count": 7},
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 6},
        },
        "tests/design/latest.json": {
            "summary": {"design_risk_count": 2},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    before_summary = runtime.memory_snapshot()["summary"]

    preview = runtime.preview_workflow_plan(
        desk="reporting",
        content=(
            "帮我做一次 CEO 复盘：查数据源 registry diff，分析12个策略 OOS 和 IC/ICIR，"
            "看 lifecycle gate，跑 execution dry-run，再检查测试设计风险"
        ),
    )
    after_summary = runtime.memory_snapshot()["summary"]

    assert before_summary == after_summary
    assert preview["status"] == "ready"
    assert preview["planning_mode"] == "dynamic_multi_intent"
    assert preview["side_effects"]["ledger_writes"] is False
    assert [action["tool_id"] for action in preview["actions"]] == [
        "astroq.data.sources.diff_registry",
        "astroq.strategy.compete",
        "astroq.lifecycle.check",
        "astroq.execution.dry_run",
        "astroq.test.design",
    ]
    assert {action["desk"] for action in preview["actions"]} == {
        "data",
        "research",
        "risk",
        "execution",
        "engineering",
    }
    assert len({action["tool_id"] for action in preview["actions"]}) == len(preview["actions"])
    assert {handoff["target_desk"] for handoff in preview["handoffs"]} == {
        "data",
        "research",
        "risk",
        "execution",
        "engineering",
    }
    assert "dynamic" in preview["answer"].lower() or "多意图" in preview["answer"]
    assert "stock_limit_list" in preview["answer"]
    assert "rate_limited" in preview["answer"]
    assert "7" in preview["answer"]
    assert "6/12" in preview["answer"]
    reasoning_by_kind = {row["kind"]: row for row in preview["reasoning"]}
    assert reasoning_by_kind["artifact_context"]["evidence_summary"][:4] == [
        "lifecycle: stock_limit_list rate_limited",
        "data: 7 unmapped source capabilities",
        "research: 6/12 strategies blocked",
        "testing: 2 test design risk(s)",
    ]
    reset_datahub()


def test_agent_workflow_plan_uses_artifact_context_for_broad_ceo_priority_request(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 2, "ready": 4},
            "blockers": [{"dimension": "macro_gdp", "reason": "source_not_updated"}],
        },
        "data-sources/latest.json": {
            "summary": {
                "source_count": 8,
                "capability_count": 300,
                "project_integrated_count": 42,
                "capability_unmapped_count": 21,
            },
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 9, "insufficient_alpha_evidence": 7},
        },
        "architecture/ast/latest.json": {
            "summary": {"issue_count": 2, "severity_counts": {"P1": 1, "P2": 1}},
        },
        "tests/design/latest.json": {
            "summary": {"case_count": 180, "risk_count": 14, "design_risk_count": 3},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Artifact-aware CEO priorities", default_desk="reporting")
    before_summary = runtime.memory_snapshot()["summary"]
    content = "今天公司应该先处理什么？根据当前证据给 Data Research Risk Engineering 安排优先级"

    preview = runtime.preview_workflow_plan(desk="reporting", content=content)
    after_summary = runtime.memory_snapshot()["summary"]
    routed = runtime.submit_ceo_message(session.session_id, desk="reporting", content=content)
    response = routed["desk_response"]
    response_tools = [
        runtime.get_action(action_id)["parameters"]["tool_id"]
        for action_id in response.proposed_actions
    ]
    reasoning_by_kind = {row["kind"]: row for row in response.reasoning}

    assert before_summary == after_summary
    assert preview["planning_mode"] == "artifact_aware"
    assert preview["side_effects"]["ledger_writes"] is False
    assert [action["tool_id"] for action in preview["actions"]] == [
        "astroq.data.sources.diff_registry",
        "astroq.lifecycle.check",
        "astroq.strategy.compete",
        "astroq.architecture.ast",
        "astroq.test.design",
    ]
    assert response_tools == [action["tool_id"] for action in preview["actions"]]
    assert {handoff["target_desk"] for handoff in preview["handoffs"]} == {
        "data",
        "risk",
        "research",
        "engineering",
    }
    assert reasoning_by_kind["intent_match"]["planning_mode"] == "artifact_aware"
    assert reasoning_by_kind["artifact_context"]["root_causes"] == [
        "lifecycle_blocker",
        "data_source_gap",
        "strategy_evidence_blocked",
        "engineering_quality_risk",
        "test_design_risk",
    ]
    assert "macro_gdp" in response.answer
    assert "source_not_updated" in response.answer
    assert "21" in response.answer
    assert "9/12" in response.answer
    assert "P1" in response.answer
    assert reasoning_by_kind["artifact_context"]["evidence_summary"][:4] == [
        "lifecycle: macro_gdp source_not_updated",
        "data: 21 unmapped source capabilities",
        "research: 9/12 strategies blocked",
        "engineering: 2 AST issue(s), P1=1, P2=1",
    ]
    assert reasoning_by_kind["artifact_context"]["missing_count"] >= 1
    assert "artifact" in preview["answer"].lower() or "证据" in preview["answer"]
    reset_datahub()


def test_agent_workflow_plan_combines_artifact_context_with_session_backlog(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 1},
            "blockers": [{"dimension": "risk_free_curve", "reason": "missing_data"}],
        },
        "data-sources/latest.json": {
            "summary": {"capability_unmapped_count": 5, "source_count": 8},
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 4, "insufficient_alpha_evidence": 3},
        },
        "architecture/ast/latest.json": {
            "summary": {"issue_count": 1, "severity_counts": {"P1": 1}},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Hybrid CEO planning", default_desk="reporting")
    evidence = runtime.create_evidence(
        kind="web_route",
        label="Open repair evidence",
        uri="/datahub",
        summary="Existing repair evidence.",
    )
    runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Repair stock_valuation after CEO approval.",
        parameters={"tool_id": "astroq.data.repair", "table": "stock_valuation"},
        expected_effect="Writes repaired partitions only after explicit approval.",
        evidence_refs=[evidence.evidence_id],
    )
    source = runtime.add_message(
        session.session_id,
        role="ceo",
        desk="reporting",
        content="Risk handoff 还没关。",
    )
    runtime.respond_as_desk(
        session_id=session.session_id,
        source_message_id=source.message_id,
        desk="reporting",
        answer="需要 Risk Desk 跟进。",
        handoffs=[{"target_desk": "risk", "reason": "Open risk handoff."}],
        evidence_refs=[evidence.evidence_id],
    )
    runtime.create_work_order(
        session_id=session.session_id,
        title="Close architecture risk",
        summary="Existing engineering work.",
        impact="Should stay visible in hybrid planning.",
        affected_files=["agent_os/workflows.py"],
        suggested_verification=["pytest tests/test_agent_os_contracts.py"],
        evidence_refs=[evidence.evidence_id],
    )

    content = "继续推进当前公司优先级，根据当前证据和未完成事项安排下一步"
    before_summary = runtime.memory_snapshot()["summary"]
    preview = runtime.preview_workflow_plan(desk="reporting", content=content, session_id=session.session_id)
    after_summary = runtime.memory_snapshot()["summary"]
    routed = runtime.submit_ceo_message(session.session_id, desk="reporting", content=content)
    response = routed["desk_response"]
    response_actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]
    preview_tools = [action["tool_id"] for action in preview["actions"]]
    response_tools = [action["parameters"]["tool_id"] for action in response_actions]
    reasoning_by_kind = {row["kind"]: row for row in response.reasoning}

    assert before_summary == after_summary
    assert preview["planning_mode"] == "adaptive_artifact"
    assert preview["side_effects"]["ledger_writes"] is False
    assert preview_tools == response_tools
    assert preview_tools == [
        "astroq.data.repair.dry_run",
        "astroq.lifecycle.check",
        "astroq.architecture.ast",
        "astroq.test.design",
        "astroq.data.sources.diff_registry",
        "astroq.strategy.compete",
    ]
    assert "risk_free_curve" in response.answer
    assert "missing_data" in response.answer
    assert "5" in response.answer
    assert "4/12" in response.answer
    assert "P1" in response.answer
    assert reasoning_by_kind["intent_match"]["planning_mode"] == "adaptive_artifact"
    assert reasoning_by_kind["session_backlog"]["approval_required_count"] >= 1
    assert reasoning_by_kind["artifact_context"]["root_causes"] == [
        "lifecycle_blocker",
        "data_source_gap",
        "strategy_evidence_blocked",
        "engineering_quality_risk",
    ]
    assert reasoning_by_kind["artifact_context"]["evidence_summary"][:4] == [
        "lifecycle: risk_free_curve missing_data",
        "data: 5 unmapped source capabilities",
        "research: 4/12 strategies blocked",
        "engineering: 1 AST issue(s), P1=1",
    ]
    assert reasoning_by_kind["context_fusion"]["source_count"] == 2
    assert all(action["risk_level"] in {"read_only", "dry_run"} for action in response_actions)
    assert any(handoff["target_desk"] == "data" for handoff in response.handoffs)
    assert any(handoff["target_desk"] == "risk" for handoff in response.handoffs)
    reset_datahub()


def test_agent_open_ended_ceo_request_gets_safe_company_wide_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 1},
            "blockers": [{"dimension": "risk_free_curve", "reason": "missing_data"}],
        },
        "data-sources/latest.json": {
            "summary": {"capability_count": 120, "project_integrated_count": 40, "capability_unmapped_count": 12},
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 5},
        },
        "tests/design/latest.json": {
            "summary": {"design_risk_count": 2},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Open ended CEO planning", default_desk="reporting")
    content = "现在公司整体往前推进一下，判断每个 desk 该先查什么，先别直接改数据也不要交易"

    preview = runtime.preview_workflow_plan(desk="reporting", content=content, session_id=session.session_id)
    routed = runtime.submit_ceo_message(session.session_id, desk="reporting", content=content)
    response = routed["desk_response"]
    response_actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]
    preview_tools = [action["tool_id"] for action in preview["actions"]]
    response_tools = [action["parameters"]["tool_id"] for action in response_actions]
    reasoning_by_kind = {row["kind"]: row for row in response.reasoning}

    assert preview["planning_mode"] == "open_ended_adaptive"
    assert preview["side_effects"]["ledger_writes"] is False
    assert preview_tools == response_tools
    assert preview_tools == [
        "astroq.data.status",
        "astroq.strategy.catalog",
        "astroq.lifecycle.check",
        "astroq.execution.dry_run",
        "astroq.architecture.ast",
        "astroq.test.design",
    ]
    assert {handoff["target_desk"] for handoff in preview["handoffs"]} == {
        "data",
        "research",
        "risk",
        "execution",
        "engineering",
    }
    assert reasoning_by_kind["intent_match"]["planning_mode"] == "open_ended_adaptive"
    assert reasoning_by_kind["open_goal_decomposition"]["target_desks"] == [
        "data",
        "research",
        "risk",
        "execution",
        "engineering",
    ]
    assert reasoning_by_kind["safety"]["approval_required_count"] == 0
    assert all(action["risk_level"] in {"read_only", "dry_run"} for action in response_actions)
    assert response.blockers == ["open_ended_plan_is_diagnostic_only"]
    assert "risk_free_curve" in response.answer
    assert "missing_data" in response.answer
    assert "12" in response.answer
    assert "5/12" in response.answer
    assert "2 test design" in response.answer
    assert reasoning_by_kind["artifact_context"]["evidence_summary"][:4] == [
        "lifecycle: risk_free_curve missing_data",
        "data: 12 unmapped source capabilities",
        "research: 5/12 strategies blocked",
        "testing: 2 test design risk(s)",
    ]
    reset_datahub()


def test_agent_semantic_planner_is_opt_in_and_filtered_to_safe_known_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from agent_os.workflows import SemanticWorkflowDraft

    captured: list[dict[str, object]] = []

    class FakeSemanticPlanner:
        def plan(self, *, desk: str, content: str, artifact_context: dict, session_context: dict) -> SemanticWorkflowDraft:
            captured.append(
                {
                    "desk": desk,
                    "content": content,
                    "artifact_context_seen": bool(artifact_context),
                    "session_context_seen": bool(session_context),
                }
            )
            return SemanticWorkflowDraft(
                answer="Semantic planner proposed a CEO review plan.",
                confidence=0.91,
                actions=[
                    {
                        "desk": "data",
                        "tool_id": "astroq.data.status",
                        "summary": "Refresh data readiness for ambiguous CEO request.",
                        "parameters": {"tool_id": "astroq.data.repair"},
                    },
                    {
                        "desk": "data",
                        "tool_id": "astroq.data.repair",
                        "summary": "Unsafe write should be filtered.",
                    },
                    {
                        "desk": "execution",
                        "tool_id": "astroq.agent.live.submit",
                        "summary": "Unknown live submit should be filtered.",
                    },
                    {
                        "desk": "engineering",
                        "tool_id": "astroq.architecture.ast",
                        "summary": "Refresh architecture diagnostics.",
                    },
                ],
                reasoning=[{"kind": "semantic_goal", "goal": "ambiguous_cross_desk_review"}],
            )

    runtime = AgentRuntime()
    session = runtime.create_session(title="Semantic planner safety", default_desk="reporting")
    deterministic = runtime.preview_workflow_plan(
        desk="reporting",
        content="请从经营质量角度理解这段模糊要求，但先不要写数据也不要交易",
        session_id=session.session_id,
    )

    assert deterministic["planning_mode"] != "semantic_assisted"
    assert captured == []

    semantic = runtime.preview_workflow_plan(
        desk="reporting",
        content="请从经营质量角度理解这段模糊要求，但先不要写数据也不要交易",
        session_id=session.session_id,
        semantic_planner=FakeSemanticPlanner(),
    )
    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="reporting",
        content="请从经营质量角度理解这段模糊要求，但先不要写数据也不要交易",
        semantic_planner=FakeSemanticPlanner(),
    )
    response = routed["desk_response"]
    response_actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]

    assert captured
    assert semantic["planning_mode"] == "semantic_assisted"
    assert semantic["side_effects"]["ledger_writes"] is False
    assert [action["tool_id"] for action in semantic["actions"]] == [
        "astroq.data.status",
        "astroq.architecture.ast",
    ]
    assert semantic["actions"][0]["parameters"]["tool_id"] == "astroq.data.status"
    assert all(action["risk_level"] in {"read_only", "dry_run"} for action in semantic["actions"])
    assert "semantic_plan_requires_manual_review" in semantic["blockers"]
    assert "unsafe_semantic_actions_filtered" in semantic["blockers"]
    reasoning_by_kind = {row["kind"]: row for row in semantic["reasoning"]}
    assert reasoning_by_kind["semantic_planner"]["accepted_action_count"] == 2
    assert reasoning_by_kind["semantic_planner"]["rejected_action_count"] == 2
    assert [action["parameters"]["tool_id"] for action in response_actions] == [
        "astroq.data.status",
        "astroq.architecture.ast",
    ]
    assert all(action["risk_level"] in {"read_only", "dry_run"} for action in response_actions)
    assert response.blockers == semantic["blockers"]
    reset_datahub()


def test_agent_semantic_planner_infers_single_scope_desk_but_rejects_ambiguous_missing_desk(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from agent_os.workflows import SemanticWorkflowDraft

    class DesklessSemanticPlanner:
        def plan(self, *, desk: str, content: str, artifact_context: dict, session_context: dict) -> SemanticWorkflowDraft:
            return SemanticWorkflowDraft(
                answer="Deskless semantic plan should keep unambiguous safe diagnostics only.",
                confidence=0.8,
                actions=[
                    {
                        "tool_id": "astroq.architecture.ast",
                        "summary": "Inspect architecture duplicate implementation risks.",
                    },
                    {
                        "tool_id": "astroq.lifecycle.check",
                        "summary": "Ambiguous deskless lifecycle check should be rejected.",
                    },
                ],
            )

    preview = AgentRuntime().preview_workflow_plan(
        desk="reporting",
        content="请做一次安全诊断，但 planner 没给 desk 字段",
        semantic_planner=DesklessSemanticPlanner(),
    )
    reasoning_by_kind = {row["kind"]: row for row in preview["reasoning"]}

    assert preview["planning_mode"] == "semantic_assisted"
    assert [(action["desk"], action["tool_id"]) for action in preview["actions"]] == [
        ("engineering", "astroq.architecture.ast")
    ]
    assert "unsafe_semantic_actions_filtered" in preview["blockers"]
    assert reasoning_by_kind["semantic_planner"]["accepted_action_count"] == 1
    assert reasoning_by_kind["semantic_planner"]["rejected"] == [
        {"tool_id": "astroq.lifecycle.check", "desk": "", "reason": "missing_or_ambiguous_desk"}
    ]
    reset_datahub()


def test_agent_semantic_planner_rejects_invalid_fixed_tool_parameters(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from agent_os.workflows import SemanticWorkflowDraft

    class ParameterSemanticPlanner:
        def plan(self, *, desk: str, content: str, artifact_context: dict, session_context: dict) -> SemanticWorkflowDraft:
            return SemanticWorkflowDraft(
                answer="Semantic planner proposed repair dry-runs with mixed parameter quality.",
                confidence=0.83,
                actions=[
                    {
                        "desk": "data",
                        "tool_id": "astroq.data.repair.dry_run",
                        "summary": "Valid dry-run repair preview.",
                        "parameters": {"table": "stock_limit_list", "extra": "ignored"},
                    },
                    {
                        "desk": "data",
                        "tool_id": "astroq.data.repair.dry_run",
                        "summary": "Invalid table name must be rejected.",
                        "parameters": {"table": "stock-limit;rm"},
                    },
                    {
                        "desk": "data",
                        "tool_id": "astroq.data.repair.dry_run",
                        "summary": "Missing table parameter must be rejected.",
                    },
                ],
            )

    preview = AgentRuntime().preview_workflow_plan(
        desk="reporting",
        content="planner 需要提出补数据 dry-run，但参数必须走 fixed registry 校验",
        semantic_planner=ParameterSemanticPlanner(),
    )
    reasoning_by_kind = {row["kind"]: row for row in preview["reasoning"]}

    assert preview["planning_mode"] == "semantic_assisted"
    assert len(preview["actions"]) == 1
    assert preview["actions"][0]["tool_id"] == "astroq.data.repair.dry_run"
    assert preview["actions"][0]["parameters"] == {
        "table": "stock_limit_list",
        "tool_id": "astroq.data.repair.dry_run",
    }
    assert reasoning_by_kind["semantic_planner"]["accepted_action_count"] == 1
    assert reasoning_by_kind["semantic_planner"]["rejected"] == [
        {"tool_id": "astroq.data.repair.dry_run", "desk": "data", "reason": "invalid_tool_parameter:table"},
        {"tool_id": "astroq.data.repair.dry_run", "desk": "data", "reason": "missing_tool_parameter:table"},
    ]
    reset_datahub()


def test_agent_semantic_draft_malformed_metadata_returns_blocked_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from agent_os.semantic_planner import SemanticDraftPlanner

    malformed_draft = {
        "answer": "Malformed metadata should not crash the semantic planning path.",
        "confidence": "certain",
        "actions": {
            "desk": "engineering",
            "tool_id": "astroq.test.design",
            "summary": "A single action object should still be filtered safely.",
        },
        "blockers": "external_planner_untrusted",
        "reasoning": {"kind": "semantic_goal", "goal": "metadata_resilience"},
    }

    preview = AgentRuntime().preview_workflow_plan(
        desk="reporting",
        content="外部 planner 元数据格式不稳定时也不能让系统崩溃",
        semantic_planner=SemanticDraftPlanner(malformed_draft),
    )
    reasoning_by_kind = {row["kind"]: row for row in preview["reasoning"]}

    assert preview["planning_mode"] == "semantic_assisted"
    assert preview["confidence"] == 0.5
    assert [(action["desk"], action["tool_id"]) for action in preview["actions"]] == [
        ("engineering", "astroq.test.design")
    ]
    assert preview["blockers"] == [
        "external_planner_untrusted",
        "semantic_draft_invalid_confidence",
        "semantic_plan_requires_manual_review",
    ]
    assert reasoning_by_kind["semantic_planner"]["accepted_action_count"] == 1
    assert reasoning_by_kind["semantic_goal"]["goal"] == "metadata_resilience"
    reset_datahub()


def test_agent_semantic_draft_plan_api_cli_and_message_intake_are_filtered(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    semantic_draft = {
        "answer": "Drafted a cross-desk CEO plan from an external planner.",
        "confidence": 0.88,
        "actions": [
            {
                "desk": "data",
                "tool_id": "astroq.data.status",
                "summary": "Inspect current data readiness.",
                "parameters": {"tool_id": "astroq.data.repair", "table": "stock_limit_list"},
            },
            {
                "desk": "data",
                "tool_id": "astroq.data.repair",
                "summary": "Unsafe write repair must be filtered.",
                "parameters": {"table": "stock_limit_list"},
            },
            {
                "desk": "execution",
                "tool_id": "astroq.agent.live.submit",
                "summary": "Unknown live submit must be filtered.",
            },
            {
                "desk": "engineering",
                "tool_id": "astroq.test.design",
                "summary": "Inspect test design risks.",
            },
        ],
        "reasoning": [{"kind": "semantic_goal", "goal": "cross_desk_review"}],
        "blockers": ["external_planner_untrusted"],
    }
    draft_path = tmp_path / "semantic-draft.json"
    draft_path.write_text(json.dumps(semantic_draft, ensure_ascii=False), encoding="utf-8")

    runtime = AgentRuntime()
    session = runtime.create_session(title="External semantic draft", default_desk="reporting")
    client = TestClient(create_app())
    before_summary = runtime.memory_snapshot()["summary"]

    api_res = client.post(
        "/api/agent/plans",
        json={
            "desk": "reporting",
            "content": "按这个外部 planner 草案做一次安全预览",
            "planner_mode": "semantic_draft",
            "semantic_draft": semantic_draft,
        },
    )
    after_summary = runtime.memory_snapshot()["summary"]
    cli_code = run_cli(
        [
            "agent",
            "plan",
            "--desk",
            "reporting",
            "--text",
            "按这个外部 planner 草案做一次安全预览",
            "--semantic-draft-file",
            str(draft_path),
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    assert before_summary == after_summary
    assert runtime.ledger.list_evidence() == []
    assert api_res.status_code == 200
    api_plan = api_res.json()["plan"]
    assert api_plan["planning_mode"] == "semantic_assisted"
    assert api_plan["side_effects"]["ledger_writes"] is False
    assert [action["tool_id"] for action in api_plan["actions"]] == [
        "astroq.data.status",
        "astroq.test.design",
    ]
    assert api_plan["actions"][0]["parameters"]["tool_id"] == "astroq.data.status"
    assert "table" not in api_plan["actions"][0]["parameters"]
    assert api_plan["blockers"] == [
        "external_planner_untrusted",
        "semantic_plan_requires_manual_review",
        "unsafe_semantic_actions_filtered",
    ]
    semantic_reasoning = {row["kind"]: row for row in api_plan["reasoning"]}["semantic_planner"]
    assert semantic_reasoning["accepted_action_count"] == 2
    assert semantic_reasoning["rejected_action_count"] == 2

    assert cli_code == 0
    assert cli_payload["data"]["plan"]["planning_mode"] == "semantic_assisted"
    assert [action["tool_id"] for action in cli_payload["data"]["plan"]["actions"]] == [
        "astroq.data.status",
        "astroq.test.design",
    ]

    message_res = client.post(
        f"/api/agent/sessions/{session.session_id}/messages",
        json={
            "role": "ceo",
            "desk": "reporting",
            "content": "按这个外部 planner 草案创建安全行动卡",
            "planner_mode": "semantic_draft",
            "semantic_draft": semantic_draft,
        },
    )

    assert message_res.status_code == 200
    response = message_res.json()["desk_response"]
    assert response["blockers"] == api_plan["blockers"]
    persisted_actions = [runtime.get_action(action_id) for action_id in response["proposed_actions"]]
    assert [action["parameters"]["tool_id"] for action in persisted_actions] == [
        "astroq.data.status",
        "astroq.test.design",
    ]
    assert all("table" not in action["parameters"] for action in persisted_actions)
    assert all(action["risk_level"] == "read_only" for action in persisted_actions)
    response_evidence = [runtime.ledger.get_evidence(evidence_id) for evidence_id in response["evidence_refs"]]
    audit_evidence = [row for row in response_evidence if row and row["label"] == "Semantic planner audit"]
    assert len(audit_evidence) == 1
    audit_path = Path(audit_evidence[0]["uri"])
    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_evidence[0]["kind"] == "artifact"
    assert Path(audit_evidence[0]["snapshot_uri"]).exists()
    assert audit_payload["planning_mode"] == "semantic_assisted"
    assert audit_payload["desk"] == "reporting"
    assert audit_payload["accepted_action_count"] == 2
    assert audit_payload["rejected_action_count"] == 2
    assert audit_payload["blockers"] == api_plan["blockers"]
    assert "api_key" not in json.dumps(audit_payload, ensure_ascii=False)
    reset_datahub()


def test_agent_provider_semantic_planner_fails_closed_without_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from agent_os.semantic_planner import ProviderSemanticPlanner

    def forbidden_transport(*_args, **_kwargs):
        raise AssertionError("provider planner must not call transport without a secret")

    runtime = AgentRuntime()
    before_summary = runtime.memory_snapshot()["summary"]
    preview = runtime.preview_workflow_plan(
        desk="reporting",
        content="请用 provider planner 理解当前公司优先级",
        semantic_planner=ProviderSemanticPlanner(transport=forbidden_transport),
    )
    after_summary = runtime.memory_snapshot()["summary"]
    reasoning_by_kind = {row["kind"]: row for row in preview["reasoning"]}

    assert before_summary == after_summary
    assert preview["planning_mode"] == "semantic_assisted"
    assert preview["actions"] == []
    assert preview["side_effects"]["ledger_writes"] is False
    assert "semantic_provider_missing_secret" in preview["blockers"]
    assert reasoning_by_kind["semantic_planner"]["accepted_action_count"] == 0
    assert reasoning_by_kind["semantic_provider"]["status"] == "missing_secret"
    assert reasoning_by_kind["semantic_provider"]["credential_env"] == "DEEPSEEK_API_KEY"
    reset_datahub()


def test_agent_provider_semantic_planner_fails_closed_when_provider_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "disabled-provider-secret")
    from data.storage.datahub import reset_datahub
    import data.llm.usage as llm_usage

    reset_datahub()

    monkeypatch.setattr(
        llm_usage,
        "get_settings",
        lambda: {
            "llm": {
                "default_provider": "deepseek",
                "use_cases": {"agent_planning": {"provider": "deepseek", "model": "deepseek-v4-pro"}},
                "providers": {
                    "deepseek": {
                        "enabled": False,
                        "api_key_env": "DEEPSEEK_API_KEY",
                        "base_url": "https://api.deepseek.com/v1",
                        "pricing": {"models": {"deepseek-v4-pro": {"total": 1.0}}},
                    }
                },
            }
        },
    )

    from agent_os.runtime import AgentRuntime
    from agent_os.semantic_planner import ProviderSemanticPlanner

    def forbidden_transport(*_args, **_kwargs):
        raise AssertionError("disabled provider planner must not call transport")

    preview = AgentRuntime().preview_workflow_plan(
        desk="reporting",
        content="provider disabled 时不能调用模型",
        semantic_planner=ProviderSemanticPlanner(transport=forbidden_transport),
    )
    reasoning_by_kind = {row["kind"]: row for row in preview["reasoning"]}

    assert preview["planning_mode"] == "semantic_assisted"
    assert preview["actions"] == []
    assert "semantic_provider_disabled" in preview["blockers"]
    assert reasoning_by_kind["semantic_provider"]["status"] == "disabled"
    assert reasoning_by_kind["semantic_provider"]["provider"] == "deepseek"
    reset_datahub()


def test_agent_provider_semantic_planner_uses_transport_then_filters_safe_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "semantic-secret")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from agent_os.semantic_planner import ProviderSemanticPlanner
    from data.storage.datahub import get_datahub

    calls: list[dict[str, object]] = []

    def fake_transport(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        assert request["api_key"] == "semantic-secret"
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "Provider drafted a safe evidence plan.",
                                "confidence": 0.82,
                                "actions": [
                                    {
                                        "desk": "data",
                                        "tool_id": "astroq.data.status",
                                        "summary": "Inspect data health.",
                                    },
                                    {
                                        "desk": "data",
                                        "tool_id": "astroq.data.repair",
                                        "summary": "Unsafe write must be filtered.",
                                        "parameters": {"table": "stock_limit_list"},
                                    },
                                    {
                                        "desk": "risk",
                                        "tool_id": "astroq.lifecycle.check",
                                        "summary": "Inspect lifecycle blockers.",
                                    },
                                ],
                                "reasoning": [{"kind": "provider_goal", "goal": "company_priority"}],
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    runtime = AgentRuntime()
    preview = runtime.preview_workflow_plan(
        desk="reporting",
        content="请用 provider planner 判断公司优先级",
        semantic_planner=ProviderSemanticPlanner(transport=fake_transport),
    )
    reasoning_by_kind = {row["kind"]: row for row in preview["reasoning"]}

    assert calls
    assert calls[0]["use_case"] == "agent_planning"
    assert "allowed_tools" in calls[0]
    assert "api_key" not in reasoning_by_kind["semantic_provider"]
    assert preview["planning_mode"] == "semantic_assisted"
    assert [action["tool_id"] for action in preview["actions"]] == [
        "astroq.data.status",
        "astroq.lifecycle.check",
    ]
    assert preview["blockers"] == [
        "semantic_plan_requires_manual_review",
        "unsafe_semantic_actions_filtered",
    ]
    assert reasoning_by_kind["semantic_provider"]["status"] == "ok"
    assert reasoning_by_kind["semantic_provider"]["provider"] == "deepseek"
    assert reasoning_by_kind["semantic_provider"]["usage"]["total_tokens"] == 30
    assert reasoning_by_kind["semantic_planner"]["accepted_action_count"] == 2
    assert reasoning_by_kind["semantic_planner"]["rejected_action_count"] == 1
    usage_path = get_datahub().llm_project_usage_path()
    assert usage_path.exists()
    usage_rows = get_datahub().read_parquet(usage_path).to_dict(orient="records")
    assert len(usage_rows) == 1
    usage_row = usage_rows[0]
    assert usage_row["source"] == "agent_planning"
    assert usage_row["provider"] == "deepseek"
    assert usage_row["model"] == "deepseek-v4-pro"
    assert usage_row["total_tokens"] == 30
    assert usage_row["request_id"] == ""
    assert "semantic-secret" not in json.dumps(usage_rows, ensure_ascii=False)
    reset_datahub()


def test_agent_provider_semantic_planner_redacts_secret_like_context_before_transport(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "provider-secret")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.semantic_planner import ProviderSemanticPlanner

    captured_messages: list[dict[str, str]] = []

    def fake_transport(request: dict[str, object]) -> dict[str, object]:
        captured_messages.extend(request["messages"])  # type: ignore[arg-type]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "Provider received redacted context.",
                                "confidence": 0.7,
                                "actions": [],
                                "reasoning": [{"kind": "provider_goal", "goal": "redaction"}],
                            }
                        )
                    }
                }
            ],
            "usage": {"total_tokens": 1},
        }

    draft = ProviderSemanticPlanner(transport=fake_transport).plan(
        desk="reporting",
        content="请根据本地上下文做安全规划",
        artifact_context={
            "api_key": "artifact-secret",
            "nested": {"authorization": "Bearer artifact-auth-secret"},
            "items": [{"token": "artifact-token-secret"}],
            "safe_status": "blocked",
        },
        session_context={
            "active_actions": [
                {
                    "parameters": {
                        "password": "broker-password-secret",
                        "table": "stock_limit_list",
                    }
                }
            ],
            "credential_env": "DEEPSEEK_API_KEY",
        },
    )
    messages_text = json.dumps(captured_messages, ensure_ascii=False)

    assert draft["answer"] == "Provider received redacted context."
    assert "artifact-secret" not in messages_text
    assert "artifact-auth-secret" not in messages_text
    assert "artifact-token-secret" not in messages_text
    assert "broker-password-secret" not in messages_text
    assert "provider-secret" not in messages_text
    assert "stock_limit_list" in messages_text
    assert "safe_status" in messages_text
    assert "***REDACTED***" in messages_text
    reset_datahub()


def test_agent_provider_semantic_planner_api_and_cli_are_explicit_opt_in(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from astrolabe_cli.main import run_cli
    from web.api.app import create_app
    import agent_os.semantic_planner as semantic_planner

    cli_code = run_cli(
        [
            "agent",
            "plan",
            "--desk",
            "reporting",
            "--text",
            "请用 provider semantic planner 判断公司优先级",
            "--provider-semantic",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)

    assert cli_code == 0
    assert cli_payload["data"]["plan"]["planning_mode"] == "semantic_assisted"
    assert cli_payload["data"]["plan"]["actions"] == []
    assert "semantic_provider_missing_secret" in cli_payload["data"]["plan"]["blockers"]

    monkeypatch.setenv("DEEPSEEK_API_KEY", "api-semantic-secret")

    def fake_transport(request: dict[str, object]) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "API provider plan.",
                                "confidence": 0.77,
                                "actions": [
                                    {"desk": "data", "tool_id": "astroq.data.status"},
                                    {"desk": "data", "tool_id": "astroq.data.repair", "parameters": {"table": "daily"}},
                                ],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(semantic_planner, "_openai_compatible_chat_completion", fake_transport)
    api_res = TestClient(create_app()).post(
        "/api/agent/plans",
        json={
            "desk": "reporting",
            "content": "请用 provider semantic planner 判断公司优先级",
            "planner_mode": "provider_semantic",
        },
    )
    api_plan = api_res.json()["plan"]

    assert api_res.status_code == 200
    assert api_plan["planning_mode"] == "semantic_assisted"
    assert [action["tool_id"] for action in api_plan["actions"]] == ["astroq.data.status"]
    assert api_plan["blockers"] == [
        "semantic_plan_requires_manual_review",
        "unsafe_semantic_actions_filtered",
    ]
    reset_datahub()


def test_data_repair_request_proposes_dry_run_and_approval_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Data repair workflow", default_desk="data")

    result = runtime.submit_ceo_message(
        session.session_id,
        desk="data",
        content="补一下 stock_limit_list 这张表，先演练再等我审批正式写入",
    )
    response = result["desk_response"]
    actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]
    by_tool = {action["parameters"]["tool_id"]: action for action in actions}

    assert len(actions) == 2
    assert set(by_tool) == {"astroq.data.repair.dry_run", "astroq.data.repair"}
    assert by_tool["astroq.data.repair.dry_run"]["risk_level"] == "dry_run"
    assert by_tool["astroq.data.repair.dry_run"]["status"] == "proposed"
    assert by_tool["astroq.data.repair.dry_run"]["parameters"]["table"] == "stock_limit_list"
    assert by_tool["astroq.data.repair"]["risk_level"] == "write_data"
    assert by_tool["astroq.data.repair"]["status"] == "approval_required"
    assert by_tool["astroq.data.repair"]["approval_required"] is True
    assert by_tool["astroq.data.repair"]["parameters"]["table"] == "stock_limit_list"
    assert "dry-run" in response.answer.lower() or "演练" in response.answer
    assert len(response.evidence_refs) == 2
    reset_datahub()


def test_safe_workflow_runs_data_repair_dry_run_and_skips_write_action(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Safe data repair workflow", default_desk="data")
    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="data",
        content="请补 stock_limit_list 数据，先 dry-run，再生成需要 CEO 审批的写入动作",
    )

    result = runtime.run_session_read_only_actions(session.session_id, runner=fake_run)
    actions = [runtime.get_action(action_id) for action_id in routed["desk_response"].proposed_actions]
    by_tool = {action["parameters"]["tool_id"]: action for action in actions}

    assert result["status"] == "ready"
    assert result["run_count"] == 1
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["reason"] == "not_safe_workflow_action"
    assert calls[0][1:] == ["data", "repair", "stock_limit_list", "--dry-run", "--json"]
    assert by_tool["astroq.data.repair.dry_run"]["status"] == "succeeded"
    assert by_tool["astroq.data.repair"]["status"] == "approval_required"
    reset_datahub()


def test_research_strategy_blocker_review_orchestrates_research_data_risk_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 2},
            "blockers": [{"dimension": "daily_raw", "reason": "stale"}],
        },
        "data-sources/latest.json": {
            "summary": {"capability_unmapped_count": 9},
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 12, "insufficient_alpha_evidence": 8},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Strategy blocker diagnosis", default_desk="research")

    result = runtime.submit_ceo_message(
        session.session_id,
        desk="research",
        content="为什么12个策略都被阻断，是缺数据、缺 IC/ICIR，还是 lifecycle gate 的问题？",
    )
    response = result["desk_response"]
    actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]

    assert len(actions) == 3
    assert {action["desk"] for action in actions} == {"research", "data", "risk"}
    assert {action["parameters"]["tool_id"] for action in actions} == {
        "astroq.strategy.compete",
        "astroq.data.status",
        "astroq.lifecycle.check",
    }
    assert all(action["risk_level"] == "read_only" for action in actions)
    assert len(response.evidence_refs) == 3
    assert {handoff["target_desk"] for handoff in response.handoffs} == {"data", "risk"}
    assert "blocked" in response.answer.lower() or "阻断" in response.answer
    assert "daily_raw" in response.answer
    assert "stale" in response.answer
    assert "9" in response.answer
    assert "12/12" in response.answer
    reasoning_by_kind = {row["kind"]: row for row in response.reasoning}
    assert reasoning_by_kind["artifact_context"]["evidence_summary"][:3] == [
        "lifecycle: daily_raw stale",
        "data: 9 unmapped source capabilities",
        "research: 12/12 strategies blocked",
    ]
    reset_datahub()


def test_safe_workflow_runs_strategy_blocker_review_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Strategy blocker safe workflow", default_desk="research")
    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="research",
        content="为什么策略全被 blocked，帮我同时看 data coverage、strategy evidence 和 lifecycle",
    )

    result = runtime.run_session_read_only_actions(session.session_id, runner=fake_run)

    assert result["status"] == "ready"
    assert result["run_count"] == 3
    assert result["skipped_count"] == 0
    assert {run["action_id"] for run in result["runs"]} == set(routed["desk_response"].proposed_actions)
    assert {tuple(command[1:]) for command in calls} == {
        ("strategy", "compete", "--json"),
        ("data", "status", "--json"),
        ("lifecycle", "check", "--json"),
    }
    reset_datahub()


def test_reporting_daily_brief_orchestrates_multiple_desk_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    hub = get_datahub()
    artifact_root = hub.artifact_dir("lifecycle").parent
    payloads = {
        "lifecycle/latest.json": {
            "status": "blocked",
            "summary": {"blocked": 1},
            "blockers": [{"dimension": "macro_gdp", "reason": "source_not_updated"}],
        },
        "data-sources/latest.json": {
            "summary": {"capability_count": 300, "project_integrated_count": 42, "capability_unmapped_count": 21},
        },
        "tournaments/strategy_competition_latest.json": {
            "summary": {"total": 12, "blocked": 9},
        },
    }
    for relative, payload in payloads.items():
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Daily operating rhythm")

    result = runtime.submit_ceo_message(
        session.session_id,
        desk="reporting",
        content="今天系统该做什么，给我 CEO 简报",
    )
    response = result["desk_response"]
    actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]

    assert len(actions) == 3
    assert {action["desk"] for action in actions} == {"data", "research", "risk"}
    assert {action["parameters"]["tool_id"] for action in actions} == {
        "astroq.data.status",
        "astroq.strategy.catalog",
        "astroq.lifecycle.check",
    }
    assert all(action["risk_level"] == "read_only" for action in actions)
    assert len(response.evidence_refs) == 3
    assert {handoff["target_desk"] for handoff in response.handoffs} == {"data", "research", "risk"}
    assert "daily" in response.answer.lower() or "简报" in response.answer
    assert "macro_gdp" in response.answer
    assert "source_not_updated" in response.answer
    assert "21" in response.answer
    assert "9/12" in response.answer
    reasoning_by_kind = {row["kind"]: row for row in response.reasoning}
    assert reasoning_by_kind["artifact_context"]["evidence_summary"][:3] == [
        "lifecycle: macro_gdp source_not_updated",
        "data: 21 unmapped source capabilities",
        "research: 9/12 strategies blocked",
    ]
    reset_datahub()


def test_reporting_portfolio_review_orchestrates_research_risk_execution_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Portfolio operating review")

    result = runtime.submit_ceo_message(
        session.session_id,
        desk="reporting",
        content="帮我做一次组合风险和执行复盘，看看策略证据、生命周期门禁和执行 dry-run",
    )
    response = result["desk_response"]
    actions = [runtime.get_action(action_id) for action_id in response.proposed_actions]

    assert len(actions) == 3
    assert {action["desk"] for action in actions} == {"research", "risk", "execution"}
    assert {action["parameters"]["tool_id"] for action in actions} == {
        "astroq.strategy.compete",
        "astroq.lifecycle.check",
        "astroq.execution.dry_run",
    }
    assert {action["risk_level"] for action in actions} == {"read_only", "dry_run"}
    assert len(response.evidence_refs) == 3
    assert {handoff["target_desk"] for handoff in response.handoffs} == {"research", "risk", "execution"}
    assert "portfolio" in response.answer.lower() or "组合" in response.answer
    reset_datahub()


def test_agent_runtime_runs_safe_portfolio_review_workflow_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Portfolio safe workflow")
    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="reporting",
        content="组合风险和执行复盘，需要 strategy evidence、lifecycle 和 execution dry-run",
    )

    result = runtime.run_session_read_only_actions(session.session_id, runner=fake_run)

    assert result["status"] == "ready"
    assert result["run_count"] == 3
    assert result["skipped_count"] == 0
    assert {run["status"] for run in result["runs"]} == {"succeeded"}
    assert {run["action_id"] for run in result["runs"]} == set(routed["desk_response"].proposed_actions)
    assert {tuple(command[1:]) for command in calls} == {
        ("strategy", "compete", "--json"),
        ("lifecycle", "check", "--json"),
        ("execution", "dry-run", "--json"),
    }
    reset_datahub()


def test_agent_runtime_runs_session_read_only_workflow_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Daily readonly workflow")
    routed = runtime.submit_ceo_message(
        session.session_id,
        desk="reporting",
        content="今天系统该做什么，给我 CEO 简报",
    )
    write_action = runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Repair data",
        parameters={"tool_id": "astroq.data.repair", "table": "stock_limit_list"},
    )

    result = runtime.run_session_read_only_actions(session.session_id, runner=fake_run)

    assert result["status"] == "ready"
    assert result["session_id"] == session.session_id
    assert result["action_count"] == 4
    assert result["run_count"] == 3
    assert result["succeeded_count"] == 3
    assert result["failed_count"] == 0
    assert result["blocked_count"] == 0
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["action_id"] == write_action.action_id
    assert result["skipped"][0]["reason"] == "not_safe_workflow_action"
    assert {run["status"] for run in result["runs"]} == {"succeeded"}
    assert {run["action_id"] for run in result["runs"]} == set(routed["desk_response"].proposed_actions)
    assert len(calls) == 3
    assert {tuple(command[1:]) for command in calls} == {
        ("data", "status", "--json"),
        ("strategy", "catalog", "--json"),
        ("lifecycle", "check", "--json"),
    }
    assert runtime.get_action(write_action.action_id)["status"] == "approval_required"
    assert {runtime.get_action(action_id)["status"] for action_id in routed["desk_response"].proposed_actions} == {"succeeded"}
    reset_datahub()


def test_agent_dispatch_binds_approved_templated_tool_parameters(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Dispatch data repair")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="data",
        action_type="data_repair",
        risk_level="write_data",
        summary="Repair one safe table",
        parameters={"tool_id": "astroq.data.repair", "table": "stock_limit_list"},
    )
    blocked = runtime.dispatch_action(action.action_id, runner=fake_run)
    approved = runtime.approve_action(action.action_id)
    run = runtime.dispatch_action(action.action_id, runner=fake_run)

    assert blocked.status == "blocked"
    assert "approval required" in blocked.stderr_summary
    assert approved.status == "approved"
    assert run.status == "succeeded"
    assert calls[0][1:] == ["data", "repair", "stock_limit_list", "--json"]
    assert runtime.get_action(action.action_id)["status"] == "succeeded"
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


def test_agent_dispatch_records_run_event_timeline(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    def fake_run(command, **kwargs):
        return CompletedProcess(command, 0, stdout='{"ok": true, "step": "done"}', stderr="minor warning")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Run event timeline")
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
    loaded = runtime.get_run(run.run_id)

    assert loaded["status"] == "succeeded"
    assert [event["sequence"] for event in loaded["events"]] == [1, 2, 3, 4, 5]
    assert [event["event_type"] for event in loaded["events"]] == [
        "queued",
        "running",
        "stdout",
        "stderr",
        "succeeded",
    ]
    assert loaded["events"][0]["status"] == "queued"
    assert loaded["events"][2]["message"] == '{"ok": true, "step": "done"}'
    assert loaded["events"][3]["message"] == "minor warning"
    assert loaded["events"][-1]["payload"]["return_code"] == 0
    assert runtime.memory_snapshot()["summary"]["run_event_count"] == 5
    reset_datahub()


def test_agent_dispatch_streams_real_subprocess_output_as_run_events(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from agent_os.tools import AgentToolRegistry, ToolDescriptor

    runtime = AgentRuntime()
    session = runtime.create_session(title="Streaming subprocess output")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="streaming_check",
        risk_level="read_only",
        summary="Run a streaming subprocess",
        parameters={"tool_id": "astroq.health"},
    )
    registry = AgentToolRegistry(
        {
            "astroq.health": ToolDescriptor(
                tool_id="astroq.health",
                label="Streaming subprocess",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import sys,time;"
                        "print('alpha', flush=True);"
                        "print('warn', file=sys.stderr, flush=True);"
                        "time.sleep(0.05);"
                        "print('omega', flush=True)"
                    ),
                ],
                risk_level="read_only",
                desk_scopes=["engineering"],
            )
        }
    )

    run = runtime.dispatch_action(action.action_id, tool_registry=registry, timeout_seconds=5)
    loaded = runtime.get_run(run.run_id)

    assert run.status == "succeeded"
    assert run.stdout_summary.strip() == "alpha\nomega"
    assert run.stderr_summary.strip() == "warn"
    event_types = [event["event_type"] for event in loaded["events"]]
    assert event_types[:2] == ["queued", "running"]
    assert event_types[-1] == "succeeded"
    assert event_types.count("stdout") == 2
    assert event_types.count("stderr") == 1
    assert [event["message"] for event in loaded["events"] if event["event_type"] == "stdout"] == ["alpha", "omega"]
    assert [event["message"] for event in loaded["events"] if event["event_type"] == "stderr"] == ["warn"]
    assert loaded["events"][-1]["payload"]["return_code"] == 0
    reset_datahub()


def test_agent_run_events_are_exposed_by_api_and_action_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    def fake_run(command, **kwargs):
        return CompletedProcess(command, 1, stdout="partial output", stderr="provider failed")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Run event API")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Run health check",
        parameters={"tool_id": "astroq.health"},
    )
    run = runtime.dispatch_action(action.action_id, runner=fake_run)

    client = TestClient(create_app())
    api_payload = client.get(f"/api/agent/runs/{run.run_id}").json()
    cli_code = run_cli(["agent", "action", "show", action.action_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)

    assert api_payload["run"]["events"][-1]["event_type"] == "failed"
    assert api_payload["run"]["events"][-1]["payload"]["return_code"] == 1
    assert cli_code == 0
    assert cli_payload["data"]["runs"][0]["events"][-1]["event_type"] == "failed"
    assert cli_payload["data"]["runs"][0]["events"][2]["message"] == "partial output"
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


def test_agent_runtime_cancels_action_and_blocks_dispatch(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return CompletedProcess(command, 0, stdout="should not run", stderr="")

    runtime = AgentRuntime()
    session = runtime.create_session(title="Cancel action")
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Health check that CEO cancels.",
        parameters={"tool_id": "astroq.health"},
    )

    canceled = runtime.cancel_action(action.action_id, decided_by="ceo", reason="No longer needed")
    run = runtime.dispatch_action(action.action_id, runner=fake_run)

    assert canceled.status == "canceled"
    assert canceled.approval_decision["decision"] == "canceled"
    assert canceled.approval_decision["reason"] == "No longer needed"
    assert calls == []
    assert run.status == "blocked"
    assert "canceled" in run.stderr_summary
    assert runtime.get_action(action.action_id)["status"] == "canceled"
    reset_datahub()


def test_agent_cli_and_api_cancel_action(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    session = runtime.create_session(title="Cancel CLI API")
    first = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Cancel from CLI",
        parameters={"tool_id": "astroq.health"},
    )
    second = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Cancel from API",
        parameters={"tool_id": "astroq.health"},
    )
    terminal = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Already completed",
        parameters={"tool_id": "astroq.health"},
    )
    runtime.dispatch_action(
        terminal.action_id,
        runner=lambda command, **kwargs: CompletedProcess(command, 0, stdout="ok", stderr=""),
    )

    cli_code = run_cli(["agent", "cancel", first.action_id, "--reason", "CLI cancel", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_res = TestClient(create_app()).post(f"/api/agent/actions/{second.action_id}/cancel", json={"reason": "API cancel"})
    terminal_res = TestClient(create_app()).post(
        f"/api/agent/actions/{terminal.action_id}/cancel",
        json={"reason": "too late"},
    )

    assert cli_code == 0
    assert cli_payload["data"]["action"]["status"] == "canceled"
    assert cli_payload["data"]["action"]["approval_decision"]["reason"] == "CLI cancel"
    assert api_res.status_code == 200
    assert api_res.json()["action"]["status"] == "canceled"
    assert api_res.json()["action"]["approval_decision"]["reason"] == "API cancel"
    assert terminal_res.status_code == 400
    assert runtime.get_action(terminal.action_id)["status"] == "succeeded"
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


def test_agent_cli_and_api_run_session_read_only_actions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    cli_session = runtime.create_session(title="CLI readonly workflow")
    runtime.propose_action(
        session_id=cli_session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Run CLI health check",
        parameters={"tool_id": "astroq.health"},
    )

    cli_code = run_cli(["agent", "session", "run-readonly", cli_session.session_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)

    api_session = runtime.create_session(title="API readonly workflow")
    runtime.propose_action(
        session_id=api_session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Run API health check",
        parameters={"tool_id": "astroq.health"},
    )
    api_res = TestClient(create_app()).post(f"/api/agent/sessions/{api_session.session_id}/run-readonly")

    assert cli_code == 0
    assert cli_payload["data"]["workflow"]["status"] == "ready"
    assert cli_payload["data"]["workflow"]["run_count"] == 1
    assert cli_payload["data"]["workflow"]["succeeded_count"] == 1
    assert cli_payload["data"]["workflow"]["runs"][0]["events"][2]["event_type"] == "stdout"
    assert api_res.status_code == 200
    assert api_res.json()["workflow"]["status"] == "ready"
    assert api_res.json()["workflow"]["run_count"] == 1
    assert api_res.json()["workflow"]["succeeded_count"] == 1
    assert api_res.json()["workflow"]["runs"][0]["events"][2]["event_type"] == "stdout"
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


def test_agent_memory_snapshot_and_export_include_ledger_records(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

    runtime = AgentRuntime()
    session = runtime.create_session(title="Memory snapshot", default_desk="reporting")
    message = runtime.add_message(session.session_id, role="ceo", desk="reporting", content="导出本地记忆")
    evidence = runtime.create_evidence(
        kind="ledger",
        label="Memory evidence",
        uri="var/db/agent_os.sqlite",
        summary="Local ledger reference.",
    )
    action = runtime.propose_action(
        session_id=session.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Check health",
        parameters={"tool_id": "astroq.health"},
        evidence_refs=[evidence.evidence_id],
    )
    runtime.record_run(
        action_id=action.action_id,
        tool_name="astroq.health",
        command=[".venv/bin/astroq", "health", "--json"],
        status="succeeded",
        return_code=0,
        stdout_summary="ok",
        stderr_summary="",
    )
    runtime.respond_as_desk(
        session_id=session.session_id,
        source_message_id=message.message_id,
        desk="reporting",
        answer="Memory export ready.",
        handoffs=[{"target_desk": "data", "reason": "检查 memory export"}],
    )

    snapshot = runtime.memory_snapshot()
    exported = runtime.export_memory()
    exported_payload = json.loads(Path(exported["path"]).read_text(encoding="utf-8"))

    assert snapshot["status"] == "ready"
    assert snapshot["summary"]["session_count"] == 1
    assert snapshot["summary"]["message_count"] == 2
    assert snapshot["summary"]["action_count"] == 1
    assert snapshot["summary"]["run_count"] == 1
    assert snapshot["summary"]["evidence_count"] == 1
    assert snapshot["summary"]["handoff_count"] == 1
    assert exported["path"].endswith(".json")
    assert "/agent/memory/" in exported["path"]
    assert exported_payload["records"]["sessions"][0]["session_id"] == session.session_id
    reset_datahub()


def test_agent_memory_cli_and_api_export(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    runtime.create_session(title="Memory CLI/API")

    cli_code = run_cli(["agent", "memory", "export", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    client = TestClient(create_app())
    summary_res = client.get("/api/agent/memory")
    export_res = client.post("/api/agent/memory/export")

    assert cli_code == 0
    assert cli_payload["data"]["artifact"]["path"].endswith(".json")
    assert summary_res.status_code == 200
    assert summary_res.json()["summary"]["session_count"] == 1
    assert export_res.status_code == 200
    assert export_res.json()["artifact"]["path"].endswith(".json")
    reset_datahub()


def test_agent_memory_prune_and_clear_require_explicit_policy(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime
    from astrolabe_cli.main import run_cli
    from web.api.app import create_app

    runtime = AgentRuntime()
    active = runtime.create_session(title="Active memory", default_desk="reporting")
    archived = runtime.create_session(title="Archived memory", default_desk="reporting")
    runtime.update_session(archived.session_id, status="archived")
    runtime.add_message(active.session_id, role="ceo", desk="reporting", content="keep me")
    archived_message = runtime.add_message(archived.session_id, role="ceo", desk="reporting", content="prune me")
    active_evidence = runtime.create_evidence(kind="ledger", label="Active", uri="active", summary="keep")
    archived_evidence = runtime.create_evidence(kind="ledger", label="Archived", uri="archived", summary="prune")
    action = runtime.propose_action(
        session_id=archived.session_id,
        desk="engineering",
        action_type="health_check",
        risk_level="read_only",
        summary="Archived health",
        parameters={"tool_id": "astroq.health"},
        evidence_refs=[archived_evidence.evidence_id],
    )
    runtime.record_run(
        action_id=action.action_id,
        tool_name="astroq.health",
        command=[".venv/bin/astroq", "health", "--json"],
        status="succeeded",
        return_code=0,
        stdout_summary="ok",
        stderr_summary="",
        artifact_refs=[archived_evidence.evidence_id],
    )
    runtime.respond_as_desk(
        session_id=archived.session_id,
        source_message_id=archived_message.message_id,
        desk="reporting",
        answer="handoff",
        evidence_refs=[archived_evidence.evidence_id],
        handoffs=[{"target_desk": "data", "reason": "prune handoff"}],
    )

    dry_run = runtime.prune_memory(dry_run=True)
    snapshot_before = runtime.memory_snapshot()
    cli_code = run_cli(["agent", "memory", "prune", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    client = TestClient(create_app())
    cli_clear_code = run_cli(["agent", "memory", "clear", "--json"])
    cli_clear_payload = json.loads(capsys.readouterr().out)
    clear_without_confirm = client.post("/api/agent/memory/clear", json={})

    assert dry_run["dry_run"] is True
    assert dry_run["counts"]["sessions"] == 1
    assert snapshot_before["summary"]["session_count"] == 2
    assert cli_code == 0
    assert cli_payload["data"]["result"]["counts"]["sessions"] == 1
    assert runtime.memory_snapshot()["records"]["sessions"][0]["session_id"] == active.session_id
    assert runtime.memory_snapshot()["records"]["evidence"][0]["evidence_id"] == active_evidence.evidence_id
    assert cli_clear_code == 1
    assert cli_clear_payload["ok"] is False
    assert clear_without_confirm.status_code == 400
    clear_with_confirm = client.post("/api/agent/memory/clear", json={"confirm": True})
    assert clear_with_confirm.status_code == 200
    assert clear_with_confirm.json()["result"]["counts"]["sessions"] == 1
    assert runtime.memory_snapshot()["summary"]["session_count"] == 0
    assert runtime.memory_snapshot()["summary"]["evidence_count"] == 0
    reset_datahub()
