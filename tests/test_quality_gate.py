"""Tests for data/quality.py — DataQualityGate freshness/completeness/consistency checks."""

from datetime import date, timedelta

import pandas as pd
import numpy as np
import pytest


class TestDataQualityGate:
    def test_fresh_dimension_with_recent_data(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")
        hub.write_parquet(
            pd.DataFrame({
                "date": ["2026-05-21", "2026-05-20", "2026-05-19"],
                "open": [10, 11, 12],
                "high": [11, 12, 13],
                "low": [9, 10, 11],
                "close": [10.5, 11.5, 12.5],
                "volume": [1000, 1100, 1200],
            }),
            hub.dimension_path("ohlcv_daily", symbol="000001"),
            producer="test",
        )

        from data.quality.quality import DataQualityGate
        gate = DataQualityGate(today=date(2026, 5, 21), hub=hub)
        report = gate.check_dimension("ohlcv_daily", symbol="000001")

        assert report.status == "fresh"
        assert report.health_score >= 80
        assert report.row_count == 3
        assert report.null_pct == 0
        assert report.date_max == "2026-05-21"
        assert report.freshness_days == 0
        assert not report.issues

    def test_stale_dimension_past_sla(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")
        hub.write_parquet(
            pd.DataFrame({
                "date": ["2026-05-07", "2026-05-06"],
                "open": [10, 11], "high": [11, 12], "low": [9, 10],
                "close": [10.5, 11.5], "volume": [1000, 1100],
            }),
            hub.dimension_path("ohlcv_daily", symbol="000001"),
            producer="test",
        )

        from data.quality.quality import DataQualityGate
        gate = DataQualityGate(today=date(2026, 5, 21), hub=hub)
        report = gate.check_dimension("ohlcv_daily", symbol="000001")

        assert report.status == "stale"
        assert report.freshness_days == 14
        assert report.sla_days == 5
        assert report.health_score < 80
        assert any("Stale" in i for i in report.issues)

    def test_missing_dimension_no_data(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")

        from data.quality.quality import DataQualityGate
        gate = DataQualityGate(today=date(2026, 5, 21), hub=hub)
        report = gate.check_dimension("dividend")

        assert report.status == "missing"
        assert report.health_score == 0
        assert "No data found" in report.issues

    def test_unknown_dimension(self):
        from data.quality.quality import DataQualityGate
        gate = DataQualityGate()
        report = gate.check_dimension("nonexistent_dimension_xyz")

        assert report.status == "error"
        assert "Unknown dimension" in report.issues[0]

    def test_skipped_planned_dimension(self):
        from data.quality.quality import DataQualityGate
        gate = DataQualityGate()
        report = gate.check_dimension("crypto_daily")

        assert report.status == "skipped"
        assert report.health_score == 100

    def test_high_null_ratio_detected(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")

        df = pd.DataFrame({
            "date": ["2026-05-21", "2026-05-20"],
            "open": [10, None],
            "high": [None, None],
            "low": [None, 10],
            "close": [10.5, None],
            "volume": [None, None],
        })
        hub.write_parquet(df, hub.dimension_path("ohlcv_daily", symbol="000001"), producer="test")

        from data.quality.quality import DataQualityGate
        gate = DataQualityGate(today=date(2026, 5, 21), hub=hub)
        report = gate.check_dimension("ohlcv_daily", symbol="000001")

        assert report.null_pct > 40
        assert report.health_score <= 70
        assert any("High null" in i for i in report.issues)

    def test_pre_scan_gate_all_fresh(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")

        write_daily(hub, "000001")
        write_financial(hub, "000001")

        from data.quality.quality import pre_scan_gate
        ok, reports = pre_scan_gate(
            required_dims=["ohlcv_daily", "financial_summary"],
            symbol="000001",
            hub=hub,
            today=date(2026, 5, 21),
        )

        assert ok
        assert all(r.status == "fresh" for r in reports)

    def test_schema_mismatch_blocks_even_when_recent(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")
        hub.write_parquet(
            pd.DataFrame({
                "date": ["2026-05-21"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                # close is required by the ohlcv_daily contract.
                "volume": [1000.0],
            }),
            hub.dimension_path("ohlcv_daily", symbol="000001"),
            producer="test",
        )

        from data.quality.quality import DataQualityGate, pre_scan_gate
        gate = DataQualityGate(today=date(2026, 5, 21), hub=hub)
        report = gate.check_dimension("ohlcv_daily", symbol="000001")

        assert report.status == "schema_mismatch"
        assert report.is_blocking
        assert any("Required column 'close'" in i for i in report.issues)

        ok, reports = pre_scan_gate(
            required_dims=["ohlcv_daily"],
            symbol="000001",
            hub=hub,
        )
        assert not ok
        assert reports[0].status == "schema_mismatch"

    def test_pre_scan_gate_stale_blocks(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")

        hub.write_parquet(
            pd.DataFrame({
                "date": ["2026-04-01"],
                "open": [10], "high": [11], "low": [9],
                "close": [10.5], "volume": [1000],
            }),
            hub.dimension_path("ohlcv_daily", symbol="000001"),
            producer="test",
        )

        from data.quality.quality import pre_scan_gate
        ok, reports = pre_scan_gate(
            required_dims=["ohlcv_daily"],
            symbol="000001",
            hub=hub,
        )

        assert not ok
        assert reports[0].status == "stale"

    def test_pre_scan_gate_strict_raises(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")

        hub.write_parquet(
            pd.DataFrame({
                "date": ["2026-04-01"],
                "open": [10], "high": [11], "low": [9],
                "close": [10.5], "volume": [1000],
            }),
            hub.dimension_path("ohlcv_daily", symbol="000001"),
            producer="test",
        )

        from data.quality.quality import pre_scan_gate
        with pytest.raises(RuntimeError, match="quality gate FAILED"):
            pre_scan_gate(required_dims=["ohlcv_daily"], symbol="000001", strict=True, hub=hub)

    def test_check_critical_returns_all_available(self):
        from data.quality.quality import DataQualityGate
        gate = DataQualityGate()
        reports = gate.check_critical()

        assert len(reports) > 0
        for r in reports:
            assert r.dimension
            assert r.status in ("fresh", "stale", "missing", "error", "skipped", "schema_mismatch")
            assert 0 <= r.health_score <= 100

    def test_summary_report_structure(self):
        from data.quality.quality import DataQualityGate
        gate = DataQualityGate()
        summary = gate.summary_report()

        assert "checked_at" in summary
        assert "total_dimensions" in summary
        assert "avg_health_score" in summary
        assert "all_critical_fresh" in summary
        assert "worst_offenders" in summary
        assert "details" in summary
        assert isinstance(summary["details"], list)

    def test_freshness_score_decay(self, tmp_path, monkeypatch):
        from data.storage.datahub import DataHub, reset_datahub
        from data.storage.dimensions import reset_registry

        store = tmp_path / "store"
        monkeypatch.setenv("ASTROLABE_STORE", str(store))
        monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
        reset_datahub()
        reset_registry()

        hub = DataHub(store_root=store, cache_root=tmp_path / "cache")

        days_ago = 10
        last_date = date(2026, 5, 21) - timedelta(days=days_ago)
        hub.write_parquet(
            pd.DataFrame({
                "date": [last_date.isoformat()],
                "open": [10], "high": [11], "low": [9],
                "close": [10.5], "volume": [1000],
            }),
            hub.dimension_path("ohlcv_daily", symbol="000001"),
            producer="test",
        )

        from data.quality.quality import DataQualityGate
        gate = DataQualityGate(today=date(2026, 5, 21), hub=hub)
        report = gate.check_dimension("ohlcv_daily", symbol="000001")

        assert report.freshness_days == days_ago
        # health_score = freshness*0.5 + completeness*0.3 + consistency*0.2
        # freshness = max(0, 100 - (10-5)*5) = 75, completeness=100, consistency=100
        expected = round(75 * 0.5 + 100 * 0.3 + 100 * 0.2, 1)
        assert report.health_score == expected


def write_daily(hub, symbol: str) -> None:
    hub.write_parquet(
        pd.DataFrame({
            "date": ["2026-05-21", "2026-05-20", "2026-05-19"],
            "open": [10, 11, 12], "high": [11, 12, 13],
            "low": [9, 10, 11], "close": [10.5, 11.5, 12.5],
            "volume": [1000, 1100, 1200],
        }),
        hub.dimension_path("ohlcv_daily", symbol=symbol),
        producer="test",
    )


def write_financial(hub, symbol: str) -> None:
    hub.write_parquet(
        pd.DataFrame({
            "报告期": ["2026-05-21"],
            "净利润": ["120亿"],
            "净利润同比增长率": ["8%"],
            "营业总收入": ["960亿"],
            "营业总收入同比增长率": ["6%"],
            "基本每股收益": ["2.5"],
            "每股净资产": ["15.0"],
            "销售净利率": ["12%"],
            "销售毛利率": ["35%"],
            "净资产收益率": ["15%"],
        }),
        hub.dimension_path("financial_summary", symbol=symbol),
        producer="test",
    )
