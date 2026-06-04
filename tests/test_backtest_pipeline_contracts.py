"""
Pluggable pipeline contracts.

Tests the backtest/pipeline.py Pipeline and Stage abstractions with
4 fake stages: Data → Alpha → Portfolio → Execution.
"""
import pandas as pd
import pytest

from backtest.pipeline import Context, Pipeline, Stage
from backtest.pipeline_runner import PipelineBacktest
from pipeline.alpha import AlphaModel
from pipeline.types import AlphaSignal


class FakeDataStage(Stage):
    """Returns two symbols and deterministic prices."""

    def process(self, ctx: Context) -> Context:
        ctx.universe = ["SH600000", "SH600001"]
        dates = pd.date_range("2024-01-02", periods=20, freq="B")
        ctx.data = pd.DataFrame({
            "SH600000_close": [100.0 + i for i in range(20)],
            "SH600001_close": [50.0 + i * 0.5 for i in range(20)],
        }, index=dates)
        ctx.start_date = "2024-01-02"
        ctx.end_date = "2024-01-31"
        return ctx


class FakeAlphaStage(Stage):
    """Emits buy signals for both symbols."""

    def process(self, ctx: Context) -> Context:
        if ctx.data is not None and not ctx.data.empty:
            ctx.signals = pd.DataFrame({
                sym: [1.0] * len(ctx.data) for sym in ctx.universe
            }, index=ctx.data.index)
        return ctx


class FakePortfolioStage(Stage):
    """Applies equal-weight allocation with max single-name cap."""

    MAX_SINGLE_WEIGHT = 0.6

    def process(self, ctx: Context) -> Context:
        if ctx.signals is not None:
            n = len(ctx.universe)
            weight = min(1.0 / n, self.MAX_SINGLE_WEIGHT) if n > 0 else 0.0
            ctx.portfolio_weights = pd.DataFrame({
                sym: [weight] * len(ctx.signals) for sym in ctx.universe
            }, index=ctx.signals.index)
        return ctx


class FakeExecutionStage(Stage):
    """Records orders without mutating external state."""

    def process(self, ctx: Context) -> Context:
        if ctx.portfolio_weights is not None:
            for sym in ctx.universe:
                ctx.orders.append({
                    "symbol": sym,
                    "side": "buy",
                    "weight": ctx.portfolio_weights[sym].iloc[0],
                })
        return ctx


class RiskRejectingStage(Stage):
    """Rejects orders that exceed a weight threshold and logs the rejection."""

    MAX_WEIGHT = 0.3

    def process(self, ctx: Context) -> Context:
        rejected = []
        for order in ctx.orders:
            if order.get("weight", 0) > self.MAX_WEIGHT:
                rejected.append(order["symbol"])
        if rejected:
            ctx.info(f"Risk rejected: {rejected}")
            ctx.orders = [o for o in ctx.orders if o["symbol"] not in rejected]
        return ctx


class SingleSymbolAlpha(AlphaModel):
    name = "single_symbol"
    label = "Single Symbol"

    def generate_alpha(self, universe, prices, date_idx, regime):
        return [
            AlphaSignal(
                symbol=symbol,
                strategy=self.name,
                direction="buy",
                confidence=0.8,
                score=80,
            )
            for symbol in universe
        ]


class TestPipelineContract:

    def test_stages_run_in_order(self):
        """Stages execute in the order they are added."""
        ctx = Context()
        pipeline = Pipeline(
            stages=[FakeDataStage(), FakeAlphaStage(), FakePortfolioStage(), FakeExecutionStage()],
            name="TestPipeline",
        )
        result = pipeline.run(ctx)

        # Data stage populated universe and data
        assert result.universe == ["SH600000", "SH600001"]
        assert result.data is not None
        assert len(result.data) == 20

        # Alpha stage populated signals
        assert result.signals is not None

        # Portfolio stage populated weights
        assert result.portfolio_weights is not None

        # Execution stage recorded orders
        assert len(result.orders) == 2

    def test_stage_payloads_use_shared_types(self):
        """Stages use the shared Context type for input/output."""
        ctx = Context()
        pipeline = Pipeline(stages=[FakeDataStage(), FakeAlphaStage()])
        result = pipeline.run(ctx)

        assert isinstance(result, Context)
        assert isinstance(result.data, pd.DataFrame)
        assert isinstance(result.signals, pd.DataFrame)
        assert isinstance(result.universe, list)

    def test_risk_rejection_visible_in_output(self):
        """Risk rejection is visible in output, not swallowed."""
        ctx = Context()
        pipeline = Pipeline(
            stages=[
                FakeDataStage(),
                FakeAlphaStage(),
                FakePortfolioStage(),
                FakeExecutionStage(),
                RiskRejectingStage(),
            ],
            name="RiskPipeline",
        )
        result = pipeline.run(ctx)

        # Orders should be rejected (weight=0.5 > max=0.3)
        assert len(result.orders) == 0
        # Rejection should be logged
        assert any("Risk rejected" in msg for msg in result.log)

    def test_empty_pipeline_returns_context(self):
        """An empty pipeline returns the context unchanged."""
        ctx = Context()
        pipeline = Pipeline(stages=[], name="EmptyPipeline")
        result = pipeline.run(ctx)
        assert isinstance(result, Context)

    def test_pipeline_backtest_filters_universe_to_available_price_columns(self):
        dates = pd.date_range("2024-01-02", periods=5, freq="B")
        prices = pd.DataFrame({"AAA": [10, 11, 12, 11, 13]}, index=dates)
        bench = pd.Series([100, 101, 102, 101, 103], index=dates)

        result = PipelineBacktest(alpha=SingleSymbolAlpha()).run(
            prices,
            bench,
            universe=["AAA", "MISSING"],
        )

        assert result["trade_count"] > 0
