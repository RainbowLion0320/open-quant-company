"""
ProviderAdapter — unified data-source interface.

Every external data source (AKShare, Tushare, future providers) implements
the same interface.  The registry maps dimension keys to providers so that
callers never need to know which source backs a given dimension.

CompositeProvider chains multiple adapters with fallback: try primary first,
then secondary, etc.  This makes source migration seamless — flip the registry
and consumers keep working.

Usage:
    from data.provider import get_provider, AKShareAdapter, TushareAdapter

    provider = AKShareAdapter()
    df = provider.fetch("ohlcv_daily", symbol="000001", start="20260101")
    health = provider.health()
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import pandas as pd


# ── Provider Health ──


@dataclass
class ProviderHealth:
    provider: str
    status: str = "ok"  # "ok" | "degraded" | "error" | "unavailable"
    last_check: str = ""
    message: str = ""
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


# ── Provider ABC ──


class ProviderAdapter(ABC):
    """Abstract data provider that the registry routes dimension keys to."""

    name: str = "base"

    @abstractmethod
    def fetch(self, key: str, **params: Any) -> pd.DataFrame | None:
        """Fetch data for a registered dimension key.

        Args:
            key: dimension key from data_registry (e.g. "ohlcv_daily")
            **params: dimension-specific parameters (symbol, start, end, etc.)

        Returns:
            DataFrame or None if the provider cannot serve this key.
        """
        ...

    def health(self) -> ProviderHealth:
        """Default health check. Override for real connectivity tests."""
        return ProviderHealth(
            provider=self.name,
            status="ok",
            last_check=datetime.now().isoformat(),
        )

    def can_serve(self, key: str) -> bool:
        """Check if this provider can handle the given dimension key."""
        return key in self._supported_keys()

    def _supported_keys(self) -> set[str]:
        """Override to declare which dimensions this provider serves."""
        return set()

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.name}>"


# ── AKShare Adapter ──


class AKShareAdapter(ProviderAdapter):
    """Adapter for AKShare — free, no-auth, rate-limited to ~3s between calls."""

    name = "akshare"

    # Dimension → (fetcher_module, function_name, default_kwargs)
    _DISPATCH: dict[str, tuple[str, str, dict]] = {
        "ohlcv_daily":       ("data.fetcher",           "get_stock_daily",    {}),
        "financial_summary": ("data.financials",         "get_financial_summary", {}),
        "macro_cpi":         ("data.fetchers.macro",     "MacroFetcher",       {"method": "fetch_indicator", "indicator": "cpi"}),
        "macro_gdp":         ("data.fetchers.macro",     "MacroFetcher",       {"method": "fetch_indicator", "indicator": "gdp"}),
        "macro_lpr":         ("data.fetchers.macro",     "MacroFetcher",       {"method": "fetch_indicator", "indicator": "lpr"}),
        "macro_money_supply":("data.fetchers.macro",     "MacroFetcher",       {"method": "fetch_indicator", "indicator": "money_supply"}),
        "macro_pmi":         ("data.fetchers.macro",     "MacroFetcher",       {"method": "fetch_indicator", "indicator": "pmi"}),
        "macro_ppi":         ("data.fetchers.macro",     "MacroFetcher",       {"method": "fetch_indicator", "indicator": "ppi"}),
        "macro_shibor":      ("data.fetchers.macro",     "MacroFetcher",       {"method": "fetch_indicator", "indicator": "shibor"}),
        "bond_treasury_yields": ("data.assets.bond",     "BondAsset",          {"method": "_load_yields"}),
    }

    def _supported_keys(self) -> set[str]:
        return set(self._DISPATCH)

    def fetch(self, key: str, **params: Any) -> pd.DataFrame | None:
        if key not in self._DISPATCH:
            return None

        module_path, func_name, defaults = self._DISPATCH[key]
        merged = {**defaults, **params}

        try:
            mod = __import__(module_path, fromlist=[func_name])
            target = getattr(mod, func_name)

            # Class-based fetchers (e.g., MacroFetcher, BondAsset)
            if isinstance(target, type):
                instance = target()
                method_name = merged.pop("method", "fetch")
                method = getattr(instance, method_name, None)
                if method is None:
                    return None
                indicator = merged.pop("indicator", "")
                if indicator:
                    return method(indicator, **merged)
                return method(**merged)

            # Function-based fetchers (e.g., get_stock_daily)
            symbol = merged.pop("symbol", "")
            if symbol:
                return target(symbol, **merged)
            return target(**merged)

        except Exception:
            return None

    def health(self) -> ProviderHealth:
        ts = datetime.now().isoformat()
        try:
            import akshare
            return ProviderHealth(
                provider=self.name,
                status="ok",
                last_check=ts,
                message=f"AKShare v{akshare.__version__}",
            )
        except ImportError:
            return ProviderHealth(
                provider=self.name,
                status="error",
                last_check=ts,
                message="AKShare not installed",
            )
        except Exception as e:
            return ProviderHealth(
                provider=self.name,
                status="degraded",
                last_check=ts,
                message=str(e)[:200],
            )


# ── Tushare Adapter ──


class TushareAdapter(ProviderAdapter):
    """Adapter for Tushare — token-gated, rate-limited, requires credits."""

    name = "tushare"

    # Dimension → (api_method_name, default_kwargs)
    _DISPATCH: dict[str, tuple[str, dict]] = {
        "fina_indicator":    ("fina_indicator",    {}),
        "adj_factor":        ("adj_factor",        {}),
        "income_statement":  ("income",            {}),
        "balance_sheet":     ("balancesheet",      {}),
        "cashflow_statement":("cashflow",          {}),
        "daily_basic":       ("daily_basic",       {}),
        "valuation_daily":   ("daily_basic",       {}),
        "margin_detail":     ("margin_detail",     {}),
        "hk_hold":           ("hk_hold",           {}),
        "sw_daily":          ("sw_daily",          {}),
        "holder_number":     ("stk_holdernumber",  {}),
        "limit_list":        ("limit_list_d",      {}),
        "top_list":          ("top_list",          {}),
        "broker_recommend":  ("broker_recommend",  {}),
        "moneyflow_tushare_daily": ("moneyflow_mkt_dc", {}),
    }

    def __init__(self, token: str | None = None):
        self._token = token
        self._api = None

    def _get_api(self):
        if self._api is not None:
            return self._api
        from data.tushare_utils import get_tushare_token
        import tushare as ts
        token = self._token or get_tushare_token()
        if not token:
            raise RuntimeError("Tushare token not configured")
        self._api = ts.pro_api(token)
        return self._api

    def _supported_keys(self) -> set[str]:
        return set(self._DISPATCH)

    def fetch(self, key: str, **params: Any) -> pd.DataFrame | None:
        if key not in self._DISPATCH:
            return None

        method_name, defaults = self._DISPATCH[key]
        merged = {**defaults, **params}

        try:
            api = self._get_api()
            method = getattr(api, method_name, None)
            if method is None:
                return None

            time.sleep(0.3)  # Tushare rate limit
            df = method(**merged)
            return df if df is not None and len(df) > 0 else None
        except Exception:
            return None

    def health(self) -> ProviderHealth:
        ts = datetime.now().isoformat()
        try:
            from data.tushare_utils import get_tushare_token
            token = self._token or get_tushare_token()
            if not token:
                return ProviderHealth(
                    provider=self.name,
                    status="unavailable",
                    last_check=ts,
                    message="Tushare token not configured",
                )
            api = self._get_api()
            # Lightweight check: try stock_basic with limit 1
            df = api.stock_basic(list_status="L", limit=1, fields="ts_code")
            latency = int((datetime.now().timestamp() - datetime.fromisoformat(ts).timestamp()) * 1000)
            return ProviderHealth(
                provider=self.name,
                status="ok",
                last_check=ts,
                message=f"Connected, {len(df) if df is not None else 0} stocks",
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                provider=self.name,
                status="error",
                last_check=ts,
                message=str(e)[:200],
            )


# ── Composite Provider ──


class CompositeProvider(ProviderAdapter):
    """Try providers in order, returning the first successful fetch.

    Usage:
        provider = CompositeProvider([
            TushareAdapter(),    # try Tushare first (richer data)
            AKShareAdapter(),    # fall back to AKShare
        ])
        df = provider.fetch("ohlcv_daily", symbol="000001")
    """

    name = "composite"

    def __init__(self, providers: list[ProviderAdapter]):
        self.providers = providers

    def fetch(self, key: str, **params: Any) -> pd.DataFrame | None:
        errors = []
        for p in self.providers:
            if not p.can_serve(key):
                continue
            try:
                result = p.fetch(key, **params)
                if result is not None and len(result) > 0:
                    return result
                errors.append(f"{p.name}: empty result")
            except Exception as e:
                errors.append(f"{p.name}: {e}")
        return None

    def health(self) -> ProviderHealth:
        statuses = []
        for p in self.providers:
            h = p.health()
            statuses.append(h)

        all_ok = all(s.status == "ok" for s in statuses)
        any_ok = any(s.status == "ok" for s in statuses)
        return ProviderHealth(
            provider=self.name,
            status="ok" if all_ok else ("degraded" if any_ok else "error"),
            last_check=datetime.now().isoformat(),
            message="; ".join(f"{s.provider}: {s.status}" for s in statuses),
            details={"providers": [s.__dict__ for s in statuses]},
        )

    def _supported_keys(self) -> set[str]:
        keys: set[str] = set()
        for p in self.providers:
            keys |= p._supported_keys()
        return keys

    def __repr__(self) -> str:
        names = ", ".join(p.name for p in self.providers)
        return f"<CompositeProvider: [{names}]>"


# ── Registry-driven dispatch ──


# Source → provider mapping (matches data_registry "source" field)
_SOURCE_PROVIDERS: dict[str, ProviderAdapter] = {}

# Dimension-level overrides: when a dimension needs a specific provider
# regardless of its declared source.
_DIMENSION_OVERRIDES: dict[str, ProviderAdapter] = {}


def register_provider(source: str, provider: ProviderAdapter, *,
                      dimensions: list[str] | None = None):
    """Register a provider for a source and optionally specific dimensions."""
    _SOURCE_PROVIDERS[source] = provider
    if dimensions:
        for dim in dimensions:
            _DIMENSION_OVERRIDES[dim] = provider


def get_provider(source: str = "", dimension: str = "") -> ProviderAdapter:
    """Resolve the provider for a source or dimension.

    Resolution order: dimension override → source mapping → composite default.
    """
    if not _SOURCE_PROVIDERS:
        _init_defaults()
    if dimension and dimension in _DIMENSION_OVERRIDES:
        return _DIMENSION_OVERRIDES[dimension]
    if source and source in _SOURCE_PROVIDERS:
        return _SOURCE_PROVIDERS[source]
    return _default_provider()


def _default_provider() -> CompositeProvider:
    """Lazy-initialized default composite provider."""
    if not _SOURCE_PROVIDERS:
        _init_defaults()
    return CompositeProvider(list(_SOURCE_PROVIDERS.values()))


def _init_defaults():
    """Register the default AKShare + Tushare adapters."""
    akshare = AKShareAdapter()
    register_provider("akshare", akshare)
    for dimension in akshare._supported_keys():
        if dimension.startswith("macro_") or dimension == "bond_treasury_yields":
            _DIMENSION_OVERRIDES[dimension] = akshare
    register_provider("tushare_free", TushareAdapter())
    register_provider("tushare_paid", TushareAdapter())


def reset_providers():
    """Clear all registered providers (for testing)."""
    _SOURCE_PROVIDERS.clear()
    _DIMENSION_OVERRIDES.clear()


def provider_health_report() -> list[dict]:
    """Return health status for all registered providers."""
    if not _SOURCE_PROVIDERS:
        _init_defaults()
    seen = set()
    reports = []
    for source, provider in _SOURCE_PROVIDERS.items():
        if provider.name in seen:
            continue
        seen.add(provider.name)
        h = provider.health()
        reports.append({
            "source": source,
            "provider": h.provider,
            "status": h.status,
            "message": h.message,
            "latency_ms": h.latency_ms,
        })
    return reports
