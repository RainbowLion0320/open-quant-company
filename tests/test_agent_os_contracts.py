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

    cli_code = run_cli(["agent", "report", "daily", "--session", session.session_id, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_client = TestClient(create_app())
    api_create = api_client.post("/api/agent/reports", json={"kind": "weekly_review", "session_id": session.session_id})
    api_list = api_client.get(f"/api/agent/reports?session_id={session.session_id}")

    assert cli_code == 0
    assert cli_payload["data"]["report"]["kind"] == "daily_brief"
    assert Path(cli_payload["data"]["report"]["path"]).exists()
    assert api_create.status_code == 200
    assert api_create.json()["report"]["kind"] == "weekly_review"
    assert Path(api_create.json()["report"]["path"]).exists()
    assert api_list.status_code == 200
    assert api_list.json()["total"] == 2
    assert {row["kind"] for row in api_list.json()["reports"]} == {"daily_brief", "weekly_review"}
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
    action = runtime.get_action(desk_response.proposed_actions[0])
    evidence = runtime.ledger.get_evidence(desk_response.evidence_refs[0])
    handoff_targets = {handoff["target_desk"] for handoff in desk_response.handoffs}

    assert ceo_message.role == "ceo"
    assert desk_response.message.role == "desk_agent"
    assert desk_response.message.desk == "reporting"
    assert "Reporting Desk" in desk_response.answer
    assert desk_response.confidence >= 0.6
    assert action["risk_level"] == "read_only"
    assert action["parameters"]["tool_id"] == "astroq.lifecycle.check"
    assert action["status"] == "proposed"
    assert evidence["kind"] == "web_route"
    assert evidence["uri"] == "/system?tab=lifecycle"
    assert handoff_targets >= {"data", "research", "risk"}
    assert loaded["messages"][0]["message_id"] == ceo_message.message_id
    assert loaded["messages"][1]["message_id"] == desk_response.message.message_id
    assert loaded["actions"][0]["action_id"] == action["action_id"]
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
