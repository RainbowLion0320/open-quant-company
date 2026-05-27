"""
Sector pipeline & industry momentum tests.

Covers: data/sectors.py builders, signals/multifactor.py industry factor,
sector API endpoints, portfolio sector-exposure API.
"""

import json
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
    from data.symbols import SW_INDUSTRY_FIRST

    hub = _patch_hub_store(tmp_path, monkeypatch)
    mem_path = tmp_path / "sector_membership.parquet"
    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path)

    df = sectors.build_membership(hub)
    valid_names = set(sectors.SW_INDUSTRIES.values())
    for name in df["sector_name"].unique():
        assert name in valid_names, f"unexpected sector name: {name}"
    assert sectors.SW_INDUSTRIES == SW_INDUSTRY_FIRST


# ═══════════════════════════════════════════════════════════
# Performance builder
# ═══════════════════════════════════════════════════════════

def test_build_sector_performance_with_mock_data(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)

    # Mock membership
    mem = pd.DataFrame([
        {"symbol": "000001", "sector_code": "801780", "sector_name": "银行"},
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

    df = sectors.build_sector_performance(hub, lookback_days=120)
    assert len(df) > 0
    for col in ("sector_code", "return_20d", "volatility", "member_count"):
        assert col in df.columns, f"missing {col}"

    bank_row = df[df["sector_code"] == "801780"]
    if not bank_row.empty:
        assert bank_row.iloc[0]["return_20d"] > 0
        assert bank_row.iloc[0]["data_source"] == "proxy"


def test_build_sector_performance_prefers_sw_daily_real_data(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)

    mem = pd.DataFrame([
        {"symbol": "000001", "sector_code": "801780", "sector_name": "银行"},
    ])
    mem_path = tmp_path / "sector" / "membership.parquet"
    hub.write_parquet(mem, mem_path)

    sw_path = tmp_path / "sector" / "sw_daily" / "801780.parquet"
    sw_daily = pd.DataFrame({
        "trade_date": pd.date_range("2026-01-01", periods=80, freq="B"),
        "close": 100 * np.cumprod(np.full(80, 1.002)),
        "pct_chg": np.full(80, 0.2),  # Tushare pct_chg is percent, not fraction.
    })
    hub.write_parquet(sw_daily, sw_path)

    def mock_dim_path(dim, **kw):
        if dim == "sector_membership":
            return mem_path
        if dim == "sector_sw_daily" and kw.get("symbol") == "801780":
            return sw_path
        return tmp_path / dim / f"{kw.get('YYYYMMDD', kw.get('symbol', 'data'))}.parquet"

    monkeypatch.setattr(hub, "dimension_path", mock_dim_path)

    df = sectors.build_sector_performance(hub, lookback_days=80)
    bank_row = df[df["sector_code"] == "801780"].iloc[0]
    assert bank_row["data_source"] == "real"
    assert bank_row["return_20d"] > 0
    assert bank_row["member_count"] == 1


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
        {"symbol": "000001", "sector_code": "801780", "sector_name": "银行"},
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

    state = pd.DataFrame([{
        "cash": 900000.0,
        "frozen_cash": 0.0,
        "peak_equity": 1000000.0,
        "positions": json.dumps({
            "000001": {"market_value": 70000, "volume": 1000, "avg_cost": 70.0},
            "000002": {"market_value": 30000, "volume": 1000, "avg_cost": 30.0},
        }, ensure_ascii=False),
        "order_counter": 0,
        "updated_at": "2026-05-23T00:00:00",
    }])
    hub.write_parquet(state, hub.paper_path("state"))

    mem = pd.DataFrame([
        {"symbol": "000001", "sector_name": "银行"},
        {"symbol": "000002", "sector_name": "房地产"},
    ])
    mem_path = tmp_path / "sector_membership.parquet"
    hub.write_parquet(mem, mem_path)

    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path)

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


def test_build_exposure_reads_canonical_paper_state(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)

    state = pd.DataFrame([{
        "cash": 900000.0,
        "frozen_cash": 0.0,
        "peak_equity": 1000000.0,
        "positions": json.dumps({
            "000001": {"volume": 1000, "avg_cost": 10.0, "name": "平安银行"},
            "000002": {"volume": 500, "avg_cost": 20.0, "name": "万科A"},
        }, ensure_ascii=False),
        "order_counter": 0,
        "updated_at": "2026-05-23T00:00:00",
    }])
    hub.write_parquet(state, hub.paper_path("state"))

    mem = pd.DataFrame([
        {"symbol": "000001", "sector_name": "银行"},
        {"symbol": "000002", "sector_name": "房地产"},
    ])
    mem_path = tmp_path / "sector" / "membership.parquet"
    hub.write_parquet(mem, mem_path)

    monkeypatch.setattr(hub, "dimension_path", lambda dim, **kw: mem_path if dim == "sector_membership" else tmp_path / f"{dim}.parquet")

    df = sectors.build_exposure(hub)
    assert set(df["sector"]) == {"银行", "房地产"}
    assert abs(df["weight"].sum() - 1.0) < 0.01


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
        "sector_code": ["801780", "801180"],
        "sector_name": ["银行", "房地产"],
        "return_1d": [0.005, -0.003], "return_5d": [0.01, -0.02],
        "return_20d": [0.03, -0.05], "return_60d": [0.08, -0.10],
        "volatility": [0.15, 0.25], "member_count": [20, 30],
        "date": "2026-05-23", "latest_date": "2026-05-23", "data_source": "real",
    })
    perf_dir = tmp_path / "sector" / "performance_snapshot"
    perf_dir.mkdir(parents=True, exist_ok=True)
    hub.write_parquet(perf, perf_dir / "20260523.parquet")

    result = mf._get_sector_momentum()
    assert len(result) == 2
    assert "银行" in result
    assert result["银行"]["return_20d"] == 0.03
    assert result["房地产"]["return_60d"] == -0.10


def test_sector_performance_aggregates_turnover_amount_from_member_ohlcv(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)
    monkeypatch.setattr(sectors, "SW_INDUSTRIES", {"801780": "银行", "801750": "计算机"})

    mem_path = tmp_path / "sector_membership.parquet"
    mem = pd.DataFrame({
        "symbol": ["000001", "000002", "000003"],
        "sector_code": ["801780", "801780", "801750"],
        "sector_name": ["银行", "银行", "计算机"],
        "sector_level": [1, 1, 1],
    })
    hub.write_parquet(mem, mem_path)

    dates = pd.date_range("2026-05-18", periods=5, freq="B")

    def stock_frame(close: float, amounts: list[float]) -> pd.DataFrame:
        return pd.DataFrame({
            "date": [str(d.date()) for d in dates],
            "close": [close, close * 1.01, close * 1.02, close * 1.03, close * 1.04],
            "amount": amounts,
            "volume": [1000, 1000, 1000, 1000, 1000],
        })

    frames = {
        "000001": stock_frame(10, [100, 110, 120, 130, 140]),
        "000002": stock_frame(20, [200, 210, 220, 230, 240]),
        "000003": stock_frame(30, [50, 60, 70, 80, 90]),
    }
    for symbol, frame in frames.items():
        hub.write_parquet(frame, tmp_path / f"ohlcv_daily_{symbol}.parquet")

    def mock_dim_path(dim, **kw):
        if dim == "sector_membership":
            return mem_path
        if dim == "ohlcv_daily":
            return tmp_path / f"ohlcv_daily_{kw['symbol']}.parquet"
        return tmp_path / f"{dim}_{kw.get('symbol', '')}.parquet"

    monkeypatch.setattr(hub, "dimension_path", mock_dim_path)

    perf = sectors.build_sector_performance(hub, lookback_days=5)
    bank = perf[perf["sector_name"] == "银行"].iloc[0]
    tech = perf[perf["sector_name"] == "计算机"].iloc[0]

    assert bank["turnover_amount"] == 380.0
    assert bank["amount_5d_avg"] == 340.0
    assert bank["amount_source"] == "proxy"
    assert round(bank["amount_share"], 4) == round(340.0 / 410.0, 4)
    assert tech["turnover_amount"] == 90.0
    assert tech["amount_5d_avg"] == 70.0


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
        "sector_code": ["801780", "801180"],
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
                     "return_20d", "return_60d", "volatility", "member_count",
                     "turnover_amount", "amount_5d_avg", "amount_share", "amount_source",
                     "data_source"):
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


def test_sector_stocks_endpoint_is_retired(api_client):
    resp = api_client.get("/api/sectors/%E9%93%B6%E8%A1%8C/stocks")
    assert resp.status_code == 410, resp.text


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


def test_sector_performance_snapshot_contract():
    from data.contract import derive_contracts_from_registry
    contracts = derive_contracts_from_registry()
    pc = contracts.get("sector_performance_snapshot")
    assert pc is not None, "sector_performance_snapshot contract missing"
    assert "sector_code" in pc.columns
    assert "return_20d" in pc.columns
    assert "data_source" in pc.columns


# ═══════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════

def test_full_sector_flow_membership_to_performance(tmp_path, monkeypatch):
    from data import sectors

    hub = _patch_hub_store(tmp_path, monkeypatch)
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

    saved = sorted(tmp_path.glob("sector_performance_snapshot.parquet"))
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
