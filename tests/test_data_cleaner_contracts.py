"""
Contracts for data/cleaner.py rule implementations.

Each test uses deterministic DataFrames to verify rule behavior.
"""
import numpy as np
import pandas as pd
import pytest

from data.quality.cleaner import (
    CleanReport,
    OHLCVIntegrityRule,
    OutlierDetectionRule,
    SuspendedDetectionRule,
    MissingValueRule,
    FinancialValidationRule,
    WinsorizeRule,
)


def _report():
    return CleanReport()


def _ohlcv(n=10, base=100.0):
    """Generate a simple OHLCV DataFrame."""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = base + np.arange(n, dtype=float)
    return pd.DataFrame({
        "date": dates,
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.full(n, 1e6),
    })


class TestOHLCVIntegrityRule:

    def test_swaps_high_low(self):
        """high < low rows get swapped."""
        df = _ohlcv(5)
        df.loc[2, "high"] = 90.0  # lower than low
        df.loc[2, "low"] = 110.0
        rule = OHLCVIntegrityRule("ohlcv", {})
        result = rule.apply(df, _report())
        assert result.loc[2, "high"] >= result.loc[2, "low"]

    def test_clamps_close_to_range(self):
        """Close outside [low, high] gets clamped."""
        df = _ohlcv(5)
        df.loc[1, "close"] = 200.0  # above high
        df.loc[3, "close"] = 50.0   # below low
        rule = OHLCVIntegrityRule("ohlcv", {})
        result = rule.apply(df, _report())
        assert result.loc[1, "close"] == result.loc[1, "high"]
        assert result.loc[3, "close"] == result.loc[3, "low"]

    def test_removes_non_positive_close(self):
        """Rows with close <= 0 are removed (after clamping to [low,high])."""
        df = _ohlcv(5)
        # Set low=high=close=-1.0 so clamping can't rescue it
        df.loc[0, "open"] = -1.0
        df.loc[0, "high"] = -1.0
        df.loc[0, "low"] = -1.0
        df.loc[0, "close"] = -1.0
        # Set close=0 with low>0 so clamping sets close=low, then 0 check won't catch it
        # Instead, set low=high=close=0
        df.loc[1, "open"] = 0.0
        df.loc[1, "high"] = 0.0
        df.loc[1, "low"] = 0.0
        df.loc[1, "close"] = 0.0
        rule = OHLCVIntegrityRule("ohlcv", {})
        report = _report()
        result = rule.apply(df, report)
        assert len(result) == 3
        assert report.removed_rows == 2

    def test_replaces_non_positive_open_with_close(self):
        """open <= 0 is replaced with close."""
        df = _ohlcv(5)
        df.loc[2, "open"] = -5.0
        rule = OHLCVIntegrityRule("ohlcv", {})
        result = rule.apply(df, _report())
        assert result.loc[2, "open"] == result.loc[2, "close"]


class TestOutlierDetectionRule:

    def test_caps_extreme_returns(self):
        """Non-limit extreme returns are capped."""
        df = _ohlcv(30)
        # Inject a 80% spike on day 10 (well above max_change=0.20)
        df.loc[10, "close"] = df.loc[9, "close"] * 1.8
        rule = OutlierDetectionRule("outlier", {"sigma": 5, "max_daily_change_pct": 0.20})
        report = _report()
        result = rule.apply(df, report)
        # The rule should have capped outliers (sigma + max_change)
        assert report.capped_outliers > 0
        # After capping, day 10's close should equal day 9's close (reset by max_change)
        assert result.loc[10, "close"] == pytest.approx(result.loc[9, "close"])

    def test_preserves_limit_like_moves(self):
        """10%, 20%, 30% limit-like moves are preserved."""
        df = _ohlcv(30)
        # Inject a ~10% move (limit-like)
        df.loc[10, "close"] = df.loc[9, "close"] * 1.10
        rule = OutlierDetectionRule("outlier", {"sigma": 5, "max_daily_change_pct": 0.20})
        report = _report()
        result = rule.apply(df, report)
        # The ~10% move should NOT be capped
        pct = (result.loc[10, "close"] - result.loc[9, "close"]) / result.loc[9, "close"]
        assert abs(pct - 0.10) < 0.02


class TestSuspendedDetectionRule:

    def test_removes_rows_after_max_flat_days(self):
        """Rows with price unchanged for >= max_flat_days are removed."""
        df = _ohlcv(70)
        # Make days 10-69 all have the same close (60 flat days)
        flat_price = df.loc[10, "close"]
        df.loc[10:69, "close"] = flat_price
        df.loc[10:69, "open"] = flat_price
        df.loc[10:69, "high"] = flat_price
        df.loc[10:69, "low"] = flat_price

        rule = SuspendedDetectionRule("suspended", {"max_flat_days": 30})
        report = _report()
        result = rule.apply(df, report)
        # Days after the 30-day flat streak should be removed
        assert len(result) < 70
        assert report.flagged_suspended > 0


class TestMissingValueRule:

    def test_forward_fills_within_limit(self):
        """Forward-fill only within the configured limit."""
        df = _ohlcv(10)
        df.loc[3, "close"] = np.nan
        df.loc[4, "close"] = np.nan
        df.loc[5, "close"] = np.nan
        rule = MissingValueRule("missing", {"max_forward_fill": 2})
        report = _report()
        result = rule.apply(df, report)
        # Day 3 filled, day 4 filled, day 5 still NaN → removed
        assert 5 not in result.index or pd.notna(result.loc[5, "close"])

    def test_removes_rows_still_missing_close(self):
        """Rows with close still NaN after ffill are removed."""
        df = _ohlcv(5)
        df.loc[0, "close"] = np.nan  # first row, nothing to ffill from
        rule = MissingValueRule("missing", {"max_forward_fill": 5})
        report = _report()
        result = rule.apply(df, report)
        assert len(result) == 4
        assert report.removed_rows >= 1


class TestFinancialValidationRule:

    def test_caps_financial_columns(self):
        """Financial columns are clamped to configured ranges."""
        df = pd.DataFrame({
            "fund_roe": [0.5, -2.0, 1.5],      # valid, below -1, above 1
            "val_pe_ttm": [20.0, -5.0, 2000.0], # valid, below 0, above 1000
        })
        rule = FinancialValidationRule("financial", {})
        report = _report()
        result = rule.apply(df, report)
        assert result.loc[1, "fund_roe"] == -1.0
        assert result.loc[2, "fund_roe"] == 1.0
        assert result.loc[1, "val_pe_ttm"] == 0.0
        assert result.loc[2, "val_pe_ttm"] == 1000.0


class TestWinsorizeRule:

    def test_caps_numeric_tails(self):
        """Numeric feature tails are clipped to quantile range."""
        np.random.seed(42)
        df = pd.DataFrame({
            "feature_a": np.concatenate([[-1000.0], np.random.randn(98).tolist(), [1000.0]]),
            "symbol": ["X"] * 100,
            "date": pd.date_range("2024-01-01", periods=100, freq="B"),
        })
        rule = WinsorizeRule("winsorize", {"lower_pct": 0.01, "upper_pct": 0.99})
        report = _report()
        result = rule.apply(df, report)
        # The extreme values should be clipped
        assert result["feature_a"].min() > -1000.0
        assert result["feature_a"].max() < 1000.0
        # symbol and date columns unchanged
        assert list(result["symbol"]) == ["X"] * 100
        assert report.capped_outliers > 0
