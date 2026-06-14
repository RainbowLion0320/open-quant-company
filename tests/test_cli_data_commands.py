import json
from types import SimpleNamespace

import pandas as pd
import pytest


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


def test_limit_list_repair_fails_when_provider_returns_no_rows_and_table_stays_stale(monkeypatch):
    from scripts import repair_table

    monkeypatch.setattr(
        "scripts.cron_fetch_extra.fetch_limit_list",
        lambda full_history=False: 0,
    )
    monkeypatch.setattr(
        "scripts.db_health_check.run_health_check",
        lambda: pd.DataFrame(
            [{"table": "stock_limit_list", "registry_key": "limit_list", "freshness_status": "stale"}]
        ),
    )
    monkeypatch.setattr(repair_table, "_require_rows_or_cache", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="stock_limit_list remains stale"):
        repair_table.repair_limit_list()


def test_data_repair_fails_when_table_remains_stale_after_repair(monkeypatch):
    from scripts import repair_table

    class DummyLedger:
        def start(self, *args, **kwargs):
            return "run-1"

        def complete(self, *args, **kwargs):
            raise AssertionError("stale repair must not be marked complete")

        def fail(self, *args, **kwargs):
            return None

    monkeypatch.setattr("data.ops.backfill.BackfillLedger", lambda: DummyLedger())
    monkeypatch.setitem(repair_table.REPAIR_MAP, "macro_gdp", lambda limit=0, days=365: None)
    monkeypatch.setattr(
        "scripts.db_health_check.run_health_check",
        lambda: pd.DataFrame([{"registry_key": "macro_gdp", "freshness_status": "stale"}]),
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="Health check done"),
    )

    with pytest.raises(RuntimeError, match="macro_gdp remains stale after repair"):
        repair_table.repair("macro_gdp")


def test_stock_holders_repair_uses_period_batch_fetch_for_full_refresh(monkeypatch):
    from scripts import repair_table

    calls = []

    class FakeHolderFetcher:
        def fetch_period(self, end_date):
            calls.append(end_date)
            return 5500

        def batch_fetch(self, symbols, force=False):
            raise AssertionError("full holder repair must use period batch fetch")

    monkeypatch.setattr(
        "data.ingestion.fetchers.holders.HolderFetcher",
        FakeHolderFetcher,
    )
    monkeypatch.setattr(
        repair_table,
        "_latest_completed_quarter_end",
        lambda: "20260331",
        raising=False,
    )

    repair_table.repair_holders(limit=0)

    assert calls == ["20260331"]


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
            "recommended_command": "astroq data sources audit --source all --discovery-depth catalog --json",
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

    def fake_audit_sources(source="all", probe_network=False, write=True, discovery_depth="catalog"):
        calls.append(
            {
                "source": source,
                "probe_network": probe_network,
                "write": write,
                "discovery_depth": discovery_depth,
            }
        )
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
    assert calls == [{"source": "akshare", "probe_network": False, "write": True, "discovery_depth": "catalog"}]
    assert data["data"]["summary"]["capability_count"] == 2


def test_data_sources_audit_cli_passes_sample_discovery_depth(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import astrolabe_cli.commands.data as data_commands

    calls = []

    def fake_audit_sources(source="all", probe_network=False, write=True, discovery_depth="catalog"):
        calls.append(
            {
                "source": source,
                "probe_network": probe_network,
                "write": write,
                "discovery_depth": discovery_depth,
            }
        )
        return {
            "status": "ok",
            "summary": {"source_count": 1, "capability_count": 2, "sample_probed_count": 1},
            "sources": [{"source": "tencent_finance", "capability_count": 2}],
            "diff": {"summary": {}},
        }

    monkeypatch.setattr(data_commands, "audit_sources", fake_audit_sources)

    code = run_cli(
        [
            "data",
            "sources",
            "audit",
            "--source",
            "tencent_finance",
            "--discovery-depth",
            "sample",
            "--json",
        ]
    )
    data = _json_from_cli(capsys)

    assert code == 0
    assert calls == [
        {
            "source": "tencent_finance",
            "probe_network": False,
            "write": True,
            "discovery_depth": "sample",
        }
    ]
    assert data["data"]["summary"]["sample_probed_count"] == 1


def test_data_sources_audit_cli_supports_full_sample_resume_and_dry_run(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import astrolabe_cli.commands.data as data_commands

    calls = []

    def fake_audit_sources(
        source="all",
        probe_network=False,
        write=True,
        discovery_depth="catalog",
        dry_run=False,
        resume=False,
    ):
        calls.append(
            {
                "source": source,
                "probe_network": probe_network,
                "write": write,
                "discovery_depth": discovery_depth,
                "dry_run": dry_run,
                "resume": resume,
            }
        )
        return {
            "status": "ok",
            "summary": {"source_count": 9, "capability_count": 2, "probe_planned_count": 2},
            "sources": [{"source": "all", "capability_count": 2}],
            "diff": {"summary": {}},
        }

    monkeypatch.setattr(data_commands, "audit_sources", fake_audit_sources)

    code = run_cli(
        [
            "data",
            "sources",
            "audit",
            "--source",
            "all",
            "--discovery-depth",
            "full-sample",
            "--resume",
            "--dry-run",
            "--json",
        ]
    )
    data = _json_from_cli(capsys)

    assert code == 0
    assert calls == [
        {
            "source": "all",
            "probe_network": True,
            "write": True,
            "discovery_depth": "full-sample",
            "dry_run": True,
            "resume": True,
        }
    ]
    assert data["data"]["summary"]["probe_planned_count"] == 2


def test_data_sources_audit_cli_supports_tushare_offline(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli
    import astrolabe_cli.commands.data as data_commands

    calls = []
    monkeypatch.setattr(
        data_commands,
        "audit_sources",
        lambda source="all", probe_network=False, write=True, discovery_depth="catalog": (
            calls.append(
                {
                    "source": source,
                    "probe_network": probe_network,
                    "write": write,
                    "discovery_depth": discovery_depth,
                }
            )
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
    assert calls == [{"source": "tushare", "probe_network": False, "write": True, "discovery_depth": "catalog"}]
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
