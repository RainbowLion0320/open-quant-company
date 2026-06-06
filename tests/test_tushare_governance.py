import pandas as pd


def test_symbol_file_coverage_counts_missing_expected_symbols(tmp_path):
    from data.ingestion.tushare_coverage import missing_symbol_files, symbol_file_coverage

    root = tmp_path / "stock" / "fina_indicator"
    root.mkdir(parents=True)
    (root / "000001.SZ.parquet").write_bytes(b"not-empty")

    result = symbol_file_coverage(root, ["000001.SZ", "000002.SZ"])

    assert result == {
        "expected": 2,
        "existing": 1,
        "missing": 1,
        "ratio": 0.5,
        "missing_sample": ["000002.SZ"],
    }
    assert missing_symbol_files(root, ["000001.SZ", "000002.SZ"]) == ["000002.SZ"]


def test_probe_status_classifies_permission_rate_limit_and_empty(monkeypatch):
    from data.ingestion.tushare_governance import classify_probe_result

    assert classify_probe_result(pd.DataFrame({"a": [1]})) == ("ok", "")
    assert classify_probe_result(pd.DataFrame()) == ("empty", "")
    assert classify_probe_result(Exception("抱歉，您没有接口访问权限")) == ("no_permission", "抱歉，您没有接口访问权限")
    assert classify_probe_result(Exception("每分钟最多访问1次")) == ("rate_limited", "每分钟最多访问1次")


def test_backfill_records_rate_limited_tasks_as_skipped(tmp_path, monkeypatch):
    import data.ingestion.tushare_governance as governance
    from data.ingestion.tushare_governance import TushareGovernance
    from data.ingestion.tushare_tasks import BackfillTask
    from data.storage.datahub import DataHub

    hub = DataHub(
        runtime_root=tmp_path / "var",
        store_root=tmp_path / "var" / "store",
        cache_root=tmp_path / "var" / "cache",
    )
    runner = TushareGovernance(hub=hub, token="token")
    monkeypatch.setattr(governance, "BACKFILL_TASKS", [BackfillTask("cyq_perf", "筹码", "p2", direct="cyq_perf")])
    monkeypatch.setattr(
        runner,
        "coverage",
        lambda days=365: {"cyq_perf": {"expected": 1, "existing": 0, "missing": 1, "ratio": 0.0}},
    )
    monkeypatch.setattr(runner, "run_direct_task", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("每小时最多访问1次")))

    result = runner.backfill(scope="p2", dry_run=False)

    assert result["failed"] == []
    assert result["skipped"] == [{"key": "cyq_perf", "reason": "rate_limited", "message": "每小时最多访问1次"}]


def test_stock_universe_prefers_tushare_stock_basic(tmp_path, monkeypatch):
    import data.ingestion.tushare_governance as governance
    from data.ingestion.tushare_governance import TushareGovernance
    from data.storage.datahub import DataHub

    hub = DataHub(
        runtime_root=tmp_path / "var",
        store_root=tmp_path / "var" / "store",
        cache_root=tmp_path / "var" / "cache",
    )
    hub.write_parquet(
        pd.DataFrame({"symbol": ["000001", "920096", "bad"]}),
        hub.dimension_root("stock_basic"),
    )
    monkeypatch.setattr(governance, "CIRCLE_STOCKS", ("000002",))

    runner = TushareGovernance(hub=hub, token="token")

    assert runner.stock_universe() == ["000001", "920096"]


def test_asset_universe_coverage_uses_project_etf_and_futures_universes(tmp_path, monkeypatch):
    import data.ingestion.tushare_coverage as coverage_module
    from data.ingestion.tushare_governance import TushareGovernance
    from data.storage.datahub import DataHub

    hub = DataHub(
        runtime_root=tmp_path / "var",
        store_root=tmp_path / "var" / "store",
        cache_root=tmp_path / "var" / "cache",
    )
    monkeypatch.setattr(coverage_module, "ETF_UNIVERSE", ("510050", "159915"))
    monkeypatch.setattr(coverage_module, "FUTURES_UNIVERSE", ("IF", "RB"))

    hub.write_parquet(pd.DataFrame({"x": [1]}), hub.dimension_root("fund_daily") / "510050.SH.parquet")
    hub.write_parquet(pd.DataFrame({"x": [1]}), hub.dimension_root("fund_nav") / "159915.SZ.parquet")
    hub.write_parquet(pd.DataFrame({"x": [1]}), hub.dimension_root("futures_daily") / "IF.CFX.parquet")

    runner = TushareGovernance(hub=hub, token="token")
    monkeypatch.setattr(runner, "trade_days", lambda days=365: [])

    coverage = runner.coverage()

    assert coverage["fund_daily"]["expected"] == 2
    assert coverage["fund_daily"]["missing"] == 1
    assert coverage["fund_nav"]["expected"] == 2
    assert coverage["fund_nav"]["missing"] == 1
    assert coverage["futures_daily"]["expected"] == 2
    assert coverage["futures_daily"]["missing"] == 1


def test_holder_event_backfill_writes_empty_success_as_coverage_marker(tmp_path, monkeypatch):
    import data.ingestion.tushare_governance as governance
    from data.ingestion.tushare_coverage import missing_symbol_files
    from data.ingestion.tushare_governance import TushareGovernance
    from data.storage.datahub import DataHub

    hub = DataHub(
        runtime_root=tmp_path / "var",
        store_root=tmp_path / "var" / "store",
        cache_root=tmp_path / "var" / "cache",
    )
    runner = TushareGovernance(hub=hub, token="token")
    monkeypatch.setattr(governance, "CIRCLE_STOCKS", ("000001",))
    monkeypatch.setattr(governance.time, "sleep", lambda _: None)
    monkeypatch.setattr(runner, "_pro_query", lambda *args, **kwargs: pd.DataFrame(columns=["ts_code", "ann_date"]))

    rows = runner._fetch_holder_trade_missing()

    assert rows == 0
    assert (hub.dimension_root("holder_trade") / "000001.parquet").exists()
    assert missing_symbol_files(hub.dimension_root("holder_trade"), ["000001"]) == []
