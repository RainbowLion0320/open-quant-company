"""Tushare capability audit, coverage checks, and missing-data backfill."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

from core.env_secrets import secret_status
from data.ingestion.tushare_utils import get_tushare_token
from data.market.assets.etf import ETF_UNIVERSE
from data.market.assets.futures import FUTURES_UNIVERSE
from data.market.symbol_utils import normalize_symbol, to_ts_code
from data.market.symbols import CIRCLE_STOCKS, SW_INDUSTRY_FIRST
from data.storage.datahub import DataHub, get_datahub


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


def _now_text() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def classify_probe_result(result: object) -> tuple[str, str]:
    """Classify a Tushare probe response without depending on exact exception classes."""
    if isinstance(result, BaseException):
        message = str(result)
        lowered = message.lower()
        if any(term in lowered for term in ("permission", "no privilege", "没有权限", "无权限", "访问权限")):
            return "no_permission", message
        if any(term in lowered for term in ("rate", "limit", "频次", "每分钟", "每小时", "40203")):
            return "rate_limited", message
        return "error", message
    if result is None:
        return "empty", ""
    try:
        if len(result) == 0:  # type: ignore[arg-type]
            return "empty", ""
    except Exception:
        return "ok", ""
    return "ok", ""


def _candidate_file_stems(symbol: str) -> set[str]:
    normalized = normalize_symbol(symbol)
    stems = {symbol, normalized}
    try:
        stems.add(to_ts_code(normalized))
    except Exception:
        pass
    return {stem for stem in stems if stem}


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


def _etf_ts_codes() -> list[str]:
    return [to_ts_code(code) for code in ETF_UNIVERSE]


def _futures_ts_codes() -> list[str]:
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


def _write_json_report(hub: DataHub, prefix: str, payload: dict[str, Any]) -> Path:
    report_dir = hub.store_root / "_audit"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{prefix}-{_now_text()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _append_backfill_event(hub: DataHub, event: dict[str, Any]) -> None:
    ledger_dir = hub.store_root / "_backfill"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger = ledger_dir / "tushare_backfill.jsonl"
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


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


class TushareGovernance:
    """Coordinate Tushare account capability, coverage, and backfill operations."""

    def __init__(self, hub: DataHub | None = None, token: str | None = None):
        self.hub = hub or get_datahub()
        self.token = (token if token is not None else get_tushare_token()).strip()
        self._api: Any | None = None

    def api(self):
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN or TUSHARE_PRO_TOKEN is not configured in process environment")
        if self._api is None:
            import tushare as ts

            self._api = ts.pro_api(self.token)
        return self._api

    def _safe_probe(self, name: str, call: Callable[[Any], object]) -> dict[str, object]:
        if not self.token:
            return {"status": "missing_secret", "rows": 0, "message": "Tushare token is not configured"}
        try:
            result = call(self.api())
        except Exception as exc:
            status, message = classify_probe_result(exc)
            return {"status": status, "rows": 0, "message": message[:300]}
        status, message = classify_probe_result(result)
        rows = len(result) if hasattr(result, "__len__") and result is not None else 0
        if name == "stk_mins" and status == "ok":
            status = "minute_audit_only"
        return {"status": status, "rows": int(rows), "message": message[:300]}

    def probe_capabilities(self, probe_network: bool = True) -> dict[str, dict[str, object]]:
        if not probe_network:
            return {}

        end = _today()
        start = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
        sample_symbol = "000001.SZ"
        sample_sw = "801010.SI"
        probes: dict[str, Callable[[Any], object]] = {
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
            "broker_recommend": lambda api: api.broker_recommend(month=datetime.now().strftime("%Y%m")),
            "report_rc": lambda api: api.report_rc(start_date=start, end_date=end),
            "share_float": lambda api: api.share_float(start_date=start, end_date=end),
            "repurchase": lambda api: api.repurchase(start_date=start, end_date=end),
            "dividend": lambda api: api.dividend(start_date=f"{datetime.now().year}0101", end_date=end),
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
        return {name: self._safe_probe(name, call) for name, call in probes.items()}

    def trade_days(self, days: int = 365) -> list[str]:
        if not self.token:
            return []
        end = _today()
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        try:
            df = self.api().trade_cal(exchange="SSE", start_date=start, end_date=end)
        except Exception:
            return []
        if df is None or len(df) == 0 or "is_open" not in df or "cal_date" not in df:
            return []
        return sorted(df[df["is_open"] == 1]["cal_date"].astype(str).tolist())

    def coverage(self, days: int = 365) -> dict[str, dict[str, object]]:
        symbols = self.stock_universe()
        days_list = self.trade_days(days) or []
        coverage: dict[str, dict[str, object]] = {
            "stock_basic": file_coverage(self.hub.dimension_root("stock_basic")),
            "trade_cal": file_coverage(self.hub.dimension_root("trade_cal")),
            "tushare_stock_daily": partition_file_coverage(self.hub.dimension_root("tushare_stock_daily"), days_list),
            "adj_factor": symbol_file_coverage(self.hub.dimension_root("adj_factor"), symbols),
            "valuation_daily": symbol_file_coverage(self.hub.dimension_root("valuation_daily"), symbols),
            "fina_indicator": symbol_file_coverage(self.hub.dimension_root("fina_indicator"), symbols),
            "moneyflow_tushare_daily": partition_file_coverage(self.hub.dimension_root("moneyflow_tushare_daily"), days_list),
            "moneyflow_monthly": {"expected": 0, "existing": len(list(self.hub.dimension_root("moneyflow_monthly").glob("*.parquet"))) if self.hub.dimension_root("moneyflow_monthly").exists() else 0, "missing": 0, "ratio": 1.0, "missing_sample": []},
            "holder_number": symbol_file_coverage(self.hub.dimension_root("holder_number"), symbols),
            "holder_trade": symbol_file_coverage(self.hub.dimension_root("holder_trade"), symbols),
            "sector_sw_daily": symbol_file_coverage(self.hub.dimension_root("sector_sw_daily"), [f"{code}.SI" for code in SW_INDUSTRY_FIRST]),
            "moneyflow_mkt_dc": file_coverage(self.hub.dimension_root("moneyflow_mkt_dc")),
            "limit_list": partition_file_coverage(self.hub.dimension_root("limit_list"), days_list[-60:]),
            "top_list": partition_file_coverage(self.hub.dimension_root("top_list"), days_list[-60:]),
            "broker_recommend": {"expected": 0, "existing": len(list(self.hub.dimension_root("broker_recommend").glob("*.parquet"))) if self.hub.dimension_root("broker_recommend").exists() else 0, "missing": 0, "ratio": 1.0, "missing_sample": []},
            "research_report": {"expected": 0, "existing": len(list(self.hub.dimension_root("research_report").glob("*.parquet"))) if self.hub.dimension_root("research_report").exists() else 0, "missing": 0, "ratio": 1.0, "missing_sample": []},
            "share_float": file_coverage(self.hub.dimension_root("share_float")),
            "repurchase": file_coverage(self.hub.dimension_root("repurchase")),
            "dividend": file_coverage(self.hub.dimension_root("dividend")),
            "fund_basic": file_coverage(self.hub.dimension_root("fund_basic")),
            "fund_daily": symbol_file_coverage(self.hub.dimension_root("fund_daily"), _etf_ts_codes()),
            "fund_nav": symbol_file_coverage(self.hub.dimension_root("fund_nav"), _etf_ts_codes()),
            "fund_portfolio": partition_file_coverage(self.hub.dimension_root("fund_portfolio"), _recent_quarter_periods()),
            "futures_daily": partition_file_coverage(self.hub.dimension_root("futures_daily"), _futures_ts_codes()),
            "cyq_perf": partition_file_coverage(self.hub.dimension_root("cyq_perf"), days_list[-60:]),
            "stk_factor_pro": symbol_file_coverage(self.hub.dimension_root("stk_factor_pro"), symbols),
            "stk_mins": {"expected": 0, "existing": 0, "missing": 0, "ratio": 1.0, "missing_sample": [], "policy": MINUTE_POLICY},
        }
        return coverage

    def audit(self, probe_network: bool = True, days: int = 365) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "minute_policy": MINUTE_POLICY,
            "token": secret_status("TUSHARE_TOKEN", aliases=("TUSHARE_PRO_TOKEN",)),
            "capabilities": self.probe_capabilities(probe_network=probe_network),
            "coverage": self.coverage(days=days),
        }
        report_path = _write_json_report(self.hub, "tushare-audit", payload)
        payload["report_path"] = str(report_path)
        return payload

    def _write_frame(self, df: pd.DataFrame | None, path: Path, *, write_empty: bool = False) -> int:
        if df is None:
            return 0
        if len(df) == 0 and not write_empty:
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        self.hub.write_parquet(df, path)
        return int(len(df))

    def stock_universe(self) -> list[str]:
        """Return the current listed stock universe from Tushare stock_basic, with a static fallback."""
        df = self.hub.read_parquet(self.hub.dimension_root("stock_basic"), default=pd.DataFrame())
        if df is not None and len(df) and "symbol" in df.columns:
            symbols = [normalize_symbol(item) for item in df["symbol"].dropna().astype(str)]
            symbols = [item for item in symbols if item.isdigit()]
            if symbols:
                return sorted(set(symbols))
        return list(CIRCLE_STOCKS)

    def _pro_query(self, api_name: str, params: dict[str, Any] | None = None, fields: str = "", timeout: int = 30) -> pd.DataFrame:
        resp = requests.post(
            "http://api.tushare.pro",
            json={"api_name": api_name, "token": self.token, "params": params or {}, "fields": fields},
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(str(payload.get("msg") or payload))
        data = payload.get("data") or {}
        items = data.get("items") or []
        columns = data.get("fields") or []
        return pd.DataFrame(items, columns=columns)

    def _fetch_stock_basic(self) -> int:
        df = self._pro_query(
            "stock_basic",
            {"exchange": "", "list_status": "L"},
            "ts_code,symbol,name,area,industry,list_date,market,exchange",
        )
        return self._write_frame(df, self.hub.dimension_root("stock_basic"))

    def _fetch_trade_cal(self) -> int:
        end = (datetime.now() + timedelta(days=370)).strftime("%Y%m%d")
        df = self._pro_query("trade_cal", {"exchange": "SSE", "start_date": "19900101", "end_date": end})
        return self._write_frame(df, self.hub.dimension_root("trade_cal"))

    def _missing_symbols(self, key: str, limit: int = 0) -> list[str]:
        missing = missing_symbol_files(self.hub.dimension_root(key), self.stock_universe())
        return missing[:limit] if limit else missing

    def _fetch_adj_factor_missing(self, limit: int = 0) -> int:
        root = self.hub.dimension_root("adj_factor")
        root.mkdir(parents=True, exist_ok=True)
        rows = 0
        for symbol in self._missing_symbols("adj_factor", limit):
            time.sleep(0.35)
            try:
                df = self._pro_query("adj_factor", {"ts_code": to_ts_code(symbol)})
            except Exception as exc:
                if classify_probe_result(exc)[0] in {"rate_limited", "no_permission"}:
                    raise
                continue
            rows += self._write_frame(df, root / f"{normalize_symbol(symbol)}.parquet")
        return rows

    def _fetch_valuation_missing(self, limit: int = 0) -> int:
        root = self.hub.dimension_root("valuation_daily")
        root.mkdir(parents=True, exist_ok=True)
        rows = 0
        for symbol in self._missing_symbols("valuation_daily", limit):
            time.sleep(0.3)
            try:
                df = self._pro_query("daily_basic", {"ts_code": to_ts_code(symbol)})
            except Exception as exc:
                if classify_probe_result(exc)[0] in {"rate_limited", "no_permission"}:
                    raise
                continue
            rows += self._write_frame(df, root / f"{normalize_symbol(symbol)}.parquet")
        return rows

    def _fetch_fina_indicator_missing(self, limit: int = 0) -> int:
        root = self.hub.dimension_root("fina_indicator")
        root.mkdir(parents=True, exist_ok=True)
        rows = 0
        for symbol in self._missing_symbols("fina_indicator", limit):
            time.sleep(0.3)
            try:
                df = self._pro_query("fina_indicator", {"ts_code": to_ts_code(symbol)})
            except Exception as exc:
                if classify_probe_result(exc)[0] in {"rate_limited", "no_permission"}:
                    raise
                continue
            rows += self._write_frame(df, root / f"{normalize_symbol(symbol)}.parquet")
        return rows

    def _fetch_holder_number_missing(self, limit: int = 0) -> int:
        root = self.hub.dimension_root("holder_number")
        root.mkdir(parents=True, exist_ok=True)
        rows = 0
        for symbol in self._missing_symbols("holder_number", limit):
            time.sleep(0.3)
            try:
                df = self._pro_query("stk_holdernumber", {"ts_code": to_ts_code(symbol)})
            except Exception as exc:
                if classify_probe_result(exc)[0] in {"rate_limited", "no_permission"}:
                    raise
                continue
            if df is not None and len(df) > 0:
                for col in ("ann_date", "end_date"):
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                if "end_date" in df.columns:
                    df = df.sort_values("end_date")
            rows += self._write_frame(df, root / f"{normalize_symbol(symbol)}.parquet", write_empty=True)
        return rows

    def _fetch_holder_trade_missing(self, limit: int = 0) -> int:
        root = self.hub.dimension_root("holder_trade")
        root.mkdir(parents=True, exist_ok=True)
        rows = 0
        for symbol in self._missing_symbols("holder_trade", limit):
            time.sleep(0.65)
            try:
                df = self._pro_query("stk_holdertrade", {"ts_code": to_ts_code(symbol)})
            except Exception as exc:
                if classify_probe_result(exc)[0] in {"rate_limited", "no_permission"}:
                    raise
                continue
            if df is not None and len(df) > 0:
                if "ann_date" in df.columns:
                    df["ann_date"] = pd.to_datetime(df["ann_date"], errors="coerce")
                    df = df.sort_values("ann_date")
            rows += self._write_frame(df, root / f"{normalize_symbol(symbol)}.parquet", write_empty=True)
        return rows

    def _fetch_tushare_stock_daily(self, limit: int = 0, days: int = 365) -> int:
        trade_days = self.trade_days(days)
        if limit:
            trade_days = trade_days[-limit:]
        root = self.hub.dimension_root("tushare_stock_daily")
        root.mkdir(parents=True, exist_ok=True)
        count = 0
        for trade_date in trade_days:
            path = root / f"{trade_date}.parquet"
            if path.exists():
                continue
            time.sleep(0.3)
            df = self._pro_query("daily", {"trade_date": trade_date})
            count += self._write_frame(df, path)
        return count

    def _fetch_sector_sw_daily(self) -> int:
        root = self.hub.dimension_root("sector_sw_daily")
        root.mkdir(parents=True, exist_ok=True)
        count = 0
        for code in sorted(SW_INDUSTRY_FIRST):
            ts_code = f"{code}.SI"
            path = root / f"{ts_code}.parquet"
            if path.exists():
                continue
            time.sleep(65.0)
            df = self._pro_query("sw_daily", {"ts_code": ts_code})
            count += self._write_frame(df, path)
        return count

    def _fetch_moneyflow_mkt_dc(self) -> int:
        df = self._pro_query("moneyflow_mkt_dc")
        return self._write_frame(df, self.hub.dimension_root("moneyflow_mkt_dc"))

    def _fetch_fund_basic(self) -> int:
        frames = []
        for market in ("E", "O"):
            try:
                time.sleep(0.3)
                df = self._pro_query("fund_basic", {"market": market})
                if df is not None and len(df) > 0:
                    df = df.copy()
                    df["market_filter"] = market
                    frames.append(df)
            except Exception:
                continue
        merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self._write_frame(merged, self.hub.dimension_root("fund_basic"))

    def _fetch_cyq_perf(self, days: int = 365) -> int:
        root = self.hub.dimension_root("cyq_perf")
        root.mkdir(parents=True, exist_ok=True)
        count = 0
        for trade_date in self.trade_days(days)[-60:]:
            path = root / f"{trade_date}.parquet"
            if path.exists():
                continue
            time.sleep(0.35)
            df = self._pro_query("cyq_perf", {"trade_date": trade_date})
            count += self._write_frame(df, path)
        return count

    def _fetch_stk_factor_pro(self, limit: int = 0) -> int:
        universe = self.stock_universe()
        symbols = universe[:limit] if limit else universe
        root = self.hub.dimension_root("stk_factor_pro")
        root.mkdir(parents=True, exist_ok=True)
        count = 0
        for symbol in symbols:
            path = root / f"{symbol}.parquet"
            if path.exists():
                continue
            time.sleep(0.35)
            df = self._pro_query("stk_factor_pro", {"ts_code": to_ts_code(symbol)})
            count += self._write_frame(df, path)
        return count

    def run_direct_task(self, name: str, *, limit: int = 0, days: int = 365) -> int:
        handlers: dict[str, Callable[[], int]] = {
            "stock_basic": self._fetch_stock_basic,
            "trade_cal": self._fetch_trade_cal,
            "adj_factor": lambda: self._fetch_adj_factor_missing(limit),
            "valuation_daily": lambda: self._fetch_valuation_missing(limit),
            "fina_indicator": lambda: self._fetch_fina_indicator_missing(limit),
            "holder_number": lambda: self._fetch_holder_number_missing(limit),
            "holder_trade": lambda: self._fetch_holder_trade_missing(limit),
            "tushare_stock_daily": lambda: self._fetch_tushare_stock_daily(limit, days),
            "sector_sw_daily": self._fetch_sector_sw_daily,
            "moneyflow_mkt_dc": self._fetch_moneyflow_mkt_dc,
            "fund_basic": self._fetch_fund_basic,
            "cyq_perf": lambda: self._fetch_cyq_perf(days),
            "stk_factor_pro": lambda: self._fetch_stk_factor_pro(limit),
        }
        if name not in handlers:
            raise KeyError(f"Unknown direct Tushare task: {name}")
        return handlers[name]()

    def backfill(self, scope: str = "missing", resume: bool = True, dry_run: bool = False, limit: int = 0, days: int = 365) -> dict[str, Any]:
        allowed_priorities = {"p0", "p1", "p2"} if scope in {"missing", "all"} else {scope}
        tasks = [task for task in BACKFILL_TASKS if task.priority in allowed_priorities]
        coverage = self.coverage(days=days)
        planned: list[str] = []
        skipped: list[dict[str, str]] = []

        for task in tasks:
            if task.minute_audit_only:
                skipped.append({"key": task.key, "reason": MINUTE_POLICY})
                continue
            item = coverage.get(task.key, {})
            is_complete = item.get("missing") == 0 and item.get("existing", 0) != 0
            if scope == "missing" and is_complete:
                skipped.append({"key": task.key, "reason": "coverage_complete"})
                continue
            planned.append(task.key)

        result: dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "scope": scope,
            "resume": resume,
            "dry_run": dry_run,
            "limit": limit,
            "days": days,
            "minute_policy": MINUTE_POLICY,
            "planned": planned,
            "completed": [],
            "skipped": skipped,
            "failed": [],
        }

        if dry_run:
            return result
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN or TUSHARE_PRO_TOKEN is not configured in process environment")

        from scripts.repair_table import REPAIR_MAP

        task_by_key = {task.key: task for task in tasks}
        for key in planned:
            task = task_by_key[key]
            event = {"task": key, "started_at": datetime.now().isoformat(timespec="seconds")}
            try:
                if task.repair_table:
                    if task.repair_table not in REPAIR_MAP:
                        raise KeyError(f"repair table not registered: {task.repair_table}")
                    REPAIR_MAP[task.repair_table](limit=limit, days=days)
                    rows = 0
                elif task.direct:
                    rows = self.run_direct_task(task.direct, limit=limit, days=days)
                else:
                    rows = 0
                event.update({"status": "completed", "rows": rows})
                result["completed"].append({"key": key, "rows": rows})
            except Exception as exc:
                status, message = classify_probe_result(exc)
                if status in {"rate_limited", "no_permission"}:
                    event.update({"status": "skipped", "reason": status, "message": message[:300]})
                    result["skipped"].append({"key": key, "reason": status, "message": message[:300]})
                else:
                    event.update({"status": "failed", "error": str(exc)})
                    result["failed"].append({"key": key, "error": str(exc)})
            finally:
                event["finished_at"] = datetime.now().isoformat(timespec="seconds")
                _append_backfill_event(self.hub, event)

        report_path = _write_json_report(self.hub, "tushare-backfill", result)
        result["report_path"] = str(report_path)
        return result


def run_tushare_audit(probe_network: bool = True) -> dict[str, Any]:
    return TushareGovernance().audit(probe_network=probe_network)


def run_tushare_backfill(
    scope: str = "missing",
    resume: bool = True,
    dry_run: bool = False,
    limit: int = 0,
    days: int = 365,
) -> dict[str, Any]:
    return TushareGovernance().backfill(scope=scope, resume=resume, dry_run=dry_run, limit=limit, days=days)
