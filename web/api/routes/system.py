"""系统活动监视器 — SQLite 时序库 + 历史趋势"""
import json
import os
import sys

import numpy as np
import pandas as pd
from datetime import datetime
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
        with sqlite3.connect(str(DB)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception:
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
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _safe_int(value, default: int = 0) -> int:
    value = _json_value(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    value = _json_value(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    pq = HUB.deepseek_usage_path()
    if not pq.exists():
        return {"data": [], "status": "no_data"}

    try:
        df = HUB.read_parquet(pq, default=pd.DataFrame())
    except Exception as exc:
        return {"data": [], "status": "error", "message": f"DeepSeek usage parquet read failed: {str(exc)[:120]}"}
    if df is None or df.empty or not {"utc_date", "model"}.issubset(df.columns):
        return {"data": [], "status": "no_data"}

    numeric_cols = [
        "input_cache_hit", "input_cache_miss", "input_tokens", "output_tokens",
        "total_tokens", "requests", "cost_cny",
    ]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["utc_date"] = df["utc_date"].astype(str).str.slice(0, 10)
    df["model"] = df["model"].astype(str)
    df = df.sort_values(["utc_date", "model"]).tail(60)
    records = [{k: _json_value(v) for k, v in row.items()} for row in df.to_dict(orient="records")]
    return {
        "data": records,
        "models": df["model"].unique().tolist(),
        "dates": sorted(df["utc_date"].unique().tolist()),
        "total_cost": float(df["cost_cny"].sum()),
        "status": "ok",
    }


@router.get("/db-health")
async def db_health():
    """数据库健康检查结果 — 最新一次扫描"""
    import pandas as pd
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
            "tables": _safe_int(s.get("columns", 0)),
            "total_size_mb": _safe_float(s.get("size_mb", 0)),
            "avg_missing_pct": _safe_float(s.get("missing_pct", 0)),
            "total_outliers": _safe_int(s.get("outlier_count", 0)),
            "fresh_tables": _safe_int(status_counts.get("fresh", 0)),
            "stale_tables": _safe_int(status_counts.get("stale", 0)),
            "missing_tables": _safe_int(status_counts.get("missing", 0)),
            "error_tables": _safe_int(status_counts.get("error", 0)),
            "checked_at": str(s.get("checked_at", "")),
        }

    records = []
    for _, r in data_rows.iterrows():
        rec = {k: _json_value(v) for k, v in r.to_dict().items()}
        rec["missing_cols"] = _json_map(rec.get("missing_cols"))
        rec["outlier_cols"] = _json_map(rec.get("outlier_cols"))
        rec["time_breakdown"] = _json_map(rec.get("time_breakdown"))
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
_REPAIR_JOBS_MAX = 50


def _cleanup_old_repair_jobs():
    """Evict completed jobs when the dict exceeds max size."""
    if len(_repair_jobs) <= _REPAIR_JOBS_MAX:
        return
    completed = [(jid, info) for jid, info in _repair_jobs.items()
                 if info.get("status") in ("done", "failed")]
    for jid, _ in completed[:len(completed) - 10]:
        del _repair_jobs[jid]


def _repairable_tables() -> set[str]:
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

    with _repair_lock:
        for jid, info in list(_repair_jobs.items()):
            if info.get("table") == table_name and info["status"] == "running":
                return {"status": "error", "message": f"Repair already in progress for {table_name}", "job_id": jid}

        _cleanup_old_repair_jobs()
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


@router.get("/api-health")
async def api_health():
    """检查各 API 配置健康状态 (不含 token 值)。"""
    results = []

    # AKShare
    try:
        import akshare
        results.append({"name": "AKShare", "status": "ok", "detail": f"v{akshare.__version__}"})
    except ImportError:
        results.append({"name": "AKShare", "status": "error", "detail": "未安装"})

    # Tushare
    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")
    if token:
        try:
            import requests as _r
            resp = _r.post("http://api.tushare.pro", json={"api_name": "stock_basic", "token": token, "params": {"limit": 1, "list_status": "L"}, "fields": "ts_code,name"}, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    results.append({"name": "Tushare", "status": "ok", "detail": "已配置，API 正常"})
                else:
                    results.append({"name": "Tushare", "status": "error", "detail": data.get("msg", "未知错误")})
            else:
                results.append({"name": "Tushare", "status": "error", "detail": f"HTTP {resp.status_code}"})
        except Exception as e:
            results.append({"name": "Tushare", "status": "warn", "detail": f"已配置但无法连接: {str(e)[:60]}"})
    else:
        results.append({"name": "Tushare", "status": "missing", "detail": "未配置 TUSHARE_TOKEN"})

    # DeepSeek
    ds_key = os.environ.get("DEEPSEEK_API_KEY")
    if ds_key:
        masked = ds_key[:4] + "****" + ds_key[-4:] if len(ds_key) > 8 else "****"
        results.append({"name": "DeepSeek", "status": "ok", "detail": f"已配置 ({masked})"})
    else:
        results.append({"name": "DeepSeek", "status": "missing", "detail": "未配置 DEEPSEEK_API_KEY"})

    # Hindsight
    try:
        import httpx
        with httpx.Client(timeout=3) as client:
            r = client.get("http://localhost:9177/health")
            if r.status_code == 200:
                results.append({"name": "Hindsight", "status": "ok", "detail": "端口 9177 正常"})
            else:
                results.append({"name": "Hindsight", "status": "error", "detail": f"HTTP {r.status_code}"})
    except Exception:
        results.append({"name": "Hindsight", "status": "warn", "detail": "端口 9177 无响应"})

    # Telegram — config in notify.yaml (flat keys)
    try:
        cfg_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "notify.yaml"
        import yaml
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
        if cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID"):
            results.append({"name": "Telegram", "status": "ok", "detail": f"已配置 (chat_id={cfg['TELEGRAM_CHAT_ID']})"})
        elif cfg.get("TELEGRAM_BOT_TOKEN") or cfg.get("TELEGRAM_CHAT_ID"):
            results.append({"name": "Telegram", "status": "warn", "detail": "配置不完整"})
        else:
            results.append({"name": "Telegram", "status": "disabled", "detail": "未配置"})
    except Exception:
        results.append({"name": "Telegram", "status": "unknown", "detail": "无法读取配置"})

    ok = sum(1 for r in results if r["status"] == "ok")
    warn = sum(1 for r in results if r["status"] == "warn")
    err = sum(1 for r in results if r["status"] in ("error", "missing"))
    return {
        "items": results,
        "summary": f"{ok} OK, {warn} 警告, {err} 异常",
        "all_ok": err == 0 and warn == 0,
    }


@router.get("/cron-jobs")
async def cron_jobs():
    """Cron job 状态 (读取 ~/.hermes/cron/jobs.json)"""
    import json as _json
    cron_path = Path.home() / ".hermes" / "cron" / "jobs.json"
    if not cron_path.exists():
        return {"jobs": [], "status": "no_data"}

    try:
        with open(cron_path) as f:
            data = _json.load(f)
    except Exception as exc:
        return {"jobs": [], "status": "error", "message": f"无法读取 cron jobs: {str(exc)[:120]}"}

    compact = []
    for job in data.get("jobs", []):
        compact.append({
            "name": job.get("name", ""),
            "schedule": job.get("schedule_display", ""),
            "last_run": job.get("last_run_at"),
            "last_status": job.get("last_status"),
            "next_run": job.get("next_run_at"),
            "enabled": job.get("enabled", True),
            "state": job.get("state", ""),
            "no_agent": job.get("no_agent", False),
        })

    ok = sum(1 for j in compact if j["last_status"] == "ok")
    err = sum(1 for j in compact if j["last_status"] == "error")
    other = len(compact) - ok - err
    return {
        "jobs": compact,
        "summary": f"{len(compact)} jobs, {ok} OK, {err} err" + (f", {other} other" if other else ""),
        "checked_at": datetime.fromtimestamp(Path(cron_path).stat().st_mtime).isoformat(),
    }


@router.get("/service-status")
async def service_status():
    """CDP / MCP / Cookie 状态检查"""
    import json as _json
    import httpx

    items = []

    # ── Chrome CDP (port 9222) ──
    cdp_ok = False
    cdp_detail = "端口 9222 无响应"
    try:
        with httpx.Client(timeout=3) as client:
            r = client.get("http://localhost:9222/json/version")
            if r.status_code == 200:
                data = r.json()
                browser = data.get("Browser", "Chrome")
                cdp_ok = True
                cdp_detail = f"{browser}, CDP v{data.get('Protocol-Version','?')}"
    except Exception:
        pass

    items.append({
        "name": "Chrome CDP",
        "status": "ok" if cdp_ok else "error",
        "detail": cdp_detail,
    })

    # ── DeepSeek cookie ──
    cookie_ok = False
    cookie_age_days = None
    cookie_remaining = None
    cookie_detail = "未检测"

    if cdp_ok:
        try:
            with httpx.Client(timeout=3) as client:
                pages_r = client.get("http://localhost:9222/json")
                pages = pages_r.json()
                ds_page = next((p for p in pages if "deepseek.com" in p.get("url", "").lower()), None)
                if ds_page:
                    ws_url = ds_page["webSocketDebuggerUrl"]
                    import websocket
                    ws = websocket.create_connection(ws_url, timeout=5)
                    try:
                        mid = [0]
                        def _cmd(method, params=None):
                            mid[0] += 1
                            ws.send(_json.dumps({"id": mid[0], "method": method, "params": params or {}}))
                            while True:
                                raw = ws.recv()
                                if isinstance(raw, bytes): raw = raw.decode()
                                try: msg = _json.loads(raw)
                                except: continue
                                if msg.get("id") == mid[0]:
                                    return msg.get("result", {})

                        _cmd("Runtime.enable")
                        r = _cmd("Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
                        url = r.get("result", {}).get("value", "")
                        is_auth = "sign_in" not in url and "login" not in url.lower()
                    finally:
                        ws.close()

                    # Cookie file age
                    cookie_path = Path("/tmp/chrome-cdp/Default/Cookies")
                    if cookie_path.exists():
                        cookie_mtime = cookie_path.stat().st_mtime
                        cookie_age_days = (datetime.now().timestamp() - cookie_mtime) / 86400
                        cookie_remaining = max(0, 30 - cookie_age_days)

                    if is_auth:
                        cookie_ok = True
                        cookie_detail = f"已认证"
                        if cookie_remaining is not None:
                            cookie_detail += f", 剩余约 {cookie_remaining:.0f} 天"
                    else:
                        cookie_detail = "未登录 (需扫码)"
                else:
                    cookie_detail = "DeepSeek 页面未打开"
        except Exception as e:
            cookie_detail = f"检测失败: {str(e)[:50]}"
    else:
        cookie_detail = "CDP 不可用"

    items.append({
        "name": "DeepSeek Cookie",
        "status": "ok" if cookie_ok else "warn",
        "detail": cookie_detail,
        "cookie_remaining_days": round(cookie_remaining, 1) if cookie_remaining is not None else None,
    })

    ok = sum(1 for i in items if i["status"] == "ok")
    warn = sum(1 for i in items if i["status"] == "warn")
    err = sum(1 for i in items if i["status"] == "error")
    return {
        "items": items,
        "summary": f"{ok} OK, {warn} 警告, {err} 异常",
        "all_ok": err == 0 and warn == 0,
    }
