def test_strategy_catalog_has_required_fields_for_every_enabled_strategy():
    from data.strategy.catalog import get_enabled_strategies
    from research.strategy_catalog import catalog_by_name

    catalog = catalog_by_name()
    for strategy in get_enabled_strategies():
        item = catalog[strategy["name"]]
        assert item.name == strategy["name"]
        assert item.strategy_type in {"selection", "timing", "sector_rotation", "portfolio", "risk_overlay"}
        assert item.lifecycle in {"candidate", "validated", "paper", "production", "retired"}
        assert item.data_requirements
        assert item.asset_scope
        assert item.output_contract == "StrategySignalRows"


def test_data_strategy_catalog_applies_canonical_metadata_defaults():
    from data.strategy.catalog import get_strategy, load_registry

    load_registry(force_reload=True)
    ml = get_strategy("ml_lgbm")

    assert ml is not None
    assert ml["layer"] == "auxiliary_alpha"
    assert {"features", "stock_daily", "sector", "market_regime"} <= set(ml["data_requirements"])
    assert ml["asset_scope"] == ["stock"]


def test_cross_asset_allocator_declares_full_asset_scope_and_blockers():
    from research.strategy_catalog import catalog_by_name

    item = catalog_by_name()["cross_asset_allocator"]

    assert item.strategy_type == "portfolio"
    assert item.layer == "asset_allocation"
    assert {"stock", "etf", "bond", "futures", "crypto", "cash"} <= set(item.asset_scope)
    assert item.paper_supported is True
    assert item.live_supported is False
    assert "crypto_data_stale_until_fresh_source" in item.blockers


def test_volume_confirmation_declares_actual_ohlcv_proxy_inputs():
    from data.strategy.catalog import get_strategy, load_registry

    load_registry(force_reload=True)
    strategy = get_strategy("volume_confirmation")

    assert strategy is not None
    assert strategy["data_requirements"] == ["stock_daily"]


def test_strategy_catalog_api_is_not_shadowed(monkeypatch):
    from fastapi.testclient import TestClient

    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    res = TestClient(create_app()).get("/api/strategies/catalog")

    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] == len(data["items"])
    assert any(item["name"] == "multifactor" for item in data["items"])
    cross_asset = next(item for item in data["items"] if item["name"] == "cross_asset_allocator")
    assert "crypto" in cross_asset["asset_scope"]


def test_strategy_data_coverage_api_returns_matrix(monkeypatch):
    from fastapi.testclient import TestClient

    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    res = TestClient(create_app()).get("/api/strategies/data-coverage")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["summary"]["strategy_count"] == len(data["rows"])
    assert any(item["key"] == "price" for item in data["families"])
    assert any(row["strategy"] == "multifactor" for row in data["rows"])
