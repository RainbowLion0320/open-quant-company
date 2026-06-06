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
        assert item.output_contract == "StrategySignalRows"


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
