import json


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_health_command_reports_core_sections(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["health", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["project"] == "astrolabe-quant"
    assert "version" in data["data"]
    assert "store_root" in data["data"]


def test_config_validate_reports_strategy_count(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["config", "validate", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["strategy_count"] >= 4


def test_regime_status_command_uses_orchestrator(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    class FakeRegime:
        value = "sideways"

    class FakeSnapshot:
        regime = FakeRegime()
        regime_score = 51.2
        index_ma_trend = "flat"

    class FakeOrchestrator:
        def detect(self):
            return FakeSnapshot()

    monkeypatch.setattr("cybernetics.orchestrator.QuantOrchestrator", FakeOrchestrator)

    code = run_cli(["regime", "status", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["data"]["regime"] == "sideways"
    assert data["data"]["score"] == 51.2


def test_docs_check_command_runs_rg(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    class FakeCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeCompleted())

    code = run_cli(["docs", "check", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True


def test_web_build_dry_run(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    code = run_cli(["web", "build", "--dry-run", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert calls == []
    assert data["data"]["dry_run"] is True
