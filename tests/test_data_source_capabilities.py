from __future__ import annotations

import json
import sys
from types import ModuleType


def test_source_catalog_separates_external_capabilities_from_project_registry():
    from data.ingestion.source_capabilities import SOURCE_IDS, source_catalog
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
