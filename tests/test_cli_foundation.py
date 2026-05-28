import json


def test_cli_result_json_shape():
    from astrolabe_cli.results import CliResult

    payload = CliResult(ok=True, command="health", data={"status": "ok"}, message="ready").to_dict()

    assert payload == {
        "ok": True,
        "command": "health",
        "data": {"status": "ok"},
        "message": "ready",
        "errors": [],
    }


def test_cli_health_help_exits_zero(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["health", "--help"])
    out = capsys.readouterr().out

    assert code == 0
    assert "usage:" in out


def test_cli_json_flag_renders_json(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["health", "--json"])
    out = capsys.readouterr().out

    assert code == 0
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["command"] == "health"
