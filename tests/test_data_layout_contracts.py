from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def test_datahub_defaults_to_var_runtime_layout(monkeypatch):
    from data.storage.datahub import DataHub, reset_datahub

    monkeypatch.delenv("ASTROLABE_VAR", raising=False)
    reset_datahub()

    hub = DataHub(create=False)
    root = Path(__file__).resolve().parents[1]

    assert hub.runtime_dir() == root / "var"
    assert hub.store_root == root / "var" / "store"
    assert hub.cache_root == root / "var" / "cache"
    assert hub.artifact_dir("backtests") == root / "var" / "artifacts" / "backtests"
    assert hub.db_path("quant_results.duckdb") == root / "var" / "db" / "quant_results.duckdb"


def test_datahub_runtime_env_is_single_canonical_override(tmp_path, monkeypatch):
    from data.storage.datahub import DataHub, reset_datahub

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ASTROLABE_STORE", str(tmp_path / "custom-store"))
    monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "custom-cache"))
    monkeypatch.setenv("ASTROLABE_ARTIFACTS", str(tmp_path / "custom-artifacts"))
    monkeypatch.setenv("ASTROLABE_DB", str(tmp_path / "custom-db"))
    reset_datahub()

    hub = DataHub(project_root=tmp_path, create=False)

    assert hub.runtime_dir() == tmp_path / "runtime"
    assert hub.store_root == tmp_path / "runtime" / "store"
    assert hub.cache_root == tmp_path / "runtime" / "cache"
    assert hub.artifact_dir("models") == tmp_path / "runtime" / "artifacts" / "models"
    assert hub.db_path("x.duckdb") == tmp_path / "runtime" / "db" / "x.duckdb"


def test_paper_trading_store_dir_tracks_runtime_env_after_datahub_reset(tmp_path, monkeypatch):
    import broker.persistence as persistence
    from data.storage.datahub import reset_datahub

    runtime = tmp_path / "runtime"
    monkeypatch.setenv("ASTROLABE_VAR", str(runtime))
    reset_datahub()

    assert persistence._resolve_store() == runtime / "store" / "paper"


def test_datahub_explicit_roots_override_runtime_env(tmp_path, monkeypatch):
    from data.storage.datahub import DataHub, reset_datahub

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    reset_datahub()

    hub = DataHub(
        project_root=tmp_path,
        store_root=tmp_path / "custom-store",
        cache_root=tmp_path / "custom-cache",
        artifact_root=tmp_path / "custom-artifacts",
        db_root=tmp_path / "custom-db",
        create=False,
    )

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


def test_data_root_contains_only_init_and_canonical_packages():
    root = Path(__file__).resolve().parents[1] / "data"
    root_files = sorted(p.name for p in root.iterdir() if p.is_file() and p.suffix == ".py")
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


def test_data_layout_migration_tool_is_removed():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "scripts" / "migrate_data_layout.py").exists()
    assert not (root / "docs" / "operations" / "data-layout-migration.md").exists()


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


def test_removed_data_imports_are_absent():
    removed_modules = [
        ".".join(("data", "datahub")),
        ".".join(("data", "fetcher")),
        ".".join(("data", "feature_store")),
        ".".join(("data", "price_service")),
        ".".join(("data", "strategy_plugins")),
        ".".join(("data", "assets", "stock")),
        ".".join(("data", "fetchers", "base")),
        ".".join(("data", "sector_pipeline", "membership")),
        ".".join(("data", "market", "sectors")),
        ".".join(("data", "llm", "deepseek_usage")),
    ]
    for name in removed_modules:
        sys.modules.pop(name, None)
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)
