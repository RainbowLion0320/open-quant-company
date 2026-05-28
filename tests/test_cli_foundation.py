import json
import subprocess
import sys
from pathlib import Path


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


def test_python_module_entrypoint_renders_json():
    completed = subprocess.run(
        [sys.executable, "-m", "astrolabe_cli.main", "health", "--json"],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    parsed = json.loads(completed.stdout)
    assert parsed["ok"] is True
    assert parsed["command"] == "health"


def test_unknown_command_returns_usage_exit():
    from astrolabe_cli.main import run_cli

    try:
        run_cli(["missing"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("argparse should exit for unknown command")


def test_validate_runtime_mode_rejects_invalid_mode():
    from astrolabe_cli.safety import validate_runtime_mode

    try:
        validate_runtime_mode("paper")
    except ValueError as exc:
        assert "Invalid runtime mode" in str(exc)
    else:
        raise AssertionError("invalid runtime mode should fail")


def test_docs_describe_astroq_as_agent_control_plane():
    docs = Path("docs/DOCUMENTATION.md").read_text(encoding="utf-8")
    web_spec = Path("docs/specs/05-web-platform.md").read_text(encoding="utf-8")
    acceptance = Path("docs/acceptance-matrix.md").read_text(encoding="utf-8")

    assert "astroq" in docs
    assert "Agent-facing Control Plane" in web_spec
    assert "CLI Control Plane" in acceptance
