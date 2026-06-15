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
                "broker_order_id": "LIVE_0001",
                "submitted_at": "2026-06-15T00:00:00Z",
                "broker_status": "accepted",
                "raw_response_hash": "sha256:demo",
                "ledger_id": approval_id,
                "submitted": True,
            }

        def reconcile(self, ack):
            self.reconcile_calls += 1
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
    assert submitted["status"] == "succeeded"
    assert submitted["ack"]["broker_order_id"] == "LIVE_0001"
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
    assert context["available_count"] == 5
    assert context["missing_count"] >= 1
    assert any(item["key"] == "lifecycle" and item["status"] == "available" for item in context["items"])
    assert any(item["key"] == "codegraph" and item["status"] == "missing" for item in context["items"])
    assert "macro_gdp" in sections["artifact_findings"]["body"]
    assert "source_not_updated" in sections["artifact_findings"]["body"]
    assert "strategy_competition" in sections["artifact_readiness"]["body"]
    assert "data-sources/latest.json" in sections["artifact_readiness"]["body"]
    assert "codegraph" in sections["artifact_readiness"]["body"]
    assert "artifact_context" in payload
    assert "macro_gdp" in Path(report["markdown_path"]).read_text(encoding="utf-8")
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
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

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
    from data.storage.datahub import reset_datahub

    reset_datahub()

    from agent_os.runtime import AgentRuntime

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

    def fake_run(command, **kwargs):
        return CompletedProcess(command, 0, stdout='{"batch": true}', stderr="")

    monkeypatch.setattr("agent_os.runtime.subprocess.run", fake_run)

    runtime = AgentRuntime()
    cli_session = runtime.create_session(title="CLI readonly workflow")
    runtime.submit_ceo_message(cli_session.session_id, desk="reporting", content="今天系统该做什么，给我 CEO 简报")

    cli_code = run_cli(["agent", "session", "run-readonly", cli_session.session_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)

    api_session = runtime.create_session(title="API readonly workflow")
    runtime.submit_ceo_message(api_session.session_id, desk="reporting", content="今天系统该做什么，给我 CEO 简报")
    api_res = TestClient(create_app()).post(f"/api/agent/sessions/{api_session.session_id}/run-readonly")

    assert cli_code == 0
    assert cli_payload["data"]["workflow"]["status"] == "ready"
    assert cli_payload["data"]["workflow"]["run_count"] == 3
    assert cli_payload["data"]["workflow"]["succeeded_count"] == 3
    assert api_res.status_code == 200
    assert api_res.json()["workflow"]["status"] == "ready"
    assert api_res.json()["workflow"]["run_count"] == 3
    assert api_res.json()["workflow"]["succeeded_count"] == 3
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
