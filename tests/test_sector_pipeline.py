"""
Sector pipeline & industry momentum tests.

Covers: data/sectors.py builders, signals/multifactor.py industry factor,
sector API endpoints, portfolio sector-exposure API.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


# ── helpers ────────────────────────────────────────────────

def _make_ohlcv(symbol: str, n_days: int = 120, trend: float = 0.001) -> pd.DataFrame:
    """Synthetic OHLCV for one stock."""
    dates = pd.date_range("2025-11-01", periods=n_days, freq="B")
    close = pd.Series(10.0 * np.cumprod(np.full(n_days, 1 + trend)), index=dates)
    return pd.DataFrame({
        "date": [str(d.date()) for d in dates],
        "open": close * 0.99, "high": close * 1.02,
        "low": close * 0.98, "close": close, "volume": 1_000_000.0,
    })


def _patch_hub_store(tmp_path: Path, monkeypatch):
    """Redirect get_datahub() to a tmp_path-backed DataHub."""
    from data import datahub

    datahub.reset_datahub()
    hub = datahub.get_datahub()
    monkeypatch.setattr(hub, "store_root", tmp_path)
    monkeypatch.setattr(datahub, "get_datahub", lambda: hub)
    monkeypatch.setattr("data.datahub.get_datahub", lambda: hub)
    monkeypatch.setattr("data.contract.get_datahub", lambda: hub)
    return hub


# ═══════════════════════════════════════════════════════════
# Membership
# ═══════════════════════════════════════════════════════════

def test_build_membership_columns(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)
    mem_path = tmp_path / "sector_membership.parquet"
    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path)

    df = sectors.build_membership(hub)
    assert len(df) > 0
    for col in ("symbol", "sector_code", "sector_name", "sector_level"):
        assert col in df.columns, f"missing column {col}"
    assert all(isinstance(c, str) and len(c) == 6 for c in df["sector_code"])


def test_build_membership_uses_sw_industries(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)
    mem_path = tmp_path / "sector_membership.parquet"
    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path)

    df = sectors.build_membership(hub)
    valid_names = set(sectors.SW_INDUSTRIES.values())
    for name in df["sector_name"].unique():
        assert name in valid_names, f"unexpected sector name: {name}"


# ═══════════════════════════════════════════════════════════
# Performance builder
# ═══════════════════════════════════════════════════════════

def test_build_sector_performance_with_mock_data(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)

    # Mock membership
    mem = pd.DataFrame([
        {"symbol": "000001", "sector_code": "801970", "sector_name": "银行"},
        {"symbol": "000002", "sector_code": "801180", "sector_name": "房地产"},
    ])
    mem_path = tmp_path / "sector_membership.parquet"
    hub.write_parquet(mem, mem_path)

    ohlcv_map = {
        "000001": _make_ohlcv("000001", trend=0.0005),
        "000002": _make_ohlcv("000002", trend=-0.0002),
    }

    def mock_dim_path(dim, **kw):
        if kw.get("symbol"):
            p = tmp_path / f"ohlcv_{kw['symbol']}.parquet"
            if kw["symbol"] in ohlcv_map:
                hub.write_parquet(ohlcv_map[kw["symbol"]], p)
            return p
        return tmp_path / f"{dim}.parquet"

    monkeypatch.setattr(hub, "dimension_path", mock_dim_path)
    monkeypatch.setattr(sectors, "_store", lambda: tmp_path / "sector")

    df = sectors.build_sector_performance(hub, lookback_days=120)
    assert len(df) > 0
    for col in ("sector_code", "return_20d", "volatility", "member_count"):
        assert col in df.columns, f"missing {col}"

    bank_row = df[df["sector_code"] == "801970"]
    if not bank_row.empty:
        assert bank_row.iloc[0]["return_20d"] > 0


def test_build_performance_empty_membership_returns_empty(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)
    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: tmp_path / "nonexistent.parquet")
    df = sectors.build_sector_performance(hub)
    assert df.empty


# ═══════════════════════════════════════════════════════════
# Signal aggregation
# ═══════════════════════════════════════════════════════════

def test_build_signal_aggregation_with_mock_data(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)

    mem = pd.DataFrame([
        {"symbol": "000001", "sector_code": "801970", "sector_name": "银行"},
        {"symbol": "000002", "sector_code": "801180", "sector_name": "房地产"},
    ])
    mem_path = tmp_path / "sector_membership.parquet"
    hub.write_parquet(mem, mem_path)

    sig_df = pd.DataFrame([
        {"symbol": "000001", "score": 72, "signal": "buy"},
        {"symbol": "000001", "score": 68, "signal": "hold"},
        {"symbol": "000001", "score": 55, "signal": "hold"},
        {"symbol": "000002", "score": 40, "signal": "hold"},
    ])

    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path)

    def mock_signal_path(strategy):
        p = tmp_path / f"sig_{strategy}.parquet"
        hub.write_parquet(sig_df, p)
        return p

    monkeypatch.setattr(hub, "signal_path", mock_signal_path)
    monkeypatch.setattr(sectors, "_store", lambda: tmp_path / "sector")

    df = sectors.build_signal_aggregation(hub)
    assert len(df) > 0
    for col in ("sector", "strategy", "total", "buy_count", "buy_ratio", "avg_score", "top_symbol"):
        assert col in df.columns

    bank_row = df[(df["sector"] == "银行") & (df["strategy"] == "buffett")]
    if not bank_row.empty:
        assert bank_row.iloc[0]["total"] == 3
        assert bank_row.iloc[0]["buy_count"] == 1
        assert bank_row.iloc[0]["top_symbol"] == "000001"


# ═══════════════════════════════════════════════════════════
# Exposure builder
# ═══════════════════════════════════════════════════════════

def test_build_exposure_with_mock_positions(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)

    pos = pd.DataFrame([
        {"symbol": "000001", "market_value": 50000},
        {"symbol": "000002", "market_value": 30000},
        {"symbol": "000001", "market_value": 20000},
    ])
    (tmp_path / "paper").mkdir(exist_ok=True)
    hub.write_parquet(pos, tmp_path / "paper" / "positions.parquet")

    mem = pd.DataFrame([
        {"symbol": "000001", "sector_name": "银行"},
        {"symbol": "000002", "sector_name": "房地产"},
    ])
    mem_path = tmp_path / "sector_membership.parquet"
    hub.write_parquet(mem, mem_path)

    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path)
    monkeypatch.setattr(sectors, "_store", lambda: tmp_path / "sector")

    df = sectors.build_exposure(hub)
    assert len(df) == 2
    for col in ("sector", "weight", "market_value", "position_count"):
        assert col in df.columns

    bank_row = df[df["sector"] == "银行"]
    assert abs(bank_row.iloc[0]["weight"] - 0.7) < 0.01


def test_build_exposure_no_positions(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)
    df = sectors.build_exposure(hub)
    assert df.empty


# ═══════════════════════════════════════════════════════════
# Industry momentum factor (multifactor.py)
# ═══════════════════════════════════════════════════════════

def test_industry_score_with_real_sector_data(monkeypatch):
    from signals.multifactor import MultiFactorScorer

    scorer = MultiFactorScorer(regime="sideways")
    result = scorer.score_components({
        "buffett_score": 60, "safety_margin": 0.2, "roe_5y": 0.15,
        "roe_trend": "up", "momentum_1m": 0.02, "momentum_3m": 0.05,
        "momentum_3m_skip_1m": 0.04, "momentum_6m_skip_1m": 0.06,
        "volatility": 0.25, "trend_strength": 0.03,
        "sector": "银行", "symbol": "000001",
    })
    assert "industry" in result
    assert 20 <= result["industry"] <= 80, f"industry={result['industry']} out of [20,80]"
    assert "total" in result
    assert 0 <= result["total"] <= 100


def test_industry_score_fallback_when_no_data(tmp_path, monkeypatch):
    """When no sector performance data, industry score should default to 50."""
    from signals import multifactor as mf
    from data import datahub

    datahub.reset_datahub()
    hub = datahub.get_datahub()
    monkeypatch.setattr(hub, "store_root", tmp_path)
    monkeypatch.setattr(datahub, "get_datahub", lambda: hub)

    # Clear caches
    monkeypatch.setattr(mf, "_sector_ret_cache", {})
    monkeypatch.setattr(mf, "_symbol_sector_cache", {})

    scorer = mf.MultiFactorScorer()
    result = scorer.score_components({
        "buffett_score": 60, "safety_margin": 0.2, "roe_5y": 0.15,
        "roe_trend": "flat", "momentum_1m": 0.0, "momentum_3m": 0.0,
        "momentum_3m_skip_1m": 0.0, "momentum_6m_skip_1m": 0.0,
        "volatility": 0.25, "trend_strength": 0.0,
        "sector": "银行", "symbol": "000001",
    })
    assert result["industry"] == 50.0, f"expected 50.0 default, got {result['industry']}"


def test_get_sector_momentum_cache(tmp_path, monkeypatch):
    from signals import multifactor as mf
    from data import datahub

    datahub.reset_datahub()
    hub = datahub.get_datahub()
    monkeypatch.setattr(hub, "store_root", tmp_path)
    monkeypatch.setattr(datahub, "get_datahub", lambda: hub)
    monkeypatch.setattr(mf, "_sector_ret_cache", None)

    store = tmp_path / "sector"
    store.mkdir(exist_ok=True)
    perf = pd.DataFrame({
        "sector_code": ["801970", "801180"],
        "sector_name": ["银行", "房地产"],
        "return_1d": [0.005, -0.003], "return_5d": [0.01, -0.02],
        "return_20d": [0.03, -0.05], "return_60d": [0.08, -0.10],
        "volatility": [0.15, 0.25], "member_count": [20, 30],
        "date": "2026-05-23", "latest_date": "2026-05-23", "data_source": "real",
    })
    hub.write_parquet(perf, store / "sector_performance_2026-05-23.parquet")

    result = mf._get_sector_momentum()
    assert len(result) == 2
    assert "银行" in result
    assert result["银行"]["return_20d"] == 0.03
    assert result["房地产"]["return_60d"] == -0.10


def test_lookup_sector_from_membership(tmp_path, monkeypatch):
    from signals import multifactor as mf
    from data import datahub

    datahub.reset_datahub()
    hub = datahub.get_datahub()
    monkeypatch.setattr(hub, "store_root", tmp_path)
    monkeypatch.setattr(datahub, "get_datahub", lambda: hub)
    monkeypatch.setattr(mf, "_symbol_sector_cache", None)

    mem = pd.DataFrame({
        "symbol": ["000001", "000002"],
        "sector_code": ["801970", "801180"],
        "sector_name": ["银行", "房地产"],
    })
    mem_path = tmp_path / "sector_membership.parquet"
    hub.write_parquet(mem, mem_path)
    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path)

    assert mf._lookup_sector("000001", "") == "银行"
    assert mf._lookup_sector("000002", "") == "房地产"
    assert mf._lookup_sector("999999", "银行") == "银行"


def test_multifactor_weights_sum_to_one():
    from signals.multifactor import MFC
    w = MFC.get("weights", {})
    total = sum(w.values())
    assert abs(total - 1.0) < 0.01, f"weights sum={total}"


# ═══════════════════════════════════════════════════════════
# Sector API endpoints
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    from web.api.app import create_app
    return TestClient(create_app())


def test_sector_overview_returns_200(api_client):
    resp = api_client.get("/api/sectors/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "sectors" in data
    assert "total_sectors" in data
    assert isinstance(data["sectors"], list)


def test_sector_overview_fields(api_client):
    resp = api_client.get("/api/sectors/overview")
    data = resp.json()
    if data["sectors"]:
        s = data["sectors"][0]
        for key in ("sector_code", "sector_name", "rank", "return_1d", "return_5d",
                     "return_20d", "return_60d", "volatility", "member_count", "data_source"):
            assert key in s, f"missing field {key}"


def test_sector_exposure_returns_200(api_client):
    resp = api_client.get("/api/sectors/exposure")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "exposure" in data
    assert "total_sectors" in data


def test_sector_detail_returns_200(api_client):
    resp = api_client.get("/api/sectors/%E9%93%B6%E8%A1%8C")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sector_name"] == "银行"
    assert "performance" in data
    assert "signals" in data


def test_sector_stocks_returns_200(api_client):
    resp = api_client.get("/api/sectors/%E9%93%B6%E8%A1%8C/stocks")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "industry" in data, f"response missing industry key: {list(data.keys())}"
    assert data["industry"] == "银行"
    assert "stocks" in data
    assert "total" in data


def test_sector_nonexistent_returns_empty(api_client):
    resp = api_client.get("/api/sectors/%E4%B8%8D%E5%AD%98%E5%9C%A8")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sector_name"] == "不存在"


# ═══════════════════════════════════════════════════════════
# Portfolio sector exposure API
# ═══════════════════════════════════════════════════════════

def test_portfolio_sector_exposure_returns_200(api_client):
    resp = api_client.get("/api/portfolio/sector-exposure")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "exposure" in data
    assert "total_sectors" in data
    assert isinstance(data["exposure"], list)


def test_portfolio_sector_exposure_fields(api_client):
    resp = api_client.get("/api/portfolio/sector-exposure")
    data = resp.json()
    if data["exposure"]:
        e = data["exposure"][0]
        for key in ("sector", "weight", "market_value", "position_count"):
            assert key in e, f"missing field {key}"
        assert 0 <= e["weight"] <= 1


# ═══════════════════════════════════════════════════════════
# Builders: error resilience
# ═══════════════════════════════════════════════════════════

def test_all_builders_run_without_exception(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)
    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: tmp_path / f"{dim}.parquet")
    monkeypatch.setattr(sectors, "_store", lambda: tmp_path / "sector")

    results = {}
    for name, builder in [
        ("membership", sectors.build_membership),
        ("performance", sectors.build_sector_performance),
        ("signals", sectors.build_signal_aggregation),
        ("exposure", sectors.build_exposure),
    ]:
        try:
            df = builder(hub)
            results[name] = {"status": "ok", "rows": len(df)}
        except Exception as e:
            results[name] = {"status": "error", "message": str(e)[:200]}

    errs = [f"{k}: {v['message']}" for k, v in results.items() if v["status"] == "error"]
    assert not errs, f"builders failed: {errs}"
    assert set(results.keys()) == {"membership", "performance", "signals", "exposure"}


# ═══════════════════════════════════════════════════════════
# Data contract validation
# ═══════════════════════════════════════════════════════════

def test_sector_membership_contract():
    from data.contract import derive_contracts_from_registry
    contracts = derive_contracts_from_registry()
    mc = contracts.get("sector_membership")
    assert mc is not None, "sector_membership contract missing"
    assert "symbol" in mc.columns
    assert "sector_code" in mc.columns
    assert "sector_name" in mc.columns


def test_sector_sw_daily_contract():
    from data.contract import derive_contracts_from_registry
    contracts = derive_contracts_from_registry()
    sc = contracts.get("sector_sw_daily")
    assert sc is not None, "sector_sw_daily contract missing"
    assert "ts_code" in sc.columns
    assert "close" in sc.columns


# ═══════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════

def test_full_sector_flow_membership_to_performance(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)
    monkeypatch.setattr(sectors, "_store", lambda: tmp_path / "sector")

    # 1. Build membership
    mem_path = tmp_path / "sector_membership.parquet"
    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path)
    mem = sectors.build_membership(hub)
    assert len(mem) > 0

    # 2. Mock ohlcv for the first few members
    for sym in mem["symbol"].iloc[:5]:
        ohlcv_path = tmp_path / f"ohlcv_daily_{sym}.parquet"
        hub.write_parquet(_make_ohlcv(sym, 120, 0.0008), ohlcv_path)

    def mock_dim_path(dim, **kw):
        if kw.get("symbol"):
            return tmp_path / f"ohlcv_daily_{kw['symbol']}.parquet"
        return mem_path if dim == "sector_membership" else tmp_path / f"{dim}.parquet"

    monkeypatch.setattr(hub, "dimension_path", mock_dim_path)

    perf = sectors.build_sector_performance(hub, lookback_days=120)
    assert len(perf) > 0

    saved = sorted((tmp_path / "sector").glob("sector_performance_*.parquet"))
    assert len(saved) >= 1, "performance should be persisted"


def test_regime_affects_market_score_but_not_industry():
    from signals.multifactor import MultiFactorScorer

    base = {
        "buffett_score": 60, "safety_margin": 0.2, "roe_5y": 0.15,
        "roe_trend": "up", "momentum_1m": 0.02, "momentum_3m": 0.05,
        "momentum_3m_skip_1m": 0.04, "momentum_6m_skip_1m": 0.06,
        "volatility": 0.25, "trend_strength": 0.03,
        "sector": "bank", "symbol": "000001",
    }

    bull = MultiFactorScorer("bull").score_components(base)
    bear = MultiFactorScorer("bear").score_components(base)
    sideways = MultiFactorScorer("sideways").score_components(base)

    scores = {"bull": bull["market"], "bear": bear["market"], "sideways": sideways["market"]}
    assert len(set(scores.values())) >= 2, f"market scores should differ: {scores}"

    # Industry score is data-driven, not regime-dependent
    assert bull["industry"] == bear["industry"] == sideways["industry"]
