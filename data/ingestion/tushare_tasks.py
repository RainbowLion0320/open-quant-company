"""Tushare governance task definitions."""

from __future__ import annotations

from dataclasses import dataclass

MINUTE_POLICY = "audit_only"
REPORT_SCHEMA_VERSION = 1
FUTURES_TUSHARE_EXCHANGE = {
    "IF": "CFX",
    "IC": "CFX",
    "IH": "CFX",
    "IM": "CFX",
    "T": "CFX",
    "TF": "CFX",
    "TS": "CFX",
    "RB": "SHF",
    "AU": "SHF",
    "CU": "SHF",
    "SC": "INE",
}


@dataclass(frozen=True)
class BackfillTask:
    key: str
    label: str
    priority: str
    repair_table: str | None = None
    direct: str | None = None
    minute_audit_only: bool = False


BACKFILL_TASKS: list[BackfillTask] = [
    BackfillTask("stock_basic", "Tushare 股票基础信息", "p0", direct="stock_basic"),
    BackfillTask("trade_cal", "Tushare 交易日历", "p0", direct="trade_cal"),
    BackfillTask("tushare_stock_daily", "Tushare 日线原始行情", "p0", direct="tushare_stock_daily"),
    BackfillTask("adj_factor", "复权因子", "p0", direct="adj_factor"),
    BackfillTask("valuation_daily", "每日估值", "p0", direct="valuation_daily"),
    BackfillTask("fina_indicator", "财务指标", "p0", direct="fina_indicator"),
    BackfillTask("moneyflow_tushare_daily", "Tushare 日频资金流", "p0", repair_table="stock_moneyflow_tushare_daily"),
    BackfillTask("moneyflow_monthly", "月频资金流", "p0", repair_table="stock_moneyflow_monthly"),
    BackfillTask("holder_number", "股东户数", "p0", direct="holder_number"),
    BackfillTask("holder_trade", "股东增减持", "p0", direct="holder_trade"),
    BackfillTask("sector_sw_daily", "申万行业日线", "p0", direct="sector_sw_daily"),
    BackfillTask("macro_pmi", "PMI", "p0", repair_table="macro_pmi"),
    BackfillTask("macro_cpi", "CPI", "p0", repair_table="macro_cpi"),
    BackfillTask("macro_ppi", "PPI", "p0", repair_table="macro_ppi"),
    BackfillTask("macro_gdp", "GDP", "p0", repair_table="macro_gdp"),
    BackfillTask("macro_lpr", "LPR", "p0", repair_table="macro_lpr"),
    BackfillTask("moneyflow_mkt_dc", "大盘资金流", "p0", direct="moneyflow_mkt_dc"),
    BackfillTask("limit_list", "涨跌停", "p1", repair_table="stock_limit_list"),
    BackfillTask("top_list", "龙虎榜", "p1", repair_table="stock_top_list"),
    BackfillTask("broker_recommend", "券商金股", "p1", repair_table="stock_broker_recommend"),
    BackfillTask("research_report", "券商研报", "p1", repair_table="stock_research_report"),
    BackfillTask("share_float", "限售解禁", "p1", repair_table="share_float"),
    BackfillTask("repurchase", "股票回购", "p1", repair_table="repurchase"),
    BackfillTask("dividend", "分红送股", "p1", repair_table="stock_dividend"),
    BackfillTask("fund_basic", "基金基础信息", "p2", direct="fund_basic"),
    BackfillTask("fund_daily", "基金日线", "p2", repair_table="fund_daily"),
    BackfillTask("fund_nav", "基金净值", "p2", repair_table="fund_nav"),
    BackfillTask("fund_portfolio", "基金持仓", "p2", repair_table="fund_portfolio"),
    BackfillTask("futures_daily", "期货日线", "p2", repair_table="futures_daily"),
    BackfillTask("cyq_perf", "筹码分布胜率", "p2", direct="cyq_perf"),
    BackfillTask("stk_factor_pro", "专业技术因子", "p2", direct="stk_factor_pro"),
    BackfillTask("stk_mins", "分钟行情", "p2", minute_audit_only=True),
]
