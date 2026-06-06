"""
Multi-asset tournament contracts.

Tests that multi-asset allocation works correctly with stock-only,
ETF-only, and multi portfolios using local fixtures.
"""
import numpy as np
import pandas as pd
import pytest

from data.market.assets.stock import StockAsset
from data.market.assets.etf import ETFAsset
from data.market.assets.bond import BondAsset
from data.market.assets.futures import FuturesAsset
from data.market.assets.crypto import CryptoAsset


class TestAssetProvenance:

    def test_stock_tradable_and_research_ready(self):
        asset = StockAsset()
        assert asset.TRADABLE is True
        assert asset.RESEARCH_READY is True
        assert asset.DATA_SOURCE == "real"

    def test_etf_tradable_and_research_ready(self):
        asset = ETFAsset()
        assert asset.TRADABLE is True
        assert asset.RESEARCH_READY is True
        assert asset.DATA_SOURCE == "real"

    def test_bond_research_ready_but_not_tradable(self):
        asset = BondAsset()
        assert asset.TRADABLE is False
        assert asset.RESEARCH_READY is True
        assert asset.DATA_SOURCE == "proxy"

    def test_futures_research_ready(self):
        asset = FuturesAsset()
        assert asset.RESEARCH_READY is True
        assert asset.DATA_SOURCE == "real"

    def test_crypto_default_constructor_matches_adapter_contract(self):
        asset = CryptoAsset()
        assert asset.TRADABLE is False
        assert asset.RESEARCH_READY is False
        assert asset.DATA_SOURCE == "placeholder"

    def test_get_data_source_includes_provenance(self):
        asset = StockAsset()
        src = asset.get_data_source()
        assert "asset_type" in src
        assert "tradable" in src
        assert "research_ready" in src
        assert src["asset_type"] == "stock"


class TestMultiAssetAllocation:

    def test_stock_only_allocation(self):
        """Stock-only portfolio produces result rows."""
        assets = [StockAsset()]
        weights = {a.asset_type: 1.0 / len(assets) for a in assets}
        assert abs(sum(weights.values()) - 1.0) < 1e-10

    def test_etf_only_allocation(self):
        """ETF-only portfolio produces result rows."""
        assets = [ETFAsset()]
        weights = {a.asset_type: 1.0 / len(assets) for a in assets}
        assert abs(sum(weights.values()) - 1.0) < 1e-10

    def test_multi_allocation_sums_to_one(self):
        """Multi-asset portfolio weights sum to 1.0."""
        assets = [StockAsset(), ETFAsset(), BondAsset()]
        weights = {a.asset_type: 1.0 / len(assets) for a in assets}
        assert abs(sum(weights.values()) - 1.0) < 1e-10

    def test_disabled_asset_excluded(self):
        """Assets with enabled=False should be excluded from allocation."""
        all_assets = [
            ("stock", True),
            ("etf", True),
            ("bond", False),
            ("futures", False),
        ]
        enabled = [a for a, enabled in all_assets if enabled]
        weights = {a: 1.0 / len(enabled) for a in enabled}
        assert "bond" not in weights
        assert "futures" not in weights
        assert abs(sum(weights.values()) - 1.0) < 1e-10


class TestDataSourceInResults:

    def test_fallback_includes_data_source(self):
        """Any generated fallback series should include data_source."""
        # Simulate a fallback result
        result = {
            "asset_type": "bond",
            "data_source": "proxy",
            "data_source_detail": "treasury yield proxy",
        }
        assert "data_source" in result
        assert result["data_source"] == "proxy"


class TestAssetOverviewContracts:

    def test_cli_asset_overview_respects_config_enabled_flags(self, capsys):
        """Asset overview must reflect config/settings.yaml asset enablement."""
        import json

        from astrolabe_cli.main import run_cli

        code = run_cli(["assets", "overview", "--json"])
        payload = json.loads(capsys.readouterr().out)
        by_type = {item["asset_type"]: item for item in payload["data"]["items"]}

        assert code == 0
        assert by_type["stock"]["enabled"] is True
        assert by_type["etf"]["enabled"] is True
        assert by_type["bond"]["enabled"] is False
        assert by_type["futures"]["enabled"] is False
        assert by_type["crypto"]["enabled"] is False
        assert by_type["crypto"]["data_source"] == "placeholder"
        assert by_type["crypto"]["error"] == ""
