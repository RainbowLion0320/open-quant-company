def test_strategy_evaluation_requires_strong_baselines():
    from research.strategy_evaluation import required_baselines

    assert required_baselines() == [
        "buy_and_hold",
        "fixed_weight",
        "ma_timing",
        "trend_only",
        "trend_breadth",
        "current_champion",
    ]


def test_evaluation_summary_blocks_missing_oos():
    from research.strategy_evaluation import StrategyEvaluation, promotion_ready

    eval_result = StrategyEvaluation(
        name="trend_following",
        cagr=0.15,
        sharpe=0.9,
        max_drawdown=-0.18,
        turnover=3.2,
        oos_months=6,
        trades=40,
        baseline_win_rate=0.8,
        regime_coverage={"bull": 0.7, "sideways": 0.5, "bear": 0.2},
    )

    decision = promotion_ready(eval_result, target_status="paper")

    assert not decision.passed
    assert "oos_months" in decision.failed_rules


def test_strategy_evaluation_api_is_not_shadowed(monkeypatch):
    from fastapi.testclient import TestClient

    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    res = TestClient(create_app()).get("/api/strategies/evaluation")

    assert res.status_code == 200
    assert res.json()["status"] == "research_required"


def test_list_evidence_artifacts_includes_missing_catalog_strategies(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from research.strategy_evaluation import list_evidence_artifacts

    monkeypatch.setattr(
        "research.strategy_evaluation.catalog_items",
        lambda: [
            SimpleNamespace(name="trend_following"),
            SimpleNamespace(name="sector_rotation"),
        ],
        raising=False,
    )

    rows = list_evidence_artifacts(tmp_path)
    by_name = {row["strategy"]: row for row in rows}

    assert set(by_name) == {"trend_following", "sector_rotation"}
    assert by_name["trend_following"]["exists"] is False
    assert by_name["trend_following"]["promotion_decision"] == "missing"


def test_list_evidence_artifacts_merges_existing_artifact_with_catalog(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace

    from research.strategy_evaluation import list_evidence_artifacts

    monkeypatch.setattr(
        "research.strategy_evaluation.catalog_items",
        lambda: [
            SimpleNamespace(name="trend_following"),
            SimpleNamespace(name="sector_rotation"),
        ],
        raising=False,
    )
    (tmp_path / "trend_following.json").write_text(
        json.dumps({
            "strategy": "trend_following",
            "generated_at": "2026-05-30T10:00:00",
            "promotion_decision": {"passed": False},
            "oos": {"months": 12},
            "baselines": {"buy_and_hold": {}, "current_champion": {}},
        }),
        encoding="utf-8",
    )

    rows = list_evidence_artifacts(tmp_path)
    by_name = {row["strategy"]: row for row in rows}

    assert by_name["trend_following"]["exists"] is True
    assert by_name["trend_following"]["promotion_decision"] == "blocked"
    assert by_name["trend_following"]["baseline_count"] == 2
    assert by_name["sector_rotation"]["exists"] is False
