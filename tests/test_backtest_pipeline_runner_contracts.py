import pandas as pd
import pytest

from backtest.pipeline_runner import PipelineBacktest
from pipeline.alpha import AlphaModel
from pipeline.portfolio import EqualWeightConstructor
from pipeline.scheduler import RebalanceConfig, RebalanceScheduler
from pipeline.types import AlphaSignal, FillResult, OrderIntent, PortfolioTarget


pytestmark = pytest.mark.usefixtures("risk_free_curve")


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


class FuturePeekingAlpha(AlphaModel):
    name = "future_peeking_alpha"
    label = "Future Peeking Alpha"

    def __init__(self):
        self.seen_lengths: list[int] = []

    def generate_alpha(self, universe, prices, date_idx, regime):
        self.seen_lengths.append(len(prices))
        signals = []
        for symbol in universe:
            current = float(prices[symbol].iloc[date_idx])
            future = prices[symbol].iloc[date_idx + 1:]
            future_max = float(future.max()) if not future.empty else current
            if future_max > current * 5:
                signals.append(AlphaSignal(symbol=symbol, strategy=self.name, direction="buy", score=99, confidence=0.99))
        return signals


class PanelAlpha(AlphaModel):
    name = "panel_alpha"
    label = "Panel Alpha"

    def generate_score_panel(self, universe, prices, date_idx, regime):
        return [
            {
                "symbol": symbol,
                "score": 90.0 if symbol == "AAA" else 10.0,
                "data_quality": "ok",
            }
            for symbol in universe
        ]

    def generate_alpha(self, universe, prices, date_idx, regime):
        return [
            AlphaSignal(
                symbol="AAA",
                strategy=self.name,
                direction="buy",
                confidence=0.9,
                score=90.0,
            )
        ]


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


def test_pipeline_backtest_only_passes_point_in_time_prices_to_alpha():
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    prices = pd.DataFrame({"AAA": [10.0, 10.0, 1000.0, 10.0, 10.0]}, index=dates)
    bench = pd.Series([100, 100, 100, 100, 100], index=dates)
    alpha = FuturePeekingAlpha()

    result = PipelineBacktest(
        alpha=alpha,
        portfolio=EqualWeightConstructor(max_positions=1, position_pct=1.0),
        scheduler=RebalanceScheduler(RebalanceConfig(schedule="daily")),
    ).run(prices, bench, universe=["AAA"])

    assert alpha.seen_lengths == [1, 2, 3, 4, 5]
    assert result["trade_count"] == 0


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


def test_pipeline_backtest_persists_full_score_panel_for_alpha_evidence():
    dates = pd.date_range("2024-01-02", periods=25, freq="B")
    prices = pd.DataFrame(
        {
            "AAA": [10 + i for i in range(25)],
            "BBB": [30 - i * 0.2 for i in range(25)],
        },
        index=dates,
    )
    bench = pd.Series([100 + i for i in range(25)], index=dates)

    result = PipelineBacktest(
        alpha=PanelAlpha(),
        portfolio=EqualWeightConstructor(max_positions=1, position_pct=0.5),
        scheduler=RebalanceScheduler(RebalanceConfig(schedule="daily")),
    ).run(prices, bench, universe=["AAA", "BBB"])

    panel = result["score_panel"]
    assert set(panel["symbol"]) == {"AAA", "BBB"}
    assert set(panel["strategy"]) == {"panel_alpha"}
    assert {"as_of_date", "score", "rank", "selected", "forward_return_20d", "data_quality"}.issubset(panel.columns)
    latest_rows = panel[panel["as_of_date"] == panel["as_of_date"].min()]
    assert latest_rows.set_index("symbol").loc["AAA", "rank"] == 1
    assert bool(latest_rows.set_index("symbol").loc["AAA", "selected"]) is True
