"""系统活动监视器 — SQLite 时序库 + 历史趋势"""
import json
import os
import sys

import numpy as np
import pandas as pd
from fastapi import APIRouter, Query
from pathlib import Path
import sqlite3
import psutil

from data.datahub import get_datahub

router = APIRouter(prefix="/api/system", tags=["System"])

HUB = get_datahub()
DB = HUB.system_monitor_path()
TOKEN_CACHE = HUB.token_usage_path()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # routes → api → web → quant-agent


def _query(sql: str, params=()):
    if not DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


def _read_token():
    default = {"hermes": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                          "sessions": 0, "messages": 0, "tool_calls": 0, "api_calls": 0, "cost_usd": 0},
               "external": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "calls": 0, "cost_usd": 0, "sources": []},
               "total": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0},
               "updated_at": None}
    return HUB.read_json(TOKEN_CACHE, default)


def _live_system_totals() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cores_physical": psutil.cpu_count(logical=False) or psutil.cpu_count() or 0,
        "cores_logical": psutil.cpu_count() or 0,
        "memory_total_gb": round(mem.total / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "disk_used_gb": round(disk.used / 1024**3, 1),
    }


def _json_map(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        if isinstance(value, float) and np.isnan(value):
            return {}
    except TypeError:
        pass
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _json_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.generic):
        return value.item()
    return value


@router.get("/monitor")
async def system_monitor():
    """当前快照 (读最新一行 SQLite)"""
    rows = _query("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")
    procs = _query("SELECT * FROM top_processes WHERE ts = (SELECT MAX(ts) FROM top_processes) ORDER BY rank LIMIT 10")

    if not rows:
        return {"status": "no_data"}
    r = rows[0]
    token = _read_token()
    totals = _live_system_totals()

    return {
        "timestamp": r["ts"],
        "cpu": {
            "percent": r["cpu_pct"],
            "cores_physical": totals["cores_physical"],
            "cores_logical": totals["cores_logical"],
            "load_avg": [r["load_1m"], r["load_5m"], r["load_15m"]],
        },
        "memory": {
            "total_gb": totals["memory_total_gb"],
            "used_gb": r["mem_used_gb"],
            "percent": r["mem_pct"],
        },
        "disk": {
            "total_gb": totals["disk_total_gb"],
            "used_gb": totals["disk_used_gb"],
            "percent": r["disk_pct"],
        },
        "battery": {
            "percent": r["bat_pct"],
            "charging": bool(r["bat_charge"]),
        } if r["bat_pct"] is not None else None,
        "top_processes": [{"pid": p["pid"], "name": p["name"], "cpu": p["cpu_pct"], "mem": p["mem_pct"]} for p in procs],
        "token": token,
    }


@router.get("/history")
async def system_history(hours: int = Query(default=24, ge=1, le=720)):
    """历史趋势数据 — CPU/内存/Token 时间序列"""
    rows = _query(f"""
        SELECT ts, cpu_pct, mem_pct, load_1m, token_total_cost,
               token_hermes_in, token_hermes_out
        FROM metrics
        WHERE ts >= datetime('now', '-{hours} hours')
        ORDER BY ts
    """)

    return {
        "hours": hours,
        "points": len(rows),
        "data": rows,
    }

@router.get("/deepseek-usage")
async def deepseek_usage():
    """DeepSeek daily token/cost summary from Parquet."""
    import pandas as pd
    pq = HUB.deepseek_usage_path()
    if not pq.exists():
        return {"data": [], "status": "no_data"}

    df = pd.read_parquet(pq)
    df = df.sort_values("utc_date").tail(28)
    return {
        "data": df.to_dict(orient="records"),
        "models": df["model"].unique().tolist(),
        "dates": sorted(df["utc_date"].unique().tolist()),
        "total_cost": float(df["cost_cny"].sum()),
    }


@router.get("/db-health")
async def db_health():
    """数据库健康检查结果 — 最新一次扫描"""
    import pandas as pd
    pq = HUB.store_root / "db_health.parquet"
    if not pq.exists():
        return {"data": [], "summary": None, "status": "no_data", "message": "尚未运行健康检查，请等待周六自动扫描或手动触发"}

    df = pd.read_parquet(pq)
    summary_rows = df[df["table"] == "__SUMMARY__"]
    data_rows = df[df["table"] != "__SUMMARY__"]

    summary = None
    if len(summary_rows) > 0:
        s = summary_rows.iloc[0].to_dict()
        summary = {
            "tables": int(s.get("columns", 0)),
            "total_size_mb": float(s.get("size_mb", 0)),
            "avg_missing_pct": float(s.get("missing_pct", 0)),
            "total_outliers": int(s.get("outlier_count", 0)),
            "checked_at": str(s.get("checked_at", "")),
        }

    records = []
    for _, r in data_rows.iterrows():
        rec = {k: _json_value(v) for k, v in r.to_dict().items()}
        rec["missing_cols"] = _json_map(rec.get("missing_cols"))
        rec["outlier_cols"] = _json_map(rec.get("outlier_cols"))
        records.append(rec)

    return {
        "data": records,
        "summary": summary,
        "status": "ok",
        "checked_at": summary["checked_at"] if summary else None,
        "api_fallback": os.environ.get("QUANT_ALLOW_API_FALLBACK", "").lower() in {"1", "true", "yes", "on"},
    }


# ── Repair job tracking (in-memory, cleared on restart) ──
import threading
import subprocess as _subprocess
import uuid as _uuid

_repair_jobs: dict[str, dict] = {}
_repair_lock = threading.Lock()


def _repairable_tables() -> set[str]:
    try:
        from scripts.repair_table import REPAIR_MAP
        return set(REPAIR_MAP)
    except Exception:
        return {
            "macro_cpi", "macro_gdp", "macro_lpr", "macro_money_supply",
            "macro_pmi", "macro_ppi", "macro_shibor", "bond_treasury_yields",
        }


def _run_repair(table: str, job_id: str) -> None:
    """Background repair worker."""
    with _repair_lock:
        _repair_jobs[job_id]["status"] = "running"
    try:
        proc = _subprocess.run(
            [sys.executable, "scripts/repair_table.py", table],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=3600,
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


@router.post("/db-health/repair/{table_name}")
async def repair_table(table_name: str):
    """触发单表数据修复 (后台异步)"""
    if table_name not in _repairable_tables():
        return {"status": "error", "message": f"Table '{table_name}' is not repairable"}

    # Cancel existing job for same table
    with _repair_lock:
        for jid, info in list(_repair_jobs.items()):
            if info.get("table") == table_name and info["status"] == "running":
                return {"status": "error", "message": f"Repair already in progress for {table_name}", "job_id": jid}

        job_id = _uuid.uuid4().hex[:12]
        _repair_jobs[job_id] = {"table": table_name, "status": "pending", "stdout": "", "stderr": "", "exit_code": None}

    t = threading.Thread(target=_run_repair, args=(table_name, job_id), daemon=True)
    t.start()

    return {"status": "started", "job_id": job_id, "table": table_name}


@router.get("/db-health/repair-status/{job_id}")
async def repair_status(job_id: str):
    """查询修复进度"""
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
