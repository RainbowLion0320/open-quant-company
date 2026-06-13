"""Contract tests for pipeline stages — Alpha→Portfolio→Risk→Execution."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from pipeline.types import (
    AlphaSignal, PortfolioTarget, OrderIntent, FillResult, PipelineContext,
)
from pipeline.alpha import StrategyAlphaAdapter
from pipeline.portfolio import EqualWeightConstructor, InverseVolatilityConstructor
from pipeline.risk import RiskAdjuster
from pipeline.execution import ExecutionRouter
from pipeline.scheduler import RebalanceScheduler, RebalanceConfig


class TestAlphaSignal:
    def test_confidence_bounds(self):
        s = AlphaSignal("000001", "test", "buy", 0.5, 50)
        assert s.confidence == 0.5
        assert s.direction == "buy"

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValueError):
            AlphaSignal("000001", "test", "buy", 1.5, 50)

    def test_sort_by_score_descending(self):
        signals = [
            AlphaSignal("a", "s", "buy", 0.5, 50),
            AlphaSignal("b", "s", "buy", 0.9, 90),
            AlphaSignal("c", "s", "buy", 0.3, 30),
        ]
        signals.sort(key=lambda s: s.score, reverse=True)
        assert signals[0].symbol == "b"
        assert signals[2].symbol == "c"


class TestStrategyAlphaAdapter:
    def test_reuses_scores_between_signal_generation_and_score_panel(self):
        calls: list[tuple[str, int, str]] = []
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame(
            {
                "AAA": [10.0, 10.5, 11.0],
                "BBB": [20.0, 20.2, 20.1],
            },
            index=dates,
        )

        def scorer(symbol: str, series: pd.Series, date_idx: int, regime: str) -> float:
            calls.append((symbol, date_idx, regime))
            return 80.0 if symbol == "AAA" else 20.0

        alpha = StrategyAlphaAdapter("unit_alpha", "Unit Alpha", scorer, min_score=30)

        signals = alpha.generate_alpha(["AAA", "BBB"], prices, 2, "sideways")
        panel = alpha.generate_score_panel(["AAA", "BBB"], prices, 2, "sideways")

        assert [(signal.symbol, signal.score) for signal in signals] == [("AAA", 80.0)]
        assert {row["symbol"] for row in panel} == {"AAA", "BBB"}
        assert calls == [("AAA", 2, "sideways"), ("BBB", 2, "sideways")]


class TestPortfolioTarget:
    def test_side_buy(self):
        t = PortfolioTarget("000001", "s", 0.1, delta_shares=500)
        assert t.side == "buy"

    def test_side_sell(self):
        t = PortfolioTarget("000001", "s", 0.1, delta_shares=-300)
        assert t.side == "sell"

    def test_side_hold(self):
        t = PortfolioTarget("000001", "s", 0.1, delta_shares=0)
        assert t.side == "hold"


class TestFillResult:
    def test_fill_pct(self):
        f = FillResult("000001", "buy", 1000, 800, 10.0)
        assert f.fill_pct == 0.8

    def test_full_fill(self):
        f = FillResult("000001", "buy", 1000, 1000, 10.0)
        assert f.fill_pct == 1.0


class TestEqualWeightConstructor:
    def test_top_n_equal_weight(self):
        signals = [
            AlphaSignal(s, "test", "buy", c, s * 10)
            for s, c in [("a", 0.9), ("b", 0.8), ("c", 0.7), ("d", 0.6), ("e", 0.5)]
        ]
        ctx = PipelineContext(
            cash=100000,
            prices={"a": 10, "b": 20, "c": 30, "d": 40, "e": 50},
        )
        ctor = EqualWeightConstructor(max_positions=3, position_pct=0.30)
        targets = ctor.construct(signals, ctx)

        buy_targets = [t for t in targets if t.delta_shares > 0]
        assert len(buy_targets) == 3, f"Expected 3 buy targets, got {len(buy_targets)}"
        # Weights should be equal
        weights = [t.target_weight for t in buy_targets]
        assert all(abs(w - 1 / 3) < 0.01 for w in weights), f"Weights not equal: {weights}"

    def test_sells_removed_positions(self):
        signals = [
            AlphaSignal("a", "test", "buy", 0.9, 90),
            AlphaSignal("b", "test", "buy", 0.8, 80),
        ]
        ctx = PipelineContext(
            cash=50000,
            prices={"a": 10, "b": 20, "c": 30},
            holdings={"a": 0, "b": 0, "c": 500},
        )
        ctor = EqualWeightConstructor(max_positions=2, position_pct=0.30)
        targets = ctor.construct(signals, ctx)

        sell_targets = [t for t in targets if t.delta_shares < 0]
        assert len(sell_targets) == 1
        assert sell_targets[0].symbol == "c"
        assert sell_targets[0].delta_shares == -500


class TestInverseVolatilityConstructor:
    def test_produces_different_weights_than_equal(self):
        dates = pd.date_range("2026-01-01", "2026-05-21", freq="B")
        np.random.seed(42)
        # Stock A: low vol (stable), Stock B: high vol (noisy)
        a_ret = np.random.normal(0.0005, 0.005, len(dates)).cumsum()
        b_ret = np.random.normal(0.0005, 0.030, len(dates)).cumsum()
        prices_df = pd.DataFrame({
            "a": 10 * np.exp(a_ret),
            "b": 20 * np.exp(b_ret),
        }, index=dates)

        signals = [
            AlphaSignal("a", "test", "buy", 0.9, 90),
            AlphaSignal("b", "test", "buy", 0.8, 80),
        ]
        ctx = PipelineContext(cash=100000, prices={"a": 10, "b": 20}, price_history=prices_df)

        eq = EqualWeightConstructor(max_positions=2)
        iv = InverseVolatilityConstructor(max_positions=2)

        eq_targets = eq.construct(signals, ctx)
        iv_targets = iv.construct(signals, ctx)

        eq_weights = {t.symbol: t.target_weight for t in eq_targets if t.delta_shares > 0}
        iv_weights = {t.symbol: t.target_weight for t in iv_targets if t.delta_shares > 0}

        assert eq_weights["a"] == pytest.approx(eq_weights["b"], abs=0.01)
        assert iv_weights["a"] > iv_weights["b"], (
            f"Low-vol stock A should get higher weight: {iv_weights}"
        )


class TestRebalanceScheduler:
    def test_first_call_always_rebalances(self):
        sched = RebalanceScheduler()
        assert sched.should_rebalance(date(2026, 5, 21), "sideways", {}, {})

    def test_monthly_no_rebalance_same_month(self):
        sched = RebalanceScheduler(RebalanceConfig(schedule="monthly"))
        sched.should_rebalance(date(2026, 5, 1), "sideways", {}, {})
        assert not sched.should_rebalance(date(2026, 5, 15), "sideways", {}, {})

    def test_monthly_rebalances_next_month(self):
        sched = RebalanceScheduler(RebalanceConfig(schedule="monthly"))
        sched.should_rebalance(date(2026, 5, 1), "sideways", {}, {})
        assert sched.should_rebalance(date(2026, 6, 1), "sideways", {}, {})

    def test_regime_change_triggers(self):
        sched = RebalanceScheduler(RebalanceConfig(schedule="regime_change"))
        sched.should_rebalance(date(2026, 5, 1), "bull", {}, {})
        assert sched.should_rebalance(date(2026, 5, 2), "bear", {}, {})

    def test_drift_triggers(self):
        sched = RebalanceScheduler(RebalanceConfig(schedule="drift", drift_threshold=0.30))
        sched.should_rebalance(date(2026, 5, 1), "sideways", {}, {})

        holdings = {"a": 500, "b": 500, "c": 10000}
        prices = {"a": 10, "b": 10, "c": 30}
        # c dominates — drift should be high
        assert sched.should_rebalance(date(2026, 5, 10), "sideways", holdings, prices)

    def test_force_months(self):
        sched = RebalanceScheduler(RebalanceConfig(schedule="drift", force_months=[4, 5]))
        sched.should_rebalance(date(2026, 3, 1), "sideways", {}, {})
        assert sched.should_rebalance(date(2026, 4, 1), "sideways", {}, {})

    def test_strategy_trigger_override(self):
        sched = RebalanceScheduler(RebalanceConfig(schedule="drift", max_idle_days=365))
        sched.should_rebalance(date(2026, 5, 1), "sideways", {}, {})
        # Normal schedule wouldn't trigger in same regime
        assert not sched.should_rebalance(date(2026, 5, 2), "sideways", {}, {})
        # Strategy override forces it
        def custom_trigger(dt, regime, holdings):
            return dt.day == 15
        assert sched.should_rebalance(
            date(2026, 5, 15), "sideways", {}, {},
            strategy_trigger=custom_trigger,
        )


class TestRiskAdjuster:
    def test_passed_targets_pass_through(self):
        ctx = PipelineContext(
            cash=500000,
            prices={"a": 10},
            holdings={"a": 500},
        )
        targets = [
            PortfolioTarget("a", "test", 0.1, 1000, 0.05, 500, 500, "test"),
        ]
        adjuster = RiskAdjuster()
        result = adjuster.adjust(targets, ctx)
        assert len(result) == 1
        assert result[0].delta_shares > 0  # Small position won't trigger risk

    def test_zero_delta_targets_pass_through(self):
        ctx = PipelineContext(cash=100000, prices={"a": 10})
        targets = [PortfolioTarget("a", "test", 0.05, 500, 0.05, 500, 0, "no change")]
        adjuster = RiskAdjuster()
        result = adjuster.adjust(targets, ctx)
        assert len(result) == 1
        assert result[0].delta_shares == 0


class TestExecutionRouter:
    def test_sells_before_buys(self):
        ctx = PipelineContext(
            cash=50000,
            prices={"a": 10, "b": 20, "c": 30},
            holdings={"a": 500, "b": 300, "c": 0},
        )
        targets = [
            PortfolioTarget("a", "test", 0.1, 0, 0.1, 500, -500, "sell all"),
            PortfolioTarget("b", "test", 0.0, 0, 0.05, 300, -300, "sell all"),
            PortfolioTarget("c", "test", 0.2, 1500, 0.0, 0, 1500, "buy new"),
        ]
        router = ExecutionRouter()
        intents = router.targets_to_intents(targets, ctx)

        assert len(intents) > 0
        # Sells must come before buys
        sell_indices = [i for i, intent in enumerate(intents) if intent.side == "sell"]
        buy_indices = [i for i, intent in enumerate(intents) if intent.side == "buy"]
        if sell_indices and buy_indices:
            assert max(sell_indices) < min(buy_indices), "Sells must precede buys"

    def test_t_plus_1_constrains_sells(self):
        ctx = PipelineContext(
            cash=50000,
            prices={"a": 10},
            holdings={"a": 500},
        )
        targets = [PortfolioTarget("a", "test", 0, 0, 0.1, 500, -500, "sell")]
        router = ExecutionRouter()
        router._today_buys = {"a": 300}  # bought 300 today, can only sell 200

        intents = router.targets_to_intents(targets, ctx)
        sell = next((i for i in intents if i.side == "sell"), None)
        assert sell is not None
        assert sell.shares == 200, f"T+1 should limit sell to 200, got {sell.shares}"


class TestPipelineContext:
    def test_context_carries_stage_outputs(self):
        ctx = PipelineContext(cash=100000, regime="bull")
        ctx.signals = [AlphaSignal("a", "test", "buy", 0.8, 80)]
        ctx.targets = [PortfolioTarget("a", "test", 0.1, 1000)]
        ctx.adjusted_targets = [PortfolioTarget("a", "test", 0.08, 800)]
        ctx.intents = [OrderIntent("a", "buy", 800, 10.0)]
        ctx.fills = [FillResult("a", "buy", 800, 800, 10.0, status="filled")]

        assert len(ctx.signals) == 1
        assert len(ctx.targets) == 1
        assert len(ctx.adjusted_targets) == 1
        assert len(ctx.intents) == 1
        assert ctx.fills[0].status == "filled"
