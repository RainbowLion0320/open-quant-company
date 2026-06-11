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


def test_data_sources_cli_lists_latest_capability_summary(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import astrolabe_cli.commands.data as data_commands

    monkeypatch.setattr(
        data_commands,
        "sources_summary_payload",
        lambda: {
            "status": "no_artifact",
            "sources": [{"source": "akshare", "capability_count": 0}],
            "summary": {"source_count": 9, "capability_count": 0},
            "recommended_command": "astroq data sources audit --source all --json",
        },
    )

    code = run_cli(["data", "sources", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["command"] == "data sources"
    assert data["data"]["summary"]["source_count"] == 9


def test_data_sources_audit_cli_supports_akshare(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import astrolabe_cli.commands.data as data_commands

    calls = []

    def fake_audit_sources(source="all", probe_network=False, write=True):
        calls.append({"source": source, "probe_network": probe_network, "write": write})
        return {
            "status": "ok",
            "summary": {"source_count": 1, "capability_count": 2},
            "sources": [{"source": "akshare", "capability_count": 2}],
            "diff": {"summary": {}},
        }

    monkeypatch.setattr(data_commands, "audit_sources", fake_audit_sources)

    code = run_cli(["data", "sources", "audit", "--source", "akshare", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["command"] == "data sources audit"
    assert calls == [{"source": "akshare", "probe_network": False, "write": True}]
    assert data["data"]["summary"]["capability_count"] == 2


def test_data_sources_audit_cli_supports_tushare_offline(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import astrolabe_cli.commands.data as data_commands

    calls = []
    monkeypatch.setattr(
        data_commands,
        "audit_sources",
        lambda source="all", probe_network=False, write=True: (
            calls.append({"source": source, "probe_network": probe_network, "write": write})
            or {
                "status": "ok",
                "summary": {"source_count": 1, "capability_count": 1},
                "sources": [{"source": "tushare", "capability_count": 1, "access_statuses": {"not_probed": 1}}],
                "diff": {"summary": {}},
            }
        ),
    )

    code = run_cli(["data", "sources", "audit", "--source", "tushare", "--offline", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert calls == [{"source": "tushare", "probe_network": False, "write": True}]
    assert data["data"]["sources"][0]["source"] == "tushare"


def test_data_sources_diff_registry_cli(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import astrolabe_cli.commands.data as data_commands

    monkeypatch.setattr(
        data_commands,
        "sources_diff_payload",
        lambda: {
            "status": "ok",
            "summary": {"capability_unmapped_count": 3, "registry_missing_source_count": 1},
            "capability_unmapped": [],
            "registry_missing_source": [{"dimension": "stock_basic"}],
        },
    )

    code = run_cli(["data", "sources", "diff-registry", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["command"] == "data sources diff-registry"
    assert data["data"]["summary"]["registry_missing_source_count"] == 1
