import json


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_health_command_reports_core_sections(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["health", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["project"] == "open-quant-company"
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


def test_test_check_cli_writes_latest_artifact(monkeypatch, tmp_path, capsys):
    from data.storage.datahub import reset_datahub
    from astrolabe_cli.main import run_cli

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    class FakeCompleted:
        returncode = 0
        stdout = "3 passed, 1 warning in 1.23s\n"
        stderr = ""

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted()

    monkeypatch.setattr("subprocess.run", fake_run)

    code = run_cli(["test", "check", "--suite", "quick", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["suite"] == "quick"
    assert data["data"]["totals"]["passed"] == 3
    assert data["data"]["totals"]["warnings"] == 1
    assert calls and calls[0][0].endswith("python")
    assert calls[0][1:3] == ["-m", "pytest"]

    artifact_root = tmp_path / "var" / "artifacts" / "tests"
    latest = json.loads((artifact_root / "latest.json").read_text(encoding="utf-8"))
    assert latest["suite"] == "quick"
    assert latest["status"] == "passed"
    assert latest["totals"]["passed"] == 3
    assert latest["command"][1:3] == ["-m", "pytest"]
    assert (artifact_root / "runs" / f"{latest['run_id']}.json").exists()
    reset_datahub()


def test_test_check_cli_records_failure_summary(monkeypatch, tmp_path, capsys):
    from data.storage.datahub import reset_datahub
    from astrolabe_cli.main import run_cli

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    class FakeCompleted:
        returncode = 1
        stdout = "1 failed, 2 passed in 0.80s\nFAILED tests/test_example.py::test_breaks - AssertionError\n"
        stderr = "assert 1 == 2\n"

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeCompleted())

    code = run_cli(["test", "check", "--suite", "quick", "--json"])
    data = _json_from_cli(capsys)

    assert code == 1
    assert data["ok"] is False
    assert data["data"]["status"] == "failed"
    assert data["data"]["totals"]["failed"] == 1
    assert data["data"]["failures"]
    assert "test_breaks" in data["data"]["failures"][0]
    reset_datahub()


def test_test_design_cli_writes_design_artifact_without_pytest(monkeypatch, tmp_path, capsys):
    from data.storage.datahub import reset_datahub
    from astrolabe_cli.main import run_cli

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pytest should not run")))
    reset_datahub()

    code = run_cli(["test", "design", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["status"] in {"ok", "empty"}
    assert data["data"]["summary"]["test_count"] >= 1
    assert data["data"]["matrix"]["risks"]
    assert data["data"]["graph"]["node_count"] >= 1

    artifact = tmp_path / "var" / "artifacts" / "tests" / "design" / "latest.json"
    latest = json.loads(artifact.read_text(encoding="utf-8"))
    assert latest["recommended_command"] == "astroq test design --json"
    assert latest["graph"]["nodes"]
    assert latest["cases"]
    reset_datahub()
