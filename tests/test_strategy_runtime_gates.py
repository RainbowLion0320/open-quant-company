def test_production_mode_excludes_candidate_strategies(monkeypatch):
    from data.strategy_plugins import iter_strategy_plugins

    fake_registry = [
        {
            "name": "prod_alpha",
            "label": "Prod",
            "runner": "signals.runners:compute_multifactor",
            "signal_name": "prod_alpha",
            "enabled": True,
            "status": "production",
        },
        {
            "name": "candidate_alpha",
            "label": "Candidate",
            "runner": "signals.runners:compute_multifactor",
            "signal_name": "candidate_alpha",
            "enabled": True,
            "status": "candidate",
        },
    ]
    monkeypatch.setattr("data.strategy_plugins.get_enabled_strategies", lambda: fake_registry)
    monkeypatch.setattr(
        "data.strategy_plugins.get_strategy",
        lambda name: next((s for s in fake_registry if s["name"] == name), None),
    )
    monkeypatch.setattr("data.strategy_plugins.list_strategy_names", lambda: [s["name"] for s in fake_registry])

    names = [plugin.name for plugin in iter_strategy_plugins("all", mode="production")]

    assert names == ["prod_alpha"]


def test_research_mode_can_include_candidate_strategies(monkeypatch):
    from data.strategy_plugins import iter_strategy_plugins

    fake_registry = [
        {
            "name": "prod_alpha",
            "label": "Prod",
            "runner": "signals.runners:compute_multifactor",
            "signal_name": "prod_alpha",
            "enabled": True,
            "status": "production",
        },
        {
            "name": "candidate_alpha",
            "label": "Candidate",
            "runner": "signals.runners:compute_multifactor",
            "signal_name": "candidate_alpha",
            "enabled": True,
            "status": "candidate",
        },
    ]
    monkeypatch.setattr("data.strategy_plugins.get_enabled_strategies", lambda: fake_registry)
    monkeypatch.setattr(
        "data.strategy_plugins.get_strategy",
        lambda name: next((s for s in fake_registry if s["name"] == name), None),
    )
    monkeypatch.setattr("data.strategy_plugins.list_strategy_names", lambda: [s["name"] for s in fake_registry])

    names = [plugin.name for plugin in iter_strategy_plugins("all", mode="research")]

    assert names == ["prod_alpha", "candidate_alpha"]


def test_invalid_strategy_runtime_mode_is_rejected():
    from data.strategy_plugins import iter_strategy_plugins

    try:
        list(iter_strategy_plugins("all", mode="paper"))
    except ValueError as exc:
        assert "Invalid strategy runtime mode" in str(exc)
    else:
        raise AssertionError("invalid runtime mode should fail")


def test_strategy_run_api_accepts_research_mode(monkeypatch):
    from fastapi.testclient import TestClient

    from web.api.app import create_app

    captured = {}

    async def fake_run_strategy_async(strategy, limit=0, params=None, mode="production"):
        captured["strategy"] = strategy
        captured["mode"] = mode
        return "unit-job"

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setattr("web.api.jobs.run_strategy_async", fake_run_strategy_async)

    res = TestClient(create_app()).post(
        "/api/strategies/run",
        json={"strategy": "trend_following", "mode": "research", "limit": 5},
    )

    assert res.status_code == 200
    assert captured == {"strategy": "trend_following", "mode": "research"}
