from __future__ import annotations

import json
import sys
from types import ModuleType

import pandas as pd


def test_source_catalog_separates_external_capabilities_from_project_registry():
    from data.ingestion.source_capabilities import SOURCE_IDS, source_catalog
    from data.ingestion.source_capability_catalog import CANDIDATE_CAPABILITIES
    from data.storage.dimensions import get_registry

    expected = {
        "akshare",
        "tushare",
        "tencent_finance",
        "eastmoney",
        "sina_finance",
        "tonghuashun",
        "exchange_official",
        "cninfo",
        "computed",
    }

    assert expected.issubset(set(SOURCE_IDS))
    assert expected.issubset({item["source"] for item in source_catalog()})

    registry_sources = {dim.source for dim in get_registry().all.values()}
    assert "tencent_finance" not in registry_sources
    assert "eastmoney" not in registry_sources
    assert "sina_finance" not in registry_sources
    assert "tonghuashun" not in registry_sources

    tx_capabilities = [item for item in CANDIDATE_CAPABILITIES if item["source"] == "tencent_finance"]
    interfaces = {item["interface"] for item in tx_capabilities}
    assert {"qt_gtimg_realtime_quote", "ifzq_fqkline"}.issubset(interfaces)
    assert all(not item["mapped_dimensions"] for item in tx_capabilities)
    assert all(item["integration_status"] == "candidate" for item in tx_capabilities if item["interface"] != "stock_zh_index_daily_tx")
    assert all(item["access_status"] in {"candidate", "manual_review"} for item in tx_capabilities)


def test_tencent_finance_candidate_parsers_are_explicit_and_non_production():
    from data.ingestion.tencent_finance import parse_fqkline_payload, parse_realtime_quote

    quote = parse_realtime_quote(
        'v_sh600519="1~贵州茅台~600519~1550.00~1540.00~1541.00~12000~'
        '6000~6000~1550.00~10~1549.00~20~1551.00~30~1552.00~40~1553.00~50~'
        '1548.00~60~1547.00~70~1546.00~80~1545.00~90~1544.00~100~'
        '20260613150003";'
    )
    kline = parse_fqkline_payload(
        {
            "code": 0,
            "data": {
                "sh600519": {
                    "qfqday": [
                        ["2024-01-02", "1700.00", "1705.00", "1710.00", "1690.00", "12345"],
                    ]
                }
            },
        },
        symbol="sh600519",
        adjust="qfq",
    )

    assert quote["symbol"] == "sh600519"
    assert quote["name"] == "贵州茅台"
    assert quote["last_price"] == 1550.0
    assert quote["previous_close"] == 1540.0
    assert quote["timestamp"] == "20260613150003"
    assert kline[0]["symbol"] == "sh600519"
    assert kline[0]["adjust"] == "qfq"
    assert kline[0]["open"] == 1700.0
    assert kline[0]["close"] == 1705.0


def test_akshare_introspection_uses_local_package_without_network(monkeypatch):
    from data.ingestion.source_capabilities import audit_akshare_capabilities

    fake = ModuleType("akshare")
    fake.__version__ = "9.9.9"

    def stock_zh_a_daily(symbol="000001", start_date="", end_date=""):
        """A share daily quotes."""
        return None

    def macro_china_cpi():
        """China CPI."""
        return None

    fake.stock_zh_a_daily = stock_zh_a_daily
    fake.macro_china_cpi = macro_china_cpi
    fake.__all__ = ["stock_zh_a_daily", "macro_china_cpi"]
    monkeypatch.setitem(sys.modules, "akshare", fake)

    result = audit_akshare_capabilities(limit=20)

    assert result["source"] == "akshare"
    assert result["version"] == "9.9.9"
    names = {item["interface"] for item in result["capabilities"]}
    assert {"stock_zh_a_daily", "macro_china_cpi"}.issubset(names)
    stock = next(item for item in result["capabilities"] if item["interface"] == "stock_zh_a_daily")
    assert stock["asset_type"] == "stock"
    assert stock["data_domain"] == "market_price"
    assert stock["access_status"] == "introspected"
    assert stock["probe_strategy"] == "introspection_only"


def test_full_source_discovery_layers_candidate_backend_capabilities(monkeypatch):
    from data.ingestion import source_capabilities as caps

    fake = ModuleType("akshare")
    fake.__version__ = "9.9.9"

    def stock_board_industry_name_em():
        """Eastmoney industry board names."""
        return None

    def futures_main_sina():
        """Sina main futures quotes."""
        return None

    def stock_financial_cash_ths():
        """Tonghuashun cash flow statement."""
        return None

    def stock_zh_a_hist_tx():
        """Tencent A-share historical quotes."""
        return None

    fake.stock_board_industry_name_em = stock_board_industry_name_em
    fake.futures_main_sina = futures_main_sina
    fake.stock_financial_cash_ths = stock_financial_cash_ths
    fake.stock_zh_a_hist_tx = stock_zh_a_hist_tx
    fake.__all__ = [
        "stock_board_industry_name_em",
        "futures_main_sina",
        "stock_financial_cash_ths",
        "stock_zh_a_hist_tx",
    ]
    monkeypatch.setitem(sys.modules, "akshare", fake)
    monkeypatch.setattr(caps, "audit_tushare_capabilities", lambda probe_network=False: {"source": "tushare", "capabilities": []})

    payload = caps.audit_sources(source="all", discovery_depth="catalog", write=False)

    by_source = {}
    for item in payload["capabilities"]:
        by_source.setdefault(item["source"], set()).add(item["interface"])

    assert "stock_zh_a_hist_tx" in by_source["tencent_finance"]
    assert "stock_board_industry_name_em" in by_source["eastmoney"]
    assert "futures_main_sina" in by_source["sina_finance"]
    assert "stock_financial_cash_ths" in by_source["tonghuashun"]
    tx = next(item for item in payload["capabilities"] if item["source"] == "tencent_finance" and item["interface"] == "stock_zh_a_hist_tx")
    assert tx["discovery_status"] == "discovered"
    assert tx["discovery_scope"] == "package_backend_mapping"
    assert tx["probe_status"] == "not_probed"
    assert tx["sample_probe"]["status"] == "not_probed"
    assert tx["integration_status"] != "project_integrated"
    assert payload["summary"]["discovered_count"] >= 4
    assert payload["summary"]["sample_probed_count"] == 0


def test_sample_discovery_only_records_allowlisted_probe_metadata(monkeypatch):
    from data.ingestion import source_capabilities as caps

    def fake_probe(capability):
        if capability["interface"] != "qt_gtimg_realtime_quote":
            return None
        return {
            "status": "ok",
            "row_count": 1,
            "field_sample": ["symbol", "name", "last_price"],
            "message": "sample parsed",
        }

    monkeypatch.setattr(caps, "probe_candidate_capability_sample", fake_probe)

    payload = caps.audit_sources(source="tencent_finance", discovery_depth="sample", write=False)

    quote = next(item for item in payload["capabilities"] if item["interface"] == "qt_gtimg_realtime_quote")
    kline = next(item for item in payload["capabilities"] if item["interface"] == "ifzq_fqkline")
    assert quote["discovery_status"] == "sample_probed"
    assert quote["probe_status"] == "ok"
    assert quote["sample_probe"]["row_count"] == 1
    assert quote["field_sample"] == ["symbol", "name", "last_price"]
    assert kline["probe_status"] == "not_probed"
    assert payload["summary"]["sample_probed_count"] == 1


def test_full_sample_probe_records_safe_akshare_contract_and_blocks_unsafe(monkeypatch):
    from data.ingestion import source_capabilities as caps

    fake = ModuleType("akshare")
    fake.__version__ = "9.9.9"

    def stock_zh_a_spot_em():
        """Eastmoney spot quotes."""
        return pd.DataFrame([{"symbol": "600519", "name": "贵州茅台", "price": 1550.0}])

    def stock_zh_a_hist(symbol, start_date="", end_date="", adjust=""):
        """Historical quotes require an explicit symbol and date contract."""
        return pd.DataFrame([{"date": "2026-06-12", "close": 10.0}])

    def amac_fund_info(start_page="1", end_page="2000"):
        """Default page range is too broad for a safe sample probe."""
        return pd.DataFrame([{"fund": "sample"}])

    fake.stock_zh_a_spot_em = stock_zh_a_spot_em
    fake.stock_zh_a_hist = stock_zh_a_hist
    fake.amac_fund_info = amac_fund_info
    fake.__all__ = ["stock_zh_a_spot_em", "stock_zh_a_hist", "amac_fund_info"]
    monkeypatch.setitem(sys.modules, "akshare", fake)
    monkeypatch.setattr(caps, "audit_tushare_capabilities", lambda probe_network=False: {"source": "tushare", "capabilities": []})

    payload = caps.audit_sources(source="akshare", discovery_depth="full-sample", write=False)

    spot = next(item for item in payload["capabilities"] if item["interface"] == "stock_zh_a_spot_em")
    hist = next(item for item in payload["capabilities"] if item["interface"] == "stock_zh_a_hist")
    unbounded = next(item for item in payload["capabilities"] if item["interface"] == "amac_fund_info")
    assert spot["probe_status"] == "ok"
    assert spot["probe_contract_id"] == "akshare.no_arg_dataframe"
    assert spot["row_count"] == 1
    assert spot["field_sample"] == ["name", "price", "symbol"]
    assert spot["elapsed_ms"] >= 0
    assert hist["probe_status"] == "blocked"
    assert hist["probe_block_reason"] == "missing_probe_contract"
    assert unbounded["probe_status"] == "blocked"
    assert unbounded["probe_block_reason"] == "unsafe_unbounded_query"
    assert payload["summary"]["probe_statuses"]["ok"] == 1
    assert payload["summary"]["probe_blocked_count"] >= 1


def test_full_sample_dry_run_marks_probe_plan_without_calling_provider(monkeypatch):
    from data.ingestion import source_capabilities as caps

    fake = ModuleType("akshare")
    fake.__version__ = "9.9.9"

    def stock_zh_a_spot_em():
        raise AssertionError("dry-run must not call provider functions")

    fake.stock_zh_a_spot_em = stock_zh_a_spot_em
    fake.__all__ = ["stock_zh_a_spot_em"]
    monkeypatch.setitem(sys.modules, "akshare", fake)
    monkeypatch.setattr(caps, "audit_tushare_capabilities", lambda probe_network=False: {"source": "tushare", "capabilities": []})

    payload = caps.audit_sources(source="akshare", discovery_depth="full-sample", dry_run=True, write=False)

    spot = next(item for item in payload["capabilities"] if item["interface"] == "stock_zh_a_spot_em")
    assert spot["probe_status"] == "planned"
    assert spot["probe_contract_id"] == "akshare.no_arg_dataframe"
    assert spot["probe_block_reason"] == ""
    assert payload["summary"]["probe_planned_count"] == 1


def test_full_sample_resume_skips_completed_probe_run(tmp_path, monkeypatch):
    from data.ingestion import source_capabilities as caps
    from data.storage.datahub import DataHub

    hub = DataHub(runtime_root=tmp_path / "var", artifact_root=tmp_path / "var" / "artifacts")
    fake = ModuleType("akshare")
    fake.__version__ = "9.9.9"
    calls = []

    def stock_zh_a_spot_em():
        calls.append("called")
        return pd.DataFrame([{"symbol": "600519", "price": 1550.0}])

    fake.stock_zh_a_spot_em = stock_zh_a_spot_em
    fake.__all__ = ["stock_zh_a_spot_em"]
    monkeypatch.setitem(sys.modules, "akshare", fake)
    monkeypatch.setattr(caps, "audit_tushare_capabilities", lambda probe_network=False: {"source": "tushare", "capabilities": []})

    first = caps.audit_sources(source="akshare", discovery_depth="full-sample", write=True, hub=hub)
    second = caps.audit_sources(source="akshare", discovery_depth="full-sample", resume=True, write=True, hub=hub)

    assert calls == ["called"]
    first_spot = next(item for item in first["capabilities"] if item["interface"] == "stock_zh_a_spot_em")
    second_spot = next(item for item in second["capabilities"] if item["interface"] == "stock_zh_a_spot_em")
    assert first_spot["probe_status"] == "ok"
    assert second_spot["probe_status"] == "ok"
    assert second_spot["sample_probe"]["resume_skipped"] is True
    run_dir = hub.artifact_dir("data-sources") / "probe-runs"
    assert any(path.name.endswith(".json") for path in run_dir.iterdir())


def test_tushare_offline_audit_uses_capability_shape_without_secret(monkeypatch):
    from data.ingestion import source_capabilities as caps

    monkeypatch.setattr(caps, "secret_status", lambda name: {"name": name, "status": "missing", "present": False})

    result = caps.audit_tushare_capabilities(probe_network=False)

    assert result["source"] == "tushare"
    assert result["token"]["status"] == "missing"
    assert result["capabilities"]
    daily = next(item for item in result["capabilities"] if item["interface"] == "daily")
    assert daily["requires_token"] is True
    assert daily["access_status"] == "not_probed"
    assert daily["probe_strategy"] == "offline_catalog"


def test_diff_registry_reports_capability_and_registry_mismatches():
    from data.ingestion.source_capabilities import diff_capabilities_with_registry

    capabilities = [
        {
            "source": "akshare",
            "interface": "stock_zh_a_daily",
            "mapped_dimensions": ["ohlcv_daily"],
            "integration_status": "project_integrated",
            "frequency": "daily",
            "data_domain": "market_price",
        },
        {
            "source": "akshare",
            "interface": "stock_board_industry_name_em",
            "mapped_dimensions": [],
            "integration_status": "unmapped",
            "frequency": "event",
            "data_domain": "reference",
        },
    ]
    dimensions = [
        {"key": "ohlcv_daily", "source": "akshare", "freq": "daily", "status": "available"},
        {"key": "stock_basic", "source": "tushare_free", "freq": "event", "status": "available"},
        {"key": "direct_tx", "source": "tencent_finance", "freq": "daily", "status": "available"},
    ]

    diff = diff_capabilities_with_registry(capabilities, dimensions)

    assert diff["summary"]["capability_unmapped_count"] == 1
    assert diff["summary"]["registry_missing_source_count"] == 2
    missing_keys = {item["dimension"] for item in diff["registry_missing_source"]}
    assert missing_keys == {"stock_basic", "direct_tx"}
    assert diff["capability_unmapped"][0]["interface"] == "stock_board_industry_name_em"


def test_diff_registry_matches_normalized_registry_source_aliases():
    from data.ingestion.source_capabilities import diff_capabilities_with_registry

    capabilities = [
        {
            "source": "tushare",
            "interface": "stock_basic",
            "mapped_dimensions": ["stock_basic"],
            "integration_status": "project_integrated",
            "frequency": "event",
            "data_domain": "reference",
        },
        {
            "source": "computed",
            "interface": "sector_performance_snapshot",
            "mapped_dimensions": ["sector_performance_snapshot"],
            "integration_status": "project_integrated",
            "frequency": "daily",
            "data_domain": "derived_snapshot",
        },
    ]
    dimensions = [
        {"key": "stock_basic", "source": "tushare_free", "freq": "event", "status": "available"},
        {"key": "sector_performance_snapshot", "source": "computed", "freq": "daily", "status": "available"},
    ]

    diff = diff_capabilities_with_registry(capabilities, dimensions)

    assert diff["registry_missing_source"] == []
    assert diff["summary"]["registry_missing_source_count"] == 0


def test_diff_registry_frequency_mismatch_only_compares_same_source():
    from data.ingestion.source_capabilities import diff_capabilities_with_registry

    capabilities = [
        {
            "source": "tushare",
            "interface": "fut_daily",
            "mapped_dimensions": ["futures_daily"],
            "integration_status": "project_integrated",
            "frequency": "daily",
            "data_domain": "market_price",
        },
        {
            "source": "sina_finance",
            "interface": "futures_main_sina",
            "mapped_dimensions": ["futures_daily"],
            "integration_status": "backend_source",
            "frequency": "event",
            "data_domain": "market_price",
        },
    ]
    dimensions = [
        {"key": "futures_daily", "source": "tushare_free", "freq": "daily", "status": "available"},
    ]

    diff = diff_capabilities_with_registry(capabilities, dimensions)

    assert diff["field_frequency_mismatch"] == []
    assert diff["summary"]["field_frequency_mismatch_count"] == 0


def test_capability_artifact_written_to_runtime_artifacts(tmp_path, monkeypatch):
    from data.ingestion import source_capabilities as caps
    from data.storage.datahub import DataHub

    hub = DataHub(runtime_root=tmp_path / "var", artifact_root=tmp_path / "var" / "artifacts")
    monkeypatch.setattr(
        caps,
        "audit_akshare_capabilities",
        lambda limit=None: {
            "source": "akshare",
            "version": "unit",
            "capabilities": [
                {
                    "source": "akshare",
                    "interface": "stock_zh_a_daily",
                    "mapped_dimensions": ["ohlcv_daily"],
                    "integration_status": "project_integrated",
                    "frequency": "daily",
                    "data_domain": "market_price",
                }
            ],
            "errors": [],
        },
    )

    payload = caps.audit_sources(source="akshare", hub=hub, write=True)

    artifact = hub.artifact_path("data-sources", "latest-akshare.json")
    assert artifact.exists()
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["status"] == "ok"
    assert saved["summary"]["capability_count"] == 1
    assert payload["latest"]["artifact_path"] == artifact.as_posix()


def test_single_source_audit_does_not_overwrite_full_capability_artifact(tmp_path, monkeypatch):
    from data.ingestion import source_capabilities as caps
    from data.storage.datahub import DataHub

    hub = DataHub(runtime_root=tmp_path / "var", artifact_root=tmp_path / "var" / "artifacts")
    canonical = hub.artifact_path("data-sources", "latest.json")
    canonical.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "ok",
                "generated_at": "2026-06-12T00:00:00Z",
                "summary": {"audited_source_count": 9, "capability_count": 9, "sources": {"tushare": 1}},
                "capabilities": [{"source": "tushare", "interface": "stock_basic", "mapped_dimensions": ["stock_basic"]}],
                "diff": {"summary": {"registry_missing_source_count": 0}, "registry_missing_source": []},
            }
        ),
        encoding="utf-8",
    )
    before = canonical.read_text(encoding="utf-8")
    monkeypatch.setattr(
        caps,
        "audit_akshare_capabilities",
        lambda limit=None: {
            "source": "akshare",
            "version": "unit",
            "capabilities": [
                {
                    "source": "akshare",
                    "interface": "stock_zh_a_daily",
                    "mapped_dimensions": ["ohlcv_daily"],
                    "integration_status": "project_integrated",
                    "frequency": "daily",
                    "data_domain": "market_price",
                }
            ],
            "errors": [],
        },
    )

    payload = caps.audit_sources(source="akshare", hub=hub, write=True)

    source_artifact = hub.artifact_path("data-sources", "latest-akshare.json")
    assert source_artifact.exists()
    assert payload["latest"]["artifact_path"] == source_artifact.as_posix()
    assert canonical.read_text(encoding="utf-8") == before
