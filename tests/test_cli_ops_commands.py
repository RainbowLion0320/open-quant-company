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
