"""Static source capability catalog metadata."""

from __future__ import annotations

from typing import Any

SOURCE_IDS = (
    "akshare",
    "tushare",
    "tencent_finance",
    "eastmoney",
    "sina_finance",
    "tonghuashun",
    "exchange_official",
    "cninfo",
    "computed",
)

RECOMMENDED_AUDIT_COMMAND = "astroq data sources audit --source all --discovery-depth catalog --json"

SOURCE_LABELS = {
    "akshare": "AKShare",
    "tushare": "Tushare",
    "tencent_finance": "Tencent Finance",
    "eastmoney": "Eastmoney",
    "sina_finance": "Sina Finance",
    "tonghuashun": "Tonghuashun",
    "exchange_official": "Exchange Official",
    "cninfo": "CNINFO",
    "computed": "Computed",
}

SOURCE_NOTES = {
    "akshare": "Local Python package introspection; safe probes are allowlisted separately.",
    "tushare": "Token-gated official Pro API; live status comes from current TUSHARE_TOKEN probes.",
    "tencent_finance": "Candidate direct source and AKShare backend observed in project fetchers.",
    "eastmoney": "Candidate direct source and AKShare backend observed in project fetchers.",
    "sina_finance": "Candidate direct source and AKShare backend observed in project fetchers.",
    "tonghuashun": "Candidate direct source and AKShare backend observed in project fetchers.",
    "exchange_official": "Official exchange or announcement source candidate; no default backfill.",
    "cninfo": "Announcement and filings candidate source; no default backfill.",
    "computed": "Internal derived datasets produced from registered upstream dimensions.",
}

SOURCE_STATUS = {
    "akshare": "active",
    "tushare": "active",
    "computed": "internal",
}

CANDIDATE_CAPABILITIES = [
    {
        "source": "tencent_finance",
        "interface": "stock_zh_index_daily_tx",
        "asset_type": "index",
        "data_domain": "market_price",
        "frequency": "daily",
        "backend": "akshare",
        "integration_status": "backend_source",
        "mapped_dimensions": [],
        "probe_strategy": "documented_backend_only",
        "access_status": "candidate",
        "discovery_status": "discovered",
        "discovery_scope": "package_backend_mapping",
        "probe_status": "not_probed",
        "notes": "Observed as AKShare index source='tx'; direct provider adapter is not production-ready.",
    },
    {
        "source": "tencent_finance",
        "interface": "qt_gtimg_realtime_quote",
        "asset_type": "stock",
        "data_domain": "market_quote",
        "frequency": "intraday",
        "backend": "direct_web",
        "integration_status": "candidate",
        "mapped_dimensions": [],
        "probe_strategy": "safe_read_only_http_probe",
        "access_status": "manual_review",
        "discovery_status": "discovered",
        "discovery_scope": "static_endpoint_catalog",
        "probe_status": "not_probed",
        "endpoint_pattern": "https://qt.gtimg.cn/q={symbol}",
        "source_url": "https://qt.gtimg.cn/",
        "parser": "data.ingestion.tencent_finance.parse_realtime_quote",
        "field_sample": ["symbol", "name", "last_price", "previous_close", "open", "volume", "timestamp"],
        "notes": "Observed public web quote endpoint; non-standard text payload, no official open API contract found.",
    },
    {
        "source": "tencent_finance",
        "interface": "ifzq_fqkline",
        "asset_type": "stock",
        "data_domain": "market_price",
        "frequency": "daily",
        "backend": "direct_web",
        "integration_status": "candidate",
        "mapped_dimensions": [],
        "probe_strategy": "safe_read_only_http_probe",
        "access_status": "manual_review",
        "discovery_status": "discovered",
        "discovery_scope": "static_endpoint_catalog",
        "probe_status": "not_probed",
        "endpoint_pattern": "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,{start},{end},{limit},{adjust}",
        "source_url": "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        "parser": "data.ingestion.tencent_finance.parse_fqkline_payload",
        "field_sample": ["date", "open", "close", "high", "low", "volume", "adjust"],
        "notes": "Observed public web K-line endpoint; candidate fallback only until field drift, rate limits, and authorization are reviewed.",
    },
    {
        "source": "eastmoney",
        "interface": "stock_zh_index_daily_em",
        "asset_type": "index",
        "data_domain": "market_price",
        "frequency": "daily",
        "backend": "akshare",
        "integration_status": "backend_source",
        "mapped_dimensions": [],
        "probe_strategy": "documented_backend_only",
        "access_status": "candidate",
        "discovery_status": "discovered",
        "discovery_scope": "package_backend_mapping",
        "probe_status": "not_probed",
        "notes": "Observed as AKShare index source='em'; direct provider adapter is not production-ready.",
    },
    {
        "source": "eastmoney",
        "interface": "stock_zh_a_spot_em",
        "asset_type": "stock",
        "data_domain": "market_quote",
        "frequency": "intraday",
        "backend": "akshare",
        "integration_status": "backend_source",
        "mapped_dimensions": [],
        "probe_strategy": "documented_backend_only",
        "access_status": "candidate",
        "discovery_status": "discovered",
        "discovery_scope": "package_backend_mapping",
        "probe_status": "not_probed",
    },
    {
        "source": "sina_finance",
        "interface": "stock_zh_index_daily",
        "asset_type": "index",
        "data_domain": "market_price",
        "frequency": "daily",
        "backend": "akshare",
        "integration_status": "backend_source",
        "mapped_dimensions": [],
        "probe_strategy": "documented_backend_only",
        "access_status": "candidate",
        "discovery_status": "discovered",
        "discovery_scope": "package_backend_mapping",
        "probe_status": "not_probed",
    },
    {
        "source": "sina_finance",
        "interface": "futures_main_sina",
        "asset_type": "futures",
        "data_domain": "market_price",
        "frequency": "daily",
        "backend": "akshare",
        "integration_status": "backend_source",
        "mapped_dimensions": ["futures_daily"],
        "probe_strategy": "documented_backend_only",
        "access_status": "candidate",
        "discovery_status": "discovered",
        "discovery_scope": "package_backend_mapping",
        "probe_status": "not_probed",
    },
    {
        "source": "tonghuashun",
        "interface": "stock_financial_abstract_ths",
        "asset_type": "stock",
        "data_domain": "financial_summary",
        "frequency": "quarterly",
        "backend": "akshare",
        "integration_status": "backend_source",
        "mapped_dimensions": ["financial_summary"],
        "probe_strategy": "documented_backend_only",
        "access_status": "candidate",
        "discovery_status": "discovered",
        "discovery_scope": "package_backend_mapping",
        "probe_status": "not_probed",
    },
    {
        "source": "exchange_official",
        "interface": "official_announcements",
        "asset_type": "stock",
        "data_domain": "announcement",
        "frequency": "event",
        "backend": "",
        "integration_status": "candidate",
        "mapped_dimensions": [],
        "probe_strategy": "manual_review",
        "access_status": "manual_review",
        "discovery_status": "discovered",
        "discovery_scope": "manual_seed",
        "probe_status": "manual_review",
    },
    {
        "source": "cninfo",
        "interface": "listed_company_filings",
        "asset_type": "stock",
        "data_domain": "announcement",
        "frequency": "event",
        "backend": "",
        "integration_status": "candidate",
        "mapped_dimensions": [],
        "probe_strategy": "manual_review",
        "access_status": "manual_review",
        "discovery_status": "discovered",
        "discovery_scope": "manual_seed",
        "probe_status": "manual_review",
    },
    {
        "source": "computed",
        "interface": "sector_performance_snapshot",
        "asset_type": "sector",
        "data_domain": "derived_snapshot",
        "frequency": "daily",
        "backend": "internal",
        "integration_status": "project_integrated",
        "mapped_dimensions": ["sector_performance_snapshot"],
        "probe_strategy": "internal_registry",
        "access_status": "internal",
        "discovery_status": "project_integrated",
        "discovery_scope": "internal_registry",
        "probe_status": "internal",
    },
    {
        "source": "computed",
        "interface": "features_all_daily_asof",
        "asset_type": "stock",
        "data_domain": "feature_store",
        "frequency": "daily",
        "backend": "internal",
        "integration_status": "project_integrated",
        "mapped_dimensions": ["features_all"],
        "probe_strategy": "internal_registry",
        "access_status": "internal",
        "discovery_status": "project_integrated",
        "discovery_scope": "internal_registry",
        "probe_status": "internal",
    },
]

AKSHARE_NAME_DIMENSIONS = {
    "stock_zh_a_hist": ["ohlcv_daily"],
    "stock_zh_a_daily": ["ohlcv_daily"],
    "stock_financial_abstract_ths": ["financial_summary"],
    "macro_china_cpi": ["macro_cpi"],
    "macro_china_gdp": ["macro_gdp"],
    "macro_china_lpr": ["macro_lpr"],
    "macro_china_money_supply": ["macro_money_supply"],
    "macro_china_pmi": ["macro_pmi"],
    "macro_china_ppi": ["macro_ppi"],
    "macro_china_shibor": ["macro_shibor"],
    "bond_zh_us_rate": ["bond_treasury_yields"],
}

AKSHARE_FREQUENCY_OVERRIDES = {
    "stock_financial_abstract_ths": "quarterly",
    "macro_china_cpi": "monthly",
    "macro_china_gdp": "quarterly",
    "macro_china_lpr": "monthly",
    "macro_china_money_supply": "monthly",
    "macro_china_pmi": "monthly",
    "macro_china_ppi": "monthly",
    "macro_china_shibor": "daily",
    "bond_zh_us_rate": "daily",
}


def source_catalog() -> list[dict[str, Any]]:
    return [
        {
            "source": source,
            "label": SOURCE_LABELS[source],
            "status": SOURCE_STATUS.get(source, "candidate"),
            "requires_token": source == "tushare",
            "discovery_method": _discovery_method(source),
            "discovery_scope": _discovery_scope(source),
            "notes": SOURCE_NOTES[source],
        }
        for source in SOURCE_IDS
    ]


def _discovery_method(source: str) -> str:
    if source == "akshare":
        return "local_package_introspection"
    if source == "tushare":
        return "account_probe"
    if source == "computed":
        return "internal_registry"
    return "deterministic_catalog"


def _discovery_scope(source: str) -> str:
    if source == "akshare":
        return "full_local_introspection"
    if source == "tushare":
        return "official_catalog_account_probe"
    if source == "computed":
        return "internal_registry"
    if source in {"exchange_official", "cninfo"}:
        return "manual_seed"
    return "package_backend_mapping_static_endpoint_catalog"
