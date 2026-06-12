from __future__ import annotations

import json
from pathlib import Path


def test_lifecycle_check_writes_readiness_artifact(monkeypatch, tmp_path):
    from astrolabe_cli.commands import lifecycle

    monkeypatch.setattr(
        lifecycle,
        "sources_diff_payload",
        lambda: {
            "summary": {"registry_missing_source_count": 1},
            "registry_missing_source": [{"dimension": "cashflow_statement", "source": "tushare"}],
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "freshness_gate_from_health_check",
        lambda: ({"ok": False, "stale": ["stock_cashflow_statement"], "missing": []}, 10),
    )
    monkeypatch.setattr(
        lifecycle,
        "build_strategy_competition_report",
        lambda: {
            "summary": {"strategy_count": 1, "invalid_count": 1},
            "rankings": [
                {
                    "strategy": "alpha",
                    "competition_valid": False,
                    "data_quality": {"blockers": ["missing_score_panel"]},
                    "alpha_evidence": {"status": "missing"},
                }
            ],
        },
    )
    monkeypatch.setattr(lifecycle, "get_datahub", lambda: type("Hub", (), {"artifact_dir": lambda self, kind: tmp_path / kind})())

    result = lifecycle.check()

    assert result.ok is False
    assert result.command == "lifecycle check"
    assert result.data["status"] == "blocked"
    assert {"source_capabilities", "data_freshness", "strategy_evidence", "execution"} <= set(result.data["checks"])
    assert "missing_score_panel" in result.data["blockers"]
    latest = tmp_path / "lifecycle" / "latest.json"
    assert latest.exists()
    saved = json.loads(latest.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"


def test_lifecycle_cli_command_renders_json(monkeypatch, tmp_path, capsys):
    import astrolabe_cli.main as main
    from astrolabe_cli.main import run_cli
    from astrolabe_cli.commands import lifecycle

    monkeypatch.setattr(
        main,
        "lifecycle_check",
        lambda: lifecycle.CliResult(
            ok=True,
            command="lifecycle check",
            message="Lifecycle readiness ok",
            data={"status": "ok", "checks": {}, "blockers": []},
        ),
    )

    code = run_cli(["lifecycle", "check", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["command"] == "lifecycle check"
    assert payload["data"]["status"] == "ok"


def test_lifecycle_api_is_read_only_no_artifact(monkeypatch, tmp_path):
    from web.api.services import system_lifecycle

    monkeypatch.setattr(system_lifecycle, "get_datahub", lambda: type("Hub", (), {"artifact_dir": lambda self, kind: tmp_path / kind})())

    payload = system_lifecycle.lifecycle_payload()

    assert payload["status"] == "no_artifact"
    assert payload["recommended_command"] == "astroq lifecycle check --json"
    assert payload["checks"] == {}
