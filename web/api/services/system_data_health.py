"""Data health and repair job services for system API routes."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pandas as pd

from data.datahub import get_datahub
from web.api.services.system_common import json_map, json_value, safe_float, safe_int


HUB = get_datahub()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_repair_jobs: dict[str, dict] = {}
_repair_lock = threading.Lock()
_REPAIR_JOBS_MAX = 50


def db_health_payload() -> dict:
    pq = HUB.store_root / "db_health.parquet"
    if not pq.exists():
        return {"data": [], "summary": None, "status": "no_data", "message": "尚未运行健康检查，请等待周六自动扫描或手动触发"}

    try:
        df = HUB.read_parquet(pq, default=pd.DataFrame())
    except Exception as exc:
        return {"data": [], "summary": None, "status": "error", "message": f"健康检查结果读取失败: {str(exc)[:120]}"}
    if df is None or df.empty or "table" not in df.columns:
        return {"data": [], "summary": None, "status": "no_data", "message": "健康检查结果为空或结构不完整"}

    summary_rows = df[df["table"] == "__SUMMARY__"]
    data_rows = df[df["table"] != "__SUMMARY__"]

    summary = None
    if len(summary_rows) > 0:
        s = summary_rows.iloc[0].to_dict()
        status_counts = data_rows.get("freshness_status", pd.Series(dtype=str)).value_counts() if len(data_rows) else {}
        summary = {
            "tables": safe_int(s.get("columns", 0)),
            "total_size_mb": safe_float(s.get("size_mb", 0)),
            "avg_missing_pct": safe_float(s.get("missing_pct", 0)),
            "total_outliers": safe_int(s.get("outlier_count", 0)),
            "fresh_tables": safe_int(status_counts.get("fresh", 0)),
            "stale_tables": safe_int(status_counts.get("stale", 0)),
            "missing_tables": safe_int(status_counts.get("missing", 0)),
            "error_tables": safe_int(status_counts.get("error", 0)),
            "checked_at": str(s.get("checked_at", "")),
        }

    records = []
    for _, r in data_rows.iterrows():
        rec = {k: json_value(v) for k, v in r.to_dict().items()}
        rec["missing_cols"] = json_map(rec.get("missing_cols"))
        rec["outlier_cols"] = json_map(rec.get("outlier_cols"))
        rec["time_breakdown"] = json_map(rec.get("time_breakdown"))
        records.append(rec)

    return {
        "data": records,
        "summary": summary,
        "status": "ok",
        "checked_at": summary["checked_at"] if summary else None,
        "api_fallback": os.environ.get("QUANT_ALLOW_API_FALLBACK", "").lower() in {"1", "true", "yes", "on"},
    }


def cleanup_old_repair_jobs() -> None:
    if len(_repair_jobs) <= _REPAIR_JOBS_MAX:
        return
    completed = [
        (jid, info)
        for jid, info in _repair_jobs.items()
        if info.get("status") in ("done", "failed")
    ]
    for jid, _ in completed[:len(completed) - 10]:
        del _repair_jobs[jid]


def repairable_tables() -> set[str]:
    try:
        from scripts.repair_table import REPAIR_MAP
        return set(REPAIR_MAP)
    except Exception:
        return {
            "macro_cpi", "macro_gdp", "macro_lpr", "macro_money_supply",
            "macro_pmi", "macro_ppi", "macro_shibor", "bond_treasury_yields",
            "stock_limit_list", "stock_top_list", "stock_research_report", "stock_dividend",
            "stock_moneyflow_daily", "stock_moneyflow_tushare_daily", "stock_moneyflow_monthly",
            "fund_daily", "fund_portfolio", "fund_nav", "futures_daily",
        }


def run_repair(table: str, job_id: str) -> None:
    with _repair_lock:
        _repair_jobs[job_id]["status"] = "running"
    try:
        proc = subprocess.run(
            [sys.executable, "scripts/repair_table.py", table],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=3600,
        )
        with _repair_lock:
            _repair_jobs[job_id]["stdout"] = proc.stdout[-1000:]
            _repair_jobs[job_id]["stderr"] = proc.stderr[-500:]
            _repair_jobs[job_id]["exit_code"] = proc.returncode
            _repair_jobs[job_id]["status"] = "done" if proc.returncode == 0 else "failed"
    except Exception as e:
        with _repair_lock:
            _repair_jobs[job_id]["status"] = "failed"
            _repair_jobs[job_id]["error"] = str(e)


def start_repair_job(table_name: str) -> dict:
    with _repair_lock:
        for jid, info in list(_repair_jobs.items()):
            if info.get("table") == table_name and info["status"] == "running":
                return {"status": "conflict", "message": f"Repair already in progress for {table_name}", "job_id": jid}

        cleanup_old_repair_jobs()
        job_id = uuid.uuid4().hex[:12]
        _repair_jobs[job_id] = {"table": table_name, "status": "pending", "stdout": "", "stderr": "", "exit_code": None}

    t = threading.Thread(target=run_repair, args=(table_name, job_id), daemon=True)
    t.start()

    return {"status": "started", "job_id": job_id, "table": table_name}


def repair_status_payload(job_id: str) -> dict:
    with _repair_lock:
        job = dict(_repair_jobs.get(job_id) or {})
    if not job:
        return {"status": "not_found"}
    return {
        "status": job["status"],
        "table": job.get("table"),
        "stdout": job.get("stdout", ""),
        "stderr": job.get("stderr", ""),
        "exit_code": job.get("exit_code"),
    }
