from __future__ import annotations

import json
import importlib
import subprocess
import sys
from pathlib import Path

import pytest


def test_datahub_defaults_to_var_runtime_layout(monkeypatch):
    from data.storage.datahub import DataHub, reset_datahub

    for name in (
        "ASTROLABE_VAR",
        "ASTROLABE_STORE",
        "ASTROLABE_CACHE",
        "ASTROLABE_ARTIFACTS",
        "ASTROLABE_DB",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_datahub()

    hub = DataHub(create=False)
    root = Path(__file__).resolve().parents[1]

    assert hub.runtime_dir() == root / "var"
    assert hub.store_root == root / "var" / "store"
    assert hub.cache_root == root / "var" / "cache"
    assert hub.artifact_dir("backtests") == root / "var" / "artifacts" / "backtests"
    assert hub.db_path("quant_results.duckdb") == root / "var" / "db" / "quant_results.duckdb"
    assert hub.migration_dir() == root / "var" / "migration"


def test_datahub_runtime_env_overrides(tmp_path, monkeypatch):
    from data.storage.datahub import DataHub, reset_datahub

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ASTROLABE_STORE", str(tmp_path / "custom-store"))
    monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "custom-cache"))
    monkeypatch.setenv("ASTROLABE_ARTIFACTS", str(tmp_path / "custom-artifacts"))
    monkeypatch.setenv("ASTROLABE_DB", str(tmp_path / "custom-db"))
    reset_datahub()

    hub = DataHub(project_root=tmp_path, create=False)

    assert hub.runtime_dir() == tmp_path / "runtime"
    assert hub.store_root == tmp_path / "custom-store"
    assert hub.cache_root == tmp_path / "custom-cache"
    assert hub.artifact_dir("models") == tmp_path / "custom-artifacts" / "models"
    assert hub.db_path("x.duckdb") == tmp_path / "custom-db" / "x.duckdb"


def test_data_registry_cache_patterns_are_relative_to_store_root():
    from data.storage.dimensions import get_registry

    for dimension in get_registry().get_enabled():
        cache = str(dimension.cache or "")
        assert cache
        assert not Path(cache).is_absolute()
        assert not cache.startswith(("var/store", "data/store"))
        assert ".." not in Path(cache).parts


def test_data_layout_migration_dry_run_does_not_move_files(tmp_path):
    _write_legacy_layout(tmp_path)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/migrate_data_layout.py",
            "--root",
            str(tmp_path),
            "--dry-run",
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    targets = {item["target"] for item in payload["items"]}

    assert str(tmp_path / "var/store") in targets
    assert str(tmp_path / "var/cache") in targets
    assert str(tmp_path / "var/artifacts/backtests/backtest_ml_lgbm.pkl") in targets
    assert (tmp_path / "data/store/scan_meta.parquet").exists()
    assert (tmp_path / "data/backtest_ml_lgbm.pkl").exists()
    assert not (tmp_path / "var/migration").exists()


def test_data_layout_migration_apply_moves_files_and_records_manifest(tmp_path):
    _write_legacy_layout(tmp_path)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/migrate_data_layout.py",
            "--root",
            str(tmp_path),
            "--apply",
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert (tmp_path / "var/store/scan_meta.parquet").exists()
    assert (tmp_path / "var/cache/api/cache.parquet").exists()
    assert (tmp_path / "var/artifacts/backtests/backtest_ml_lgbm.pkl").exists()
    assert (tmp_path / "var/cache/backtest/price_matrix_qfq_demo.pkl").exists()
    assert (tmp_path / "var/artifacts/tournaments/tournament.json").exists()
    assert (tmp_path / "var/artifacts/models/lgbm_best.pkl").exists()
    assert (tmp_path / "var/db/quant_results.duckdb").exists()
    assert (tmp_path / "var/cache/runtime/financials_progress.json").exists()
    assert not (tmp_path / "data/backtest_ml_lgbm.pkl").exists()

    manifest_path = Path(payload["manifest_path"])
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(item["status"] == "moved" for item in manifest["items"])
    assert any(item["source"].endswith("data/backtest_ml_lgbm.pkl") and item["sha256"] for item in manifest["items"])


def test_data_layout_migration_apply_does_not_overwrite_existing_targets(tmp_path):
    source = tmp_path / "data" / "backtest_ml_lgbm.pkl"
    target = tmp_path / "var" / "artifacts" / "backtests" / "backtest_ml_lgbm.pkl"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    target.write_text("target", encoding="utf-8")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/migrate_data_layout.py",
            "--root",
            str(tmp_path),
            "--apply",
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert source.exists()
    assert target.read_text(encoding="utf-8") == "target"
    item = next(item for item in payload["items"] if item["source"].endswith("data/backtest_ml_lgbm.pkl"))
    assert item["status"] == "conflict"
    assert item["sha256"]


def test_data_root_contains_only_init_and_canonical_packages():
    root = Path(__file__).resolve().parents[1] / "data"
    root_files = sorted(p.name for p in root.iterdir() if p.is_file())
    forbidden_legacy_packages = ["assets", "fetchers", "sector_pipeline"]
    forbidden_suffixes = {".pkl", ".db", ".duckdb"}
    forbidden_files = [
        p
        for p in root.iterdir()
        if p.is_file() and (p.suffix in forbidden_suffixes or p.name == ".financials_progress.json")
    ]
    forbidden_dirs = [p for p in ("store", "cache", "tournament", "models") if (root / p).exists()]

    assert root_files == ["__init__.py"]
    assert [name for name in forbidden_legacy_packages if (root / name).exists()] == []
    assert forbidden_files == []
    assert forbidden_dirs == []


def test_canonical_data_imports_are_available():
    from data.storage.datahub import DataHub
    from data.storage.dimensions import DataRegistry
    from data.ingestion.fetcher import get_stock_daily
    from data.market.price_service import get_stock_prices
    from data.features.feature_store import FeatureStoreBuilder
    from data.quality.cleaner import DataCleaner
    from data.ops.cron_logger import cron_run
    from data.rates.risk_free_rates import RiskFreeRateProvider

    assert DataHub
    assert DataRegistry
    assert get_stock_daily
    assert get_stock_prices
    assert FeatureStoreBuilder
    assert DataCleaner
    assert cron_run
    assert RiskFreeRateProvider


def test_legacy_data_imports_are_removed():
    legacy_modules = [
        ".".join(("data", "datahub")),
        ".".join(("data", "fetcher")),
        ".".join(("data", "feature_store")),
        ".".join(("data", "price_service")),
        ".".join(("data", "strategy_plugins")),
        ".".join(("data", "assets", "stock")),
        ".".join(("data", "fetchers", "base")),
        ".".join(("data", "sector_pipeline", "membership")),
    ]
    for name in legacy_modules:
        sys.modules.pop(name, None)
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)


def _write_legacy_layout(root: Path) -> None:
    files = {
        "data/store/scan_meta.parquet": "store",
        "data/cache/api/cache.parquet": "cache",
        "data/backtest_ml_lgbm.pkl": "backtest",
        "data/price_matrix_qfq_demo.pkl": "matrix",
        "data/tournament/tournament.json": "{}",
        "data/models/lgbm_best.pkl": "model",
        "data/quant_results.duckdb": "db",
        "data/.financials_progress.json": "{}",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
