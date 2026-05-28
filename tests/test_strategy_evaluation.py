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
