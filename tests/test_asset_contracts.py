"""Contract tests for P2-13 multi-asset adapters — data contracts, metadata, data_source."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from unittest.mock import patch


# ── Helpers ──

def _make_ohlcv_df(dates=10):
    """Build a realistic daily OHLCV DataFrame."""
    idx = pd.date_range("2024-01-01", periods=dates, freq="B")
    n = len(idx)
    rng = np.random.default_rng(42)
    close = 100 + rng.normal(0, 2, n).cumsum()
    return pd.DataFrame({
        "date": idx,
        "open": close + rng.normal(0, 0.3, n),
        "high": close + abs(rng.normal(0, 0.5, n)),
        "low": close - abs(rng.normal(0, 0.5, n)),
        "close": close,
        "volume": rng.integers(1000, 10000, n).astype(float),
    })


# ═══════════════════════════════════════
# Test ETF Asset
# ═══════════════════════════════════════

class TestETFAssetContracts:
    def test_data_source_is_real(self):
        from data.market.assets.etf import ETFAsset
        assert ETFAsset.DATA_SOURCE == "real"
        assert ETFAsset.TRADING_CALENDAR == "SSE"

    def test_universe_is_nonempty(self):
        from data.market.assets.etf import ETFAsset, ETF_UNIVERSE
        assert len(ETF_UNIVERSE) >= 50
        assert "518880" in ETF_UNIVERSE

    def test_fetch_daily_returns_ohlcv(self, tmp_path):
        """Mock AKShare to return a known DataFrame, verify columns."""
        from data.market.assets.etf import ETFAsset

        df = _make_ohlcv_df()
        df.rename(columns={"date": "日期", "open": "开盘", "close": "收盘",
                           "high": "最高", "low": "最低", "volume": "成交量"}, inplace=True)

        store = tmp_path / "store"
        with patch("akshare.fund_etf_hist_em", return_value=df):
            adapter = ETFAsset(store_root=store)
            result = adapter.fetch_daily("518880", "2024-01-01", "2024-12-31")
            assert result is not None
            assert all(c in result.columns for c in ("date", "open", "high", "low", "close", "volume"))

    def test_get_metadata_returns_name_and_category(self, tmp_path):
        from data.market.assets.etf import ETFAsset

        store = tmp_path / "store"
        adapter = ETFAsset(store_root=store)
        meta = adapter.get_metadata("510050")
        assert "name" in meta
        assert "category" in meta or "industry" in meta

    def test_get_data_source_returns_dict(self, tmp_path):
        from data.market.assets.etf import ETFAsset

        adapter = ETFAsset(store_root=tmp_path / "store")
        ds = adapter.get_data_source()
        assert ds["data_source"] == "real"
        assert "detail" in ds
        assert ds["currency"] == "CNY"


# ═══════════════════════════════════════
# Test Bond Asset
# ═══════════════════════════════════════

class TestBondAssetContracts:
    def test_data_source_is_proxy_by_default(self):
        from data.market.assets.bond import BondAsset
        assert BondAsset.DATA_SOURCE == "proxy"

    def test_get_data_source_proxy_for_treasury(self, tmp_path):
        from data.market.assets.bond import BondAsset
        adapter = BondAsset(store_root=tmp_path / "store")
        ds = adapter.get_data_source("CN10Y")
        assert ds["data_source"] == "proxy"
        assert "收益率" in ds["detail"]

    def test_get_data_source_real_for_convertible(self, tmp_path):
        from data.market.assets.bond import BondAsset
        adapter = BondAsset(store_root=tmp_path / "store")
        ds = adapter.get_data_source("110059")
        assert ds["data_source"] == "real"
        assert "可转债" in ds["detail"]

    def test_universe_has_treasury_and_convertibles(self):
        from data.market.assets.bond import BondAsset, BOND_UNIVERSE
        assert "CN10Y" in BOND_UNIVERSE
        assert "CN2Y" in BOND_UNIVERSE
        assert any(s.startswith("11") or s.startswith("12") or s.startswith("13") for s in BOND_UNIVERSE)

    def test_fetch_daily_returns_proxy_price_for_CN10Y(self, tmp_path):
        """Bond fetcher synthesizes price from yields."""
        from data.market.assets.bond import BondAsset

        idx = pd.date_range("2024-01-01", periods=30, freq="B")
        yield_df = pd.DataFrame({
            "日期": idx,
            "中国国债收益率10年": np.linspace(2.5, 2.8, 30),
            "中国国债收益率2年": np.linspace(2.0, 2.3, 30),
        })

        store = tmp_path / "store"
        with patch("akshare.bond_zh_us_rate", return_value=yield_df):
            adapter = BondAsset(store_root=store)
            result = adapter.fetch_daily("CN10Y", "2024-01-01", "2024-12-31")
            assert result is not None
            assert "close" in result.columns
            assert "yield" in result.columns


# ═══════════════════════════════════════
# Test Futures Asset
# ═══════════════════════════════════════

class TestFuturesAssetContracts:
    def test_data_source_is_real(self):
        from data.market.assets.futures import FuturesAsset
        assert FuturesAsset.DATA_SOURCE == "real"

    def test_contract_multipliers(self):
        from data.market.assets.futures import FuturesAsset
        m = FuturesAsset._MULTIPLIERS
        assert m["IF"] == 300
        assert m["IC"] == 200
        assert m["IH"] == 300
        assert m["T"] == 10000
        assert m["RB"] == 10
        assert m["AU"] == 1000

    def test_universe_has_index_and_commodity(self):
        from data.market.assets.futures import FuturesAsset, FUTURES_UNIVERSE
        assert "IF" in FUTURES_UNIVERSE
        assert "IC" in FUTURES_UNIVERSE
        assert "RB" in FUTURES_UNIVERSE

    def test_get_data_source_reports_multiplier(self, tmp_path):
        from data.market.assets.futures import FuturesAsset
        adapter = FuturesAsset(store_root=tmp_path / "store")
        ds = adapter.get_data_source("IF")
        assert ds["data_source"] == "real"
        assert ds["multiplier"] == 300

    def test_fetch_daily_columns_include_open_interest(self, tmp_path):
        from data.market.assets.futures import FuturesAsset

        df = _make_ohlcv_df()
        df["open_interest"] = 50000.0
        df.rename(columns={"date": "日期", "open": "开盘价", "close": "收盘价",
                           "high": "最高价", "low": "最低价", "volume": "成交量"}, inplace=True)

        store = tmp_path / "store"
        with patch("akshare.futures_main_sina", return_value=df):
            adapter = FuturesAsset(store_root=store)
            result = adapter.fetch_daily("IF", "2024-01-01", "2024-12-31")
            assert result is not None
            assert "open_interest" in result.columns


# ═══════════════════════════════════════
# Test Crypto Asset
# ═══════════════════════════════════════

class TestCryptoAssetContracts:
    def test_data_source_is_placeholder(self):
        from data.market.assets.crypto import CryptoAsset
        assert CryptoAsset.DATA_SOURCE == "placeholder"
        assert "pending" in CryptoAsset.DATA_SOURCE_DETAIL.lower()

    def test_fetch_daily_returns_none(self, tmp_path):
        from data.market.assets.crypto import CryptoAsset
        adapter = CryptoAsset(store_root=tmp_path / "store")
        result = adapter.fetch_daily("BTC/USDT")
        assert result is None

    def test_universe_has_btc_eth(self, tmp_path):
        from data.market.assets.crypto import CryptoAsset
        adapter = CryptoAsset(store_root=tmp_path / "store")
        u = adapter.get_universe()
        assert "BTC/USDT" in u
        assert "ETH/USDT" in u

    def test_currency_is_usdt(self):
        from data.market.assets.crypto import CryptoAsset
        assert CryptoAsset.CURRENCY == "USDT"
        assert CryptoAsset.TRADING_CALENDAR == "24x7"


# ═══════════════════════════════════════
# Test Asset Registry
# ═══════════════════════════════════════

class TestAssetRegistryWithContracts:
    def test_register_all_adapters(self, tmp_path):
        from data.market.assets.base import AssetRegistry
        from data.market.assets.stock import StockAsset
        from data.market.assets.etf import ETFAsset
        from data.market.assets.bond import BondAsset
        from data.market.assets.futures import FuturesAsset
        from data.market.assets.crypto import CryptoAsset

        s = tmp_path / "store"
        reg = AssetRegistry()
        reg.register(StockAsset(store_root=s))
        reg.register(ETFAsset(store_root=s))
        reg.register(BondAsset(store_root=s))
        reg.register(FuturesAsset(store_root=s))
        reg.register(CryptoAsset(store_root=s))
        assert len(reg.asset_types) == 5

    def test_registry_get_by_type(self, tmp_path):
        from data.market.assets.base import AssetRegistry
        from data.market.assets.etf import ETFAsset

        reg = AssetRegistry()
        reg.register(ETFAsset(store_root=tmp_path / "store"))
        adapter = reg.get("etf")
        assert adapter is not None
        assert adapter.asset_type == "etf"

    def test_all_adapters_report_data_source(self, tmp_path):
        from data.market.assets.base import AssetRegistry
        from data.market.assets.stock import StockAsset
        from data.market.assets.etf import ETFAsset
        from data.market.assets.bond import BondAsset
        from data.market.assets.futures import FuturesAsset
        from data.market.assets.crypto import CryptoAsset

        s = tmp_path / "store"
        reg = AssetRegistry()
        for ad in [StockAsset(store_root=s), ETFAsset(store_root=s), BondAsset(store_root=s),
                   FuturesAsset(store_root=s), CryptoAsset(store_root=s)]:
            reg.register(ad)

        for at in reg.asset_types:
            ds = reg.get(at).get_data_source()
            assert "data_source" in ds
            assert ds["data_source"] in ("real", "proxy", "placeholder", "unknown")

    def test_registry_duplicate_raises(self, tmp_path):
        from data.market.assets.base import AssetRegistry
        from data.market.assets.etf import ETFAsset

        reg = AssetRegistry()
        reg.register(ETFAsset(store_root=tmp_path / "store"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(ETFAsset(store_root=tmp_path / "store"))


# ═══════════════════════════════════════
# Test Multi-Asset Contract Derivation
# ═══════════════════════════════════════

class TestMultiAssetContractsDerivation:
    def test_derive_fund_daily_contract_columns(self):
        from data.quality.contract import derive_contracts_from_registry
        contracts = derive_contracts_from_registry()
        c = contracts.get("fund_daily")
        assert c is not None
        for col in ("date", "open", "high", "low", "close", "volume", "amount"):
            assert col in c.columns, f"fund_daily contract missing column: {col}"

    def test_derive_bond_treasury_yields_contract_columns(self):
        from data.quality.contract import derive_contracts_from_registry
        contracts = derive_contracts_from_registry()
        c = contracts.get("bond_treasury_yields")
        assert c is not None
        assert "date" in c.columns
        assert "中国国债收益率10年" in c.columns

    def test_derive_futures_daily_contract_columns(self):
        from data.quality.contract import derive_contracts_from_registry
        contracts = derive_contracts_from_registry()
        c = contracts.get("futures_daily")
        assert c is not None
        assert "open_interest" in c.columns
        for col in ("date", "open", "high", "low", "close", "volume"):
            assert col in c.columns

    def test_fund_daily_contract_validates_etf_data(self):
        """The derived fund_daily contract should validate a correct ETF DataFrame."""
        from data.quality.contract import derive_contracts_from_registry
        contracts = derive_contracts_from_registry()
        c = contracts.get("fund_daily")
        assert c is not None

        df = _make_ohlcv_df()
        df["amount"] = df["close"] * df["volume"] / 100
        violations = c.validate(df)
        # validate() returns list of ContractViolation objects
        errors = [v for v in violations if v.severity == "error"]
        assert len(errors) == 0, f"Unexpected errors: {errors}"
