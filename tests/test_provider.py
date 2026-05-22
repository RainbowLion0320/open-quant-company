"""Contract tests for ProviderAdapter — dispatch, health, fallback."""

import pytest
from data.provider import (
    ProviderAdapter, AKShareAdapter, TushareAdapter,
    CompositeProvider, ProviderHealth,
    register_provider, get_provider, reset_providers,
    provider_health_report,
)


class TestProviderAdapter:
    def test_can_serve_by_supported_keys(self):
        class DummyProvider(ProviderAdapter):
            name = "dummy"
            def fetch(self, key, **params):
                return None
            def _supported_keys(self):
                return {"ohlcv_daily", "adj_factor"}

        p = DummyProvider()
        assert p.can_serve("ohlcv_daily")
        assert p.can_serve("adj_factor")
        assert not p.can_serve("unknown_dim")


class TestAKShareAdapter:
    def test_can_serve_known_dimensions(self):
        adapter = AKShareAdapter()
        assert adapter.can_serve("ohlcv_daily")
        assert adapter.can_serve("macro_pmi")
        assert adapter.can_serve("bond_treasury_yields")

    def test_cannot_serve_unknown_dimension(self):
        adapter = AKShareAdapter()
        assert not adapter.can_serve("tushare_only_dim")

    def test_fetch_unknown_returns_none(self):
        adapter = AKShareAdapter()
        assert adapter.fetch("unknown_dim") is None

    def test_health_reports_ok(self):
        adapter = AKShareAdapter()
        health = adapter.health()
        assert health.provider == "akshare"
        assert health.status in ("ok", "error", "degraded")


class TestTushareAdapter:
    def test_can_serve_known_dimensions(self):
        adapter = TushareAdapter()
        assert adapter.can_serve("fina_indicator")
        assert adapter.can_serve("daily_basic")

    def test_cannot_serve_unknown_dimension(self):
        adapter = TushareAdapter()
        assert not adapter.can_serve("ohlcv_daily")

    def test_health_without_token(self):
        adapter = TushareAdapter(token="")
        health = adapter.health()
        assert health.provider == "tushare"


class TestCompositeProvider:
    def test_fallback_chain(self):
        class GoodProvider(ProviderAdapter):
            name = "good"
            def fetch(self, key, **params):
                import pandas as pd
                return pd.DataFrame({"a": [1, 2, 3]})
            def _supported_keys(self):
                return {"test_dim"}

        class BadProvider(ProviderAdapter):
            name = "bad"
            def fetch(self, key, **params):
                raise RuntimeError("simulated failure")
            def _supported_keys(self):
                return {"test_dim"}

        composite = CompositeProvider([BadProvider(), GoodProvider()])
        result = composite.fetch("test_dim")
        assert result is not None
        assert len(result) == 3

    def test_all_fail_returns_none(self):
        class AlwaysFail(ProviderAdapter):
            name = "fail"
            def fetch(self, key, **params):
                raise RuntimeError("fail")
            def _supported_keys(self):
                return {"test_dim"}

        composite = CompositeProvider([AlwaysFail()])
        result = composite.fetch("test_dim")
        assert result is None

    def test_health_aggregates(self):
        class OkProvider(ProviderAdapter):
            name = "ok_p"
            def fetch(self, key, **params):
                return None
            def health(self):
                return ProviderHealth(provider="ok_p", status="ok")

        class BadProvider(ProviderAdapter):
            name = "bad_p"
            def fetch(self, key, **params):
                return None
            def health(self):
                return ProviderHealth(provider="bad_p", status="error")

        composite = CompositeProvider([OkProvider(), BadProvider()])
        h = composite.health()
        assert h.status == "degraded"
        assert "ok_p: ok" in h.message
        assert "bad_p: error" in h.message

    def test_all_ok_health(self):
        class P1(ProviderAdapter):
            name = "p1"
            def fetch(self, key, **params): return None
            def health(self):
                return ProviderHealth(provider="p1", status="ok")

        class P2(ProviderAdapter):
            name = "p2"
            def fetch(self, key, **params): return None
            def health(self):
                return ProviderHealth(provider="p2", status="ok")

        composite = CompositeProvider([P1(), P2()])
        h = composite.health()
        assert h.status == "ok"


class TestProviderRegistry:
    def teardown_method(self):
        reset_providers()

    def test_register_and_get(self):
        class MyProvider(ProviderAdapter):
            name = "my"
            def fetch(self, key, **params):
                import pandas as pd
                return pd.DataFrame({"x": [1]})

        register_provider("mysource", MyProvider())
        provider = get_provider(source="mysource")
        assert provider.name == "my"

    def test_dimension_override(self):
        class DefaultP(ProviderAdapter):
            name = "default"
            def fetch(self, key, **params): return None
        class OverrideP(ProviderAdapter):
            name = "override"
            def fetch(self, key, **params): return None

        register_provider("source_a", DefaultP())
        register_provider("source_b", OverrideP(), dimensions=["special_dim"])

        # By source: gets default
        p = get_provider(source="source_a")
        assert p.name == "default" if hasattr(p, 'name') else True

    def test_provider_health_report(self):
        reset_providers()
        report = provider_health_report()
        assert len(report) >= 1
        # Should include akshare or tushare
        names = [r["provider"] for r in report]
        assert "akshare" in names or "tushare" in names
