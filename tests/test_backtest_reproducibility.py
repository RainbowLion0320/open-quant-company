"""
Backtest reproducibility contracts.

Verifies that running the same deterministic backtest twice produces
byte-stable or rounded-stable results (total return, max drawdown, trade count).
"""
import numpy as np
import pandas as pd
import pytest


def _make_fixture():
    """Create a tiny deterministic price fixture."""
    dates = pd.date_range("2024-01-02", periods=60, freq="B")
    np.random.seed(42)
    # Two stocks with deterministic prices
    base_a = 100.0 + np.cumsum(np.random.randn(60) * 0.5)
    base_b = 50.0 + np.cumsum(np.random.randn(60) * 0.3)
    prices = pd.DataFrame({
        "SH600000_close": base_a,
        "SH600001_close": base_b,
    }, index=dates)
    return prices


def _simple_backtest(prices: pd.DataFrame) -> dict:
    """Run a trivial equal-weight buy-and-hold backtest."""
    # Equal weight allocation on day 0
    weights = {col: 1.0 / len(prices.columns) for col in prices.columns}
    portfolio_value = pd.Series(0.0, index=prices.index)
    initial_cash = 1_000_000.0

    # Buy on day 0
    shares = {}
    for col in prices.columns:
        shares[col] = (initial_cash * weights[col]) / prices[col].iloc[0]

    # Track portfolio value
    for i, date in enumerate(prices.index):
        val = sum(shares[col] * prices[col].iloc[i] for col in prices.columns)
        portfolio_value.iloc[i] = val

    daily_returns = portfolio_value.pct_change().dropna()
    total_return = (portfolio_value.iloc[-1] / initial_cash) - 1.0
    max_drawdown = (portfolio_value / portfolio_value.cummax() - 1.0).min()

    return {
        "total_return": round(total_return, 10),
        "max_drawdown": round(max_drawdown, 10),
        "trade_count": len(prices.columns),  # one buy per stock
        "final_value": round(portfolio_value.iloc[-1], 10),
    }


class TestBacktestReproducibility:

    def test_same_input_produces_identical_output(self):
        """Running the same backtest twice yields identical results."""
        prices = _make_fixture()
        result1 = _simple_backtest(prices)
        result2 = _simple_backtest(prices)

        assert result1["total_return"] == result2["total_return"]
        assert result1["max_drawdown"] == result2["max_drawdown"]
        assert result1["trade_count"] == result2["trade_count"]
        assert result1["final_value"] == result2["final_value"]

    def test_ranking_order_stable(self):
        """Multiple strategies on the same data produce a stable ranking."""
        prices = _make_fixture()

        # Strategy A: equal weight
        result_a = _simple_backtest(prices)

        # Strategy B: 80/20 weight
        weights_b = {prices.columns[0]: 0.8, prices.columns[1]: 0.2}
        shares_b = {}
        initial_cash = 1_000_000.0
        for col in prices.columns:
            shares_b[col] = (initial_cash * weights_b[col]) / prices[col].iloc[0]
        final_b = sum(shares_b[col] * prices[col].iloc[-1] for col in prices.columns)
        result_b_total = (final_b / initial_cash) - 1.0

        # Run twice
        shares_b2 = {}
        for col in prices.columns:
            shares_b2[col] = (initial_cash * weights_b[col]) / prices[col].iloc[0]
        final_b2 = sum(shares_b2[col] * prices[col].iloc[-1] for col in prices.columns)
        result_b2_total = (final_b2 / initial_cash) - 1.0

        assert result_b_total == result_b2_total
        # Ranking should be consistent
        ranking1 = sorted([result_a["total_return"], result_b_total], reverse=True)
        ranking2 = sorted([result_a["total_return"], result_b2_total], reverse=True)
        assert ranking1 == ranking2

    def test_no_network_dependency(self):
        """Test does not require network data."""
        prices = _make_fixture()
        assert prices is not None
        assert len(prices) == 60
        # All values are finite
        assert np.all(np.isfinite(prices.values))
