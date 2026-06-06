import pandas as pd
import pytest


def test_default_strategy_stack_reframes_four_strategies_as_layers():
    from research.strategy_governance import default_strategy_roles, strategy_stack

    roles = default_strategy_roles()
    stack = strategy_stack(roles)

    assert roles["buffett"].layer == "quality_filter"
    assert roles["multifactor"].layer == "primary_alpha"
    assert roles["ml_lgbm"].layer == "auxiliary_alpha"
    assert roles["cybernetic"].layer == "risk_overlay"
    assert stack["quality_filter"] == ["buffett"]
    assert stack["primary_alpha"] == ["multifactor"]
    assert stack["risk_overlay"] == ["cybernetic"]


def test_strategy_promotion_gate_requires_oos_risk_and_ic_evidence():
    from research.strategy_governance import StrategyMetrics, evaluate_promotion

    strong = StrategyMetrics(
        cagr=0.12,
        sharpe=0.82,
        max_drawdown=-0.18,
        turnover=3.0,
        win_rate=0.55,
        ic=0.035,
        icir=0.55,
        oos_months=36,
        trades=72,
    )
    assert evaluate_promotion(strong, target_status="paper").passed

    weak = StrategyMetrics(
        cagr=0.04,
        sharpe=0.24,
        max_drawdown=-0.31,
        turnover=9.0,
        win_rate=0.48,
        ic=0.005,
        icir=0.05,
        oos_months=6,
        trades=8,
    )
    decision = evaluate_promotion(weak, target_status="paper")

    assert not decision.passed
    assert {"sharpe", "max_drawdown", "turnover", "oos_months", "trades", "ic"}.issubset(set(decision.failed_rules))


def test_factor_diagnostics_rank_ic_quantile_spread_and_correlation_clusters():
    from signals.factor_research import factor_correlation_clusters, factor_diagnostics

    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    symbols = ["a", "b", "c", "d", "e"]
    factors = pd.DataFrame(
        [[1, 2, 3, 4, 5], [1, 3, 2, 5, 4], [2, 1, 3, 4, 5], [1, 2, 4, 3, 5], [1, 2, 3, 5, 4], [2, 1, 3, 4, 5]],
        index=dates,
        columns=symbols,
    )
    fwd_returns = factors / 100.0
    factors["factor_only"] = 99
    fwd_returns["return_only"] = -0.01

    diagnostics = factor_diagnostics(factors, fwd_returns, quantiles=5, min_obs=5)

    assert diagnostics.observations == 30
    assert diagnostics.mean_ic > 0.90
    assert diagnostics.quantile_spread > 0
    assert diagnostics.monotonicity > 0.70

    factor_frame = pd.DataFrame(
        {
            "roe": [1, 2, 3, 4, 5],
            "quality": [1.1, 2.1, 3.1, 4.1, 5.1],
            "momentum": [5, 4, 3, 2, 1],
            "size": [2, 2, 3, 3, 4],
        }
    )
    clusters = factor_correlation_clusters(factor_frame, threshold=0.95)

    assert any({"roe", "quality"}.issubset(set(cluster)) for cluster in clusters)


def test_constrained_portfolio_constructor_caps_sector_and_single_name_weight():
    from pipeline.portfolio import ConstrainedPortfolioConstructor
    from pipeline.types import AlphaSignal, PipelineContext

    signals = [
        AlphaSignal("hold1", "multifactor", "hold", 0.95, 95),
        AlphaSignal("bank1", "multifactor", "buy", 0.90, 90),
        AlphaSignal("bank2", "multifactor", "buy", 0.85, 85),
        AlphaSignal("tech1", "multifactor", "buy", 0.80, 80),
        AlphaSignal("health1", "multifactor", "buy", 0.70, 70),
    ]
    ctx = PipelineContext(
        cash=100_000,
        prices={"hold1": 12, "bank1": 10, "bank2": 10, "tech1": 20, "health1": 25},
    )
    constructor = ConstrainedPortfolioConstructor(
        max_positions=4,
        position_pct=0.80,
        max_single_weight=0.20,
        max_sector_weight=0.30,
        sector_map={"bank1": "银行", "bank2": "银行", "tech1": "科技", "health1": "医药"},
    )

    targets = constructor.construct(signals, ctx)
    buy_targets = [target for target in targets if target.delta_shares > 0]

    assert [target.symbol for target in buy_targets] == ["bank1", "tech1", "health1"]
    assert all(target.target_weight <= 0.20 for target in buy_targets)
    assert sum(target.target_weight for target in buy_targets if target.symbol.startswith("bank")) <= 0.30


def test_constrained_portfolio_constructor_does_not_collapse_missing_sector_metadata():
    from pipeline.portfolio import ConstrainedPortfolioConstructor
    from pipeline.types import AlphaSignal, PipelineContext

    signals = [
        AlphaSignal("stock1", "multifactor", "buy", 0.90, 90),
        AlphaSignal("stock2", "multifactor", "buy", 0.85, 85),
        AlphaSignal("stock3", "multifactor", "buy", 0.80, 80),
        AlphaSignal("stock4", "multifactor", "buy", 0.75, 75),
    ]
    ctx = PipelineContext(
        cash=100_000,
        prices={"stock1": 10, "stock2": 10, "stock3": 10, "stock4": 10},
    )
    constructor = ConstrainedPortfolioConstructor(
        max_positions=4,
        position_pct=0.80,
        max_single_weight=0.20,
        max_sector_weight=0.30,
    )

    targets = constructor.construct(signals, ctx)

    assert [target.symbol for target in targets if target.delta_shares > 0] == [
        "stock1",
        "stock2",
        "stock3",
        "stock4",
    ]


def test_strategy_governance_api_exposes_roles_before_detail_route(monkeypatch):
    from fastapi.testclient import TestClient
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    res = TestClient(create_app()).get("/api/strategies/governance")

    assert res.status_code == 200
    data = res.json()
    assert data["stack"]["primary_alpha"] == ["multifactor"]
    assert "paper" in data["promotion_rules"]


def test_ml_strategy_is_paper_until_oos_gate_passes():
    from data.strategy.catalog import get_status

    assert get_status("ml_lgbm") == "paper"
