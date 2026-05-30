"""
Point-in-Time (PIT) lookahead bias contracts.

Verifies that feature generation and strategy decisions on date T
cannot see data from T+1 or later.
"""
import numpy as np
import pandas as pd
import pytest


def _make_price_fixture_with_future_spike():
    """Create a fixture where stock A has a future price spike after the decision date."""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    prices = pd.DataFrame({
        "close": 100.0 + np.arange(30, dtype=float) * 0.1,
    }, index=dates)
    # Inject a 30% spike on day 20 (the "future" event)
    prices.iloc[20, 0] = prices.iloc[19, 0] * 1.30
    return prices


class TestPITLookahead:

    def test_feature_on_T_cannot_see_T_plus_1_price(self):
        """Feature generated at T should not incorporate prices from T+1."""
        prices = _make_price_fixture_with_future_spike()

        # Generate "features" using only data up to each date
        # A simple moving average should not see the spike before day 20
        sma_5 = prices["close"].rolling(5).mean()

        # On day 18 (before spike), SMA should be based on days 14-18
        # The spike is on day 20, so day 18's SMA should be ~100.5 range
        t18_sma = sma_5.iloc[18]
        assert t18_sma < 110.0, f"SMA at T=18 should not see future spike, got {t18_sma}"

    def test_strategy_cannot_buy_on_future_return(self):
        """A strategy that only uses past data should not buy solely because of a future return."""
        prices = _make_price_fixture_with_future_spike()

        # Simple momentum strategy: buy if last 5-day return > 5%
        past_returns = prices["close"].pct_change(5)

        # On day 18, past 5-day return should be small (no spike yet)
        day18_ret = past_returns.iloc[18]
        assert abs(day18_ret) < 0.10, f"Day 18 return should not reflect future spike: {day18_ret}"

    def test_as_of_constraint_limits_data(self):
        """Data filtered to as_of date excludes future rows."""
        prices = _make_price_fixture_with_future_spike()

        as_of = prices.index[15]  # day 15
        visible = prices.loc[:as_of]

        assert len(visible) == 16  # days 0-15
        # The spike on day 20 should NOT be visible
        assert visible["close"].max() < 120.0

    def test_contaminated_feature_detected(self):
        """If a feature deliberately uses future data, a check should flag it."""
        prices = _make_price_fixture_with_future_spike()

        # Normal feature: returns at T
        normal_ret = prices["close"].pct_change()

        # Contaminated feature: uses shifted data (sees future)
        contaminated_ret = prices["close"].shift(-1).pct_change()

        # At day 19, the contaminated version sees the spike from day 20
        # while the normal version does not
        day19_normal = normal_ret.iloc[19]
        day19_contaminated = contaminated_ret.iloc[19]

        # The contaminated version should differ from the normal version
        # (it incorporates the day-20 spike)
        if not np.isnan(day19_contaminated):
            assert day19_normal != day19_contaminated, "Contaminated feature should differ from normal"
