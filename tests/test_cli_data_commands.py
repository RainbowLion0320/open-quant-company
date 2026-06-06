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


def test_tushare_audit_cli_reports_capabilities_and_coverage(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import data.ingestion.tushare_governance as governance

    monkeypatch.setattr(
        governance,
        "run_tushare_audit",
        lambda probe_network=True: {
            "capabilities": {
                "daily": {"status": "ok", "rows": 1},
                "stk_mins": {"status": "minute_audit_only", "rows": 1},
            },
            "coverage": {
                "fina_indicator": {"expected": 2, "existing": 1, "missing": 1, "ratio": 0.5}
            },
            "minute_policy": "audit_only",
        },
    )

    code = run_cli(["data", "tushare-audit", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["command"] == "data tushare-audit"
    assert data["data"]["capabilities"]["daily"]["status"] == "ok"
    assert data["data"]["capabilities"]["stk_mins"]["status"] == "minute_audit_only"
    assert data["data"]["coverage"]["fina_indicator"]["missing"] == 1


def test_tushare_backfill_cli_dry_run_does_not_fetch(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import data.ingestion.tushare_governance as governance

    calls = []

    def fake_backfill(scope="missing", resume=True, dry_run=False, limit=0, days=365):
        calls.append(
            {"scope": scope, "resume": resume, "dry_run": dry_run, "limit": limit, "days": days}
        )
        return {
            "dry_run": dry_run,
            "planned": ["stock_fina_indicator", "stock_valuation"],
            "completed": [],
            "skipped": [],
            "failed": [],
        }

    monkeypatch.setattr(governance, "run_tushare_backfill", fake_backfill)

    code = run_cli(
        [
            "data",
            "tushare-backfill",
            "--scope",
            "missing",
            "--resume",
            "--dry-run",
            "--limit",
            "3",
            "--days",
            "30",
            "--json",
        ]
    )
    data = _json_from_cli(capsys)

    assert code == 0
    assert calls == [{"scope": "missing", "resume": True, "dry_run": True, "limit": 3, "days": 30}]
    assert data["ok"] is True
    assert data["command"] == "data tushare-backfill"
    assert data["data"]["planned"] == ["stock_fina_indicator", "stock_valuation"]
