from __future__ import annotations

import pandas as pd
import pytest


def test_risk_free_provider_aligns_cn_treasury_curve(tmp_path):
    from data.rates.risk_free_rates import RiskFreeRateProvider

    source = tmp_path / "treasury_yields.parquet"
    pd.DataFrame(
        {
            "日期": ["2026-01-02", "2026-01-05"],
            "中国国债收益率2年": [1.50, 1.60],
        }
    ).to_parquet(source, index=False)

    provider = RiskFreeRateProvider(source_path=source, market="CN", tenor="2Y", max_staleness_days=7)
    index = pd.to_datetime(["2026-01-02", "2026-01-06"])

    rates = provider.annualized_series(index)

    assert rates.index.equals(pd.DatetimeIndex(index))
    assert rates.tolist() == [0.015, 0.016]


def test_risk_free_provider_fails_when_curve_missing_required_dates(tmp_path):
    from data.rates.risk_free_rates import RiskFreeRateDataError, RiskFreeRateProvider

    source = tmp_path / "treasury_yields.parquet"
    pd.DataFrame(
        {
            "日期": ["2026-01-02"],
            "中国国债收益率2年": [1.50],
        }
    ).to_parquet(source, index=False)

    provider = RiskFreeRateProvider(source_path=source, market="CN", tenor="2Y", max_staleness_days=1)

    with pytest.raises(RiskFreeRateDataError, match="missing"):
        provider.annualized_series(pd.to_datetime(["2026-01-10"]))


def test_risk_free_provider_rejects_non_date_index(tmp_path):
    from data.rates.risk_free_rates import RiskFreeRateDataError, RiskFreeRateProvider

    source = tmp_path / "treasury_yields.parquet"
    pd.DataFrame(
        {
            "日期": ["2026-01-02"],
            "中国国债收益率2年": [1.50],
        }
    ).to_parquet(source, index=False)

    provider = RiskFreeRateProvider(source_path=source, market="CN", tenor="2Y")

    with pytest.raises(RiskFreeRateDataError, match="date-like"):
        provider.annualized_series([0, 1, 2])


def test_risk_analytics_requires_daily_risk_free_series():
    from backtest.analytics import RiskAnalytics
    from data.rates.risk_free_rates import RiskFreeRateDataError

    returns = pd.Series([0.01] * 20, index=pd.date_range("2026-01-02", periods=20, freq="B"))

    with pytest.raises(RiskFreeRateDataError, match="risk-free"):
        RiskAnalytics.compute(returns)


def test_risk_analytics_rejects_positional_risk_free_series():
    from backtest.analytics import RiskAnalytics
    from data.rates.risk_free_rates import RiskFreeRateDataError

    returns = pd.Series([0.01] * 20, index=pd.date_range("2026-01-02", periods=20, freq="B"))
    positional_rates = pd.Series([0.015] * len(returns))

    with pytest.raises(RiskFreeRateDataError, match="DatetimeIndex"):
        RiskAnalytics.compute(returns, risk_free_rates=positional_rates)


def test_config_does_not_allow_fixed_risk_free_fallback():
    from core.settings import get_section

    backtest = get_section("backtest", {}) or {}
    risk_free = backtest.get("risk_free", {})

    assert "risk_free_rate" not in backtest
    assert risk_free.get("mode") == "curve"
    assert "fallback_rate" not in risk_free
    assert "fixed" not in str(risk_free).lower()


def test_legacy_top_level_risk_free_rate_is_rejected():
    from data.rates.risk_free_rates import RiskFreeRateDataError, risk_free_spec_from_config

    with pytest.raises(RiskFreeRateDataError, match="risk_free_rate"):
        risk_free_spec_from_config({"backtest": {"risk_free_rate": 0.03}})
