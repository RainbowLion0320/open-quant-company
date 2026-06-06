import pandas as pd

from backtest.pipeline_runner import PipelineBacktest
from pipeline.alpha import AlphaModel
from pipeline.types import AlphaSignal, FillResult, OrderIntent, PortfolioTarget


class RecordingAlpha(AlphaModel):
    name = "recording_alpha"
    label = "Recording Alpha"

    def __init__(self, events: list[str]):
        self.events = events
        self.seen_universe: list[str] = []

    def generate_alpha(self, universe, prices, date_idx, regime):
        self.events.append("alpha")
        self.seen_universe = list(universe)
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


class RecordingPortfolio:
    def __init__(self, events: list[str]):
        self.events = events

    def construct(self, signals, ctx):
        self.events.append("portfolio")
        return [
            PortfolioTarget(
                symbol=signal.symbol,
                strategy=signal.strategy,
                target_weight=1.0,
                target_shares=100,
                current_shares=0,
                delta_shares=100,
                reason="unit-test target",
            )
            for signal in signals
        ]


class RecordingRisk:
    def __init__(self, events: list[str]):
        self.events = events

    def adjust(self, targets, ctx):
        self.events.append("risk")
        return targets


class RecordingExecution:
    def __init__(self, events: list[str]):
        from broker.exchange import AShareExchange

        self.events = events
        self.exchange = AShareExchange()

    def targets_to_intents(self, targets, ctx):
        self.events.append("execution:intents")
        return [
            OrderIntent(
                symbol=target.symbol,
                side="buy",
                shares=target.delta_shares,
                price=ctx.prices[target.symbol],
                strategy=target.strategy,
            )
            for target in targets
            if target.delta_shares > 0
        ]

    def execute(self, intents):
        self.events.append("execution:fills")
        return [
            FillResult(
                symbol=intent.symbol,
                side=intent.side,
                requested_shares=intent.shares,
                filled_shares=intent.shares,
                fill_price=intent.price,
                status="filled",
            )
            for intent in intents
        ]

    def end_of_day(self):
        self.events.append("execution:eod")


def test_pipeline_backtest_uses_production_shared_stage_sequence():
    events: list[str] = []
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    prices = pd.DataFrame({"AAA": [10, 11, 12, 11, 13]}, index=dates)
    bench = pd.Series([100, 101, 102, 101, 103], index=dates)

    result = PipelineBacktest(
        alpha=RecordingAlpha(events),
        portfolio=RecordingPortfolio(events),
        risk=RecordingRisk(events),
        execution=RecordingExecution(events),
    ).run(prices, bench, universe=["AAA"])

    assert events[:5] == ["alpha", "portfolio", "risk", "execution:intents", "execution:fills"]
    assert events[-1] == "execution:eod"
    assert result["trade_count"] == 1


def test_pipeline_backtest_filters_universe_to_available_price_columns():
    events: list[str] = []
    alpha = RecordingAlpha(events)
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    prices = pd.DataFrame({"AAA": [10, 11, 12, 11, 13]}, index=dates)
    bench = pd.Series([100, 101, 102, 101, 103], index=dates)

    result = PipelineBacktest(
        alpha=alpha,
        portfolio=RecordingPortfolio(events),
        risk=RecordingRisk(events),
        execution=RecordingExecution(events),
    ).run(prices, bench, universe=["AAA", "MISSING"])

    assert alpha.seen_universe == ["AAA"]
    assert result["trade_count"] == 1
