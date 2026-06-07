"""Tushare local coverage helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from data.ingestion.tushare_tasks import FUTURES_TUSHARE_EXCHANGE, MINUTE_POLICY
from data.market.assets.etf import ETF_UNIVERSE
from data.market.assets.futures import FUTURES_UNIVERSE
from data.market.symbol_utils import normalize_symbol, to_ts_code
from data.market.symbols import SW_INDUSTRY_FIRST
from data.storage.datahub import DataHub


def symbol_file_coverage(root: str | Path, expected_symbols: list[str]) -> dict[str, object]:
    """Count expected symbol parquet files, accepting 6-digit and Tushare-code filenames."""
    path = Path(root)
    existing_stems = {item.stem for item in path.glob("*.parquet")} if path.exists() else set()
    missing = [
        symbol
        for symbol in expected_symbols
        if not (_candidate_file_stems(symbol) & existing_stems)
    ]
    expected = len(expected_symbols)
    existing = expected - len(missing)
    ratio = round(existing / expected, 4) if expected else 1.0
    return {
        "expected": expected,
        "existing": existing,
        "missing": len(missing),
        "ratio": ratio,
        "missing_sample": missing[:20],
    }


def missing_symbol_files(root: str | Path, expected_symbols: list[str]) -> list[str]:
    path = Path(root)
    existing_stems = {item.stem for item in path.glob("*.parquet")} if path.exists() else set()
    return [
        symbol
        for symbol in expected_symbols
        if not (_candidate_file_stems(symbol) & existing_stems)
    ]


def partition_file_coverage(root: str | Path, expected_partitions: list[str]) -> dict[str, object]:
    path = Path(root)
    existing = {item.stem for item in path.glob("*.parquet")} if path.exists() else set()
    missing = [partition for partition in expected_partitions if partition not in existing]
    expected = len(expected_partitions)
    present = expected - len(missing)
    ratio = round(present / expected, 4) if expected else 1.0
    return {
        "expected": expected,
        "existing": present,
        "missing": len(missing),
        "ratio": ratio,
        "missing_sample": missing[:20],
    }


def file_coverage(path: str | Path) -> dict[str, object]:
    target = Path(path)
    exists = target.exists() and target.stat().st_size > 0
    return {
        "expected": 1,
        "existing": 1 if exists else 0,
        "missing": 0 if exists else 1,
        "ratio": 1.0 if exists else 0.0,
        "missing_sample": [] if exists else [target.name],
    }


def build_tushare_coverage(hub: DataHub, symbols: list[str], trade_days: list[str]) -> dict[str, dict[str, object]]:
    return {
        "stock_basic": file_coverage(hub.dimension_root("stock_basic")),
        "trade_cal": file_coverage(hub.dimension_root("trade_cal")),
        "tushare_stock_daily": partition_file_coverage(hub.dimension_root("tushare_stock_daily"), trade_days),
        "adj_factor": symbol_file_coverage(hub.dimension_root("adj_factor"), symbols),
        "valuation_daily": symbol_file_coverage(hub.dimension_root("valuation_daily"), symbols),
        "fina_indicator": symbol_file_coverage(hub.dimension_root("fina_indicator"), symbols),
        "moneyflow_tushare_daily": partition_file_coverage(hub.dimension_root("moneyflow_tushare_daily"), trade_days),
        "moneyflow_monthly": _count_only_coverage(hub.dimension_root("moneyflow_monthly")),
        "holder_number": symbol_file_coverage(hub.dimension_root("holder_number"), symbols),
        "holder_trade": symbol_file_coverage(hub.dimension_root("holder_trade"), symbols),
        "sector_sw_daily": symbol_file_coverage(hub.dimension_root("sector_sw_daily"), [f"{code}.SI" for code in SW_INDUSTRY_FIRST]),
        "moneyflow_mkt_dc": file_coverage(hub.dimension_root("moneyflow_mkt_dc")),
        "limit_list": partition_file_coverage(hub.dimension_root("limit_list"), trade_days[-60:]),
        "top_list": partition_file_coverage(hub.dimension_root("top_list"), trade_days[-60:]),
        "broker_recommend": _count_only_coverage(hub.dimension_root("broker_recommend")),
        "research_report": _count_only_coverage(hub.dimension_root("research_report")),
        "share_float": file_coverage(hub.dimension_root("share_float")),
        "repurchase": file_coverage(hub.dimension_root("repurchase")),
        "dividend": file_coverage(hub.dimension_root("dividend")),
        "fund_basic": file_coverage(hub.dimension_root("fund_basic")),
        "fund_daily": symbol_file_coverage(hub.dimension_root("fund_daily"), tushare_etf_ts_codes()),
        "fund_nav": symbol_file_coverage(hub.dimension_root("fund_nav"), tushare_etf_ts_codes()),
        "fund_portfolio": partition_file_coverage(hub.dimension_root("fund_portfolio"), _recent_quarter_periods()),
        "futures_daily": partition_file_coverage(hub.dimension_root("futures_daily"), tushare_futures_ts_codes()),
        "cyq_perf": partition_file_coverage(hub.dimension_root("cyq_perf"), trade_days[-60:]),
        "stk_factor_pro": symbol_file_coverage(hub.dimension_root("stk_factor_pro"), symbols),
        "stk_mins": {"expected": 0, "existing": 0, "missing": 0, "ratio": 1.0, "missing_sample": [], "policy": MINUTE_POLICY},
    }


def _candidate_file_stems(symbol: str) -> set[str]:
    normalized = normalize_symbol(symbol)
    stems = {symbol, normalized}
    try:
        stems.add(to_ts_code(normalized))
    except Exception:
        pass
    return {stem for stem in stems if stem}


def _count_only_coverage(root: Path) -> dict[str, object]:
    existing = len(list(root.glob("*.parquet"))) if root.exists() else 0
    return {"expected": 0, "existing": existing, "missing": 0, "ratio": 1.0, "missing_sample": []}


def tushare_etf_ts_codes() -> list[str]:
    return [to_ts_code(code) for code in ETF_UNIVERSE]


def tushare_futures_ts_codes() -> list[str]:
    codes = []
    for code in FUTURES_UNIVERSE:
        text = str(code).strip().upper()
        if not text:
            continue
        if "." in text:
            codes.append(text)
            continue
        exchange = FUTURES_TUSHARE_EXCHANGE.get(text)
        if exchange:
            codes.append(f"{text}.{exchange}")
    return codes


def _recent_quarter_periods(count: int = 4) -> list[str]:
    today = datetime.now()
    periods: list[str] = []
    for year in range(today.year - 2, today.year + 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            period = datetime(year, month, day)
            if period.date() <= today.date():
                periods.append(period.strftime("%Y%m%d"))
    return sorted(periods, reverse=True)[:count]
