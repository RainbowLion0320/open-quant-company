"""Tushare capability audit, coverage checks, and missing-data backfill."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from core.env_secrets import secret_status
from data.ingestion.tushare_capabilities import build_tushare_probe_calls
from data.ingestion.tushare_coverage import build_tushare_coverage, missing_symbol_files
from data.ingestion.tushare_tasks import BACKFILL_TASKS, MINUTE_POLICY, REPORT_SCHEMA_VERSION
from data.ingestion.tushare_utils import get_tushare_token
from data.market.symbol_utils import normalize_symbol, to_ts_code
from data.market.symbols import CIRCLE_STOCKS, SW_INDUSTRY_FIRST
from data.storage.datahub import DataHub, get_datahub


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


class TushareGovernance:
    """Coordinate Tushare account capability, coverage, and backfill operations."""

    def __init__(self, hub: DataHub | None = None, token: str | None = None):
        self.hub = hub or get_datahub()
        self.token = (token if token is not None else get_tushare_token()).strip()
        self._api: Any | None = None

    def api(self):
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN is not configured in process environment")
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
        probes = build_tushare_probe_calls(start, end)
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
        return build_tushare_coverage(self.hub, symbols, days_list)

    def audit(self, probe_network: bool = True, days: int = 365) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "minute_policy": MINUTE_POLICY,
            "token": secret_status("TUSHARE_TOKEN"),
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
        frames = []
        for status in ("L", "D", "P"):
            df = self._pro_query(
                "stock_basic",
                {"exchange": "", "list_status": status},
                "ts_code,symbol,name,area,industry,list_date,market,exchange,list_status,delist_date",
            )
            if df is not None and len(df):
                frames.append(df)
        merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self._write_frame(merged, self.hub.dimension_root("stock_basic"))

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

    def _fetch_income_statement_missing(self, limit: int = 0) -> int:
        root = self.hub.dimension_root("income_statement")
        root.mkdir(parents=True, exist_ok=True)
        rows = 0
        for symbol in self._missing_symbols("income_statement", limit):
            time.sleep(0.3)
            try:
                df = self._pro_query("income", {"ts_code": to_ts_code(symbol)})
            except Exception as exc:
                if classify_probe_result(exc)[0] in {"rate_limited", "no_permission"}:
                    raise
                continue
            rows += self._write_frame(df, root / f"{normalize_symbol(symbol)}.parquet")
        return rows

    def _fetch_balance_sheet_missing(self, limit: int = 0) -> int:
        root = self.hub.dimension_root("balance_sheet")
        root.mkdir(parents=True, exist_ok=True)
        rows = 0
        for symbol in self._missing_symbols("balance_sheet", limit):
            time.sleep(0.3)
            try:
                df = self._pro_query("balancesheet", {"ts_code": to_ts_code(symbol)})
            except Exception as exc:
                if classify_probe_result(exc)[0] in {"rate_limited", "no_permission"}:
                    raise
                continue
            rows += self._write_frame(df, root / f"{normalize_symbol(symbol)}.parquet")
        return rows

    def _fetch_cashflow_statement_missing(self, limit: int = 0) -> int:
        root = self.hub.dimension_root("cashflow_statement")
        root.mkdir(parents=True, exist_ok=True)
        rows = 0
        for symbol in self._missing_symbols("cashflow_statement", limit):
            time.sleep(0.3)
            try:
                df = self._pro_query("cashflow", {"ts_code": to_ts_code(symbol)})
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
            "income_statement": lambda: self._fetch_income_statement_missing(limit),
            "balance_sheet": lambda: self._fetch_balance_sheet_missing(limit),
            "cashflow_statement": lambda: self._fetch_cashflow_statement_missing(limit),
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
            raise RuntimeError("TUSHARE_TOKEN is not configured in process environment")

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
