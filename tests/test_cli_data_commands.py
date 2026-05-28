import json


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_data_status_runs_health_check(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    monkeypatch.setattr(
        "scripts.db_health_check.run_health_check",
        lambda: [{"table": "summary", "missing_pct": 0}],
    )

    code = run_cli(["data", "status", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["rows"] == 1


def test_data_repair_dry_run_does_not_call_repair(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    calls = []
    monkeypatch.setattr("scripts.repair_table.repair", lambda *args, **kwargs: calls.append((args, kwargs)))

    code = run_cli(["data", "repair", "stock_valuation", "--dry-run", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert calls == []
    assert data["data"]["dry_run"] is True
