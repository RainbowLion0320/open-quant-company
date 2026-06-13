"""Tushare capability catalog and probe call definitions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

TUSHARE_CAPABILITY_CATALOG: dict[str, dict[str, str]] = {
    "stock_basic": {"asset_type": "stock", "data_domain": "reference", "frequency": "event", "mapped_dimensions": "stock_basic"},
    "trade_cal": {"asset_type": "market", "data_domain": "calendar", "frequency": "daily", "mapped_dimensions": "trade_cal"},
    "daily": {"asset_type": "stock", "data_domain": "market_price", "frequency": "daily", "mapped_dimensions": "tushare_stock_daily"},
    "adj_factor": {"asset_type": "stock", "data_domain": "corporate_action", "frequency": "daily", "mapped_dimensions": "adj_factor"},
    "daily_basic": {"asset_type": "stock", "data_domain": "valuation", "frequency": "daily", "mapped_dimensions": "valuation_daily"},
    "fina_indicator": {"asset_type": "stock", "data_domain": "financial_indicator", "frequency": "quarterly", "mapped_dimensions": "fina_indicator"},
    "moneyflow": {"asset_type": "stock", "data_domain": "capital_flow", "frequency": "daily", "mapped_dimensions": "moneyflow_tushare_daily"},
    "moneyflow_mkt_dc": {"asset_type": "stock", "data_domain": "capital_flow", "frequency": "daily", "mapped_dimensions": "moneyflow_mkt_dc"},
    "limit_list_d": {"asset_type": "stock", "data_domain": "market_event", "frequency": "daily", "mapped_dimensions": "limit_list"},
    "top_list": {"asset_type": "stock", "data_domain": "market_event", "frequency": "daily", "mapped_dimensions": "top_list"},
    "broker_recommend": {"asset_type": "stock", "data_domain": "research", "frequency": "monthly", "mapped_dimensions": "broker_recommend"},
    "report_rc": {"asset_type": "stock", "data_domain": "research", "frequency": "monthly", "mapped_dimensions": "research_report"},
    "share_float": {"asset_type": "stock", "data_domain": "share_structure", "frequency": "event", "mapped_dimensions": "share_float"},
    "repurchase": {"asset_type": "stock", "data_domain": "corporate_action", "frequency": "event", "mapped_dimensions": "repurchase"},
    "dividend": {"asset_type": "stock", "data_domain": "corporate_action", "frequency": "event", "mapped_dimensions": "dividend"},
    "cyq_perf": {"asset_type": "stock", "data_domain": "chip_distribution", "frequency": "daily", "mapped_dimensions": "cyq_perf"},
    "stk_factor_pro": {"asset_type": "stock", "data_domain": "factor", "frequency": "daily", "mapped_dimensions": "stk_factor_pro"},
    "stk_mins": {"asset_type": "stock", "data_domain": "market_price", "frequency": "minute", "mapped_dimensions": "stk_mins"},
    "cn_pmi": {"asset_type": "macro", "data_domain": "macro", "frequency": "monthly", "mapped_dimensions": "macro_pmi"},
    "cn_cpi": {"asset_type": "macro", "data_domain": "macro", "frequency": "monthly", "mapped_dimensions": "macro_cpi"},
    "cn_ppi": {"asset_type": "macro", "data_domain": "macro", "frequency": "monthly", "mapped_dimensions": "macro_ppi"},
    "cn_gdp": {"asset_type": "macro", "data_domain": "macro", "frequency": "quarterly", "mapped_dimensions": "macro_gdp"},
    "shibor_lpr": {"asset_type": "macro", "data_domain": "rate", "frequency": "daily", "mapped_dimensions": "risk_free_curve"},
    "fund_basic": {"asset_type": "fund", "data_domain": "reference", "frequency": "event", "mapped_dimensions": "fund_basic"},
    "fund_daily": {"asset_type": "fund", "data_domain": "market_price", "frequency": "daily", "mapped_dimensions": "fund_daily"},
    "fund_nav": {"asset_type": "fund", "data_domain": "nav", "frequency": "daily", "mapped_dimensions": "fund_nav"},
    "fund_portfolio": {"asset_type": "fund", "data_domain": "holding", "frequency": "quarterly", "mapped_dimensions": "fund_portfolio"},
    "fut_daily": {"asset_type": "futures", "data_domain": "market_price", "frequency": "daily", "mapped_dimensions": "futures_daily"},
    "sw_daily": {"asset_type": "sector", "data_domain": "sector_market", "frequency": "daily", "mapped_dimensions": "sector_sw_daily"},
}


def build_tushare_probe_calls(start: str, end: str) -> dict[str, Callable[[Any], object]]:
    sample_symbol = "000001.SZ"
    sample_sw = "801010.SI"
    month = datetime.now().strftime("%Y%m")
    year_start = f"{datetime.now().year}0101"
    return {
        "stock_basic": lambda api: api.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,list_date"),
        "trade_cal": lambda api: api.trade_cal(exchange="SSE", start_date=start, end_date=end),
        "daily": lambda api: api.daily(ts_code=sample_symbol, start_date=start, end_date=end),
        "adj_factor": lambda api: api.adj_factor(ts_code=sample_symbol, start_date=start, end_date=end),
        "daily_basic": lambda api: api.daily_basic(ts_code=sample_symbol, start_date=start, end_date=end),
        "fina_indicator": lambda api: api.fina_indicator(ts_code=sample_symbol, start_date="20240101", end_date=end),
        "moneyflow": lambda api: api.moneyflow(ts_code=sample_symbol, start_date=start, end_date=end),
        "moneyflow_mkt_dc": lambda api: api.moneyflow_mkt_dc(start_date=start, end_date=end),
        "limit_list_d": lambda api: api.limit_list_d(trade_date=end, limit_type="U"),
        "top_list": lambda api: api.top_list(trade_date=end),
        "broker_recommend": lambda api: api.broker_recommend(month=month),
        "report_rc": lambda api: api.report_rc(start_date=start, end_date=end),
        "share_float": lambda api: api.share_float(start_date=start, end_date=end),
        "repurchase": lambda api: api.repurchase(start_date=start, end_date=end),
        "dividend": lambda api: api.dividend(start_date=year_start, end_date=end),
        "cyq_perf": lambda api: api.cyq_perf(trade_date=end),
        "stk_factor_pro": lambda api: api.stk_factor_pro(ts_code=sample_symbol, start_date=start, end_date=end),
        "stk_mins": lambda api: api.stk_mins(ts_code=sample_symbol, freq="1min", start_date=start, end_date=end),
        "cn_pmi": lambda api: api.cn_pmi(),
        "cn_cpi": lambda api: api.cn_cpi(),
        "cn_ppi": lambda api: api.cn_ppi(),
        "cn_gdp": lambda api: api.cn_gdp(),
        "shibor_lpr": lambda api: api.shibor_lpr(),
        "fund_basic": lambda api: api.fund_basic(market="E"),
        "fund_daily": lambda api: api.fund_daily(ts_code="510050.SH"),
        "fund_nav": lambda api: api.fund_nav(ts_code="510050.SH"),
        "fund_portfolio": lambda api: api.fund_portfolio(period="20250331"),
        "fut_daily": lambda api: api.fut_daily(ts_code="IF.CFX"),
        "sw_daily": lambda api: api.sw_daily(ts_code=sample_sw, start_date=start, end_date=end),
    }
