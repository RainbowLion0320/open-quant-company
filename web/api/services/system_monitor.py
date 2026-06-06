"""System monitor and usage payload builders for API routes."""
from __future__ import annotations

import sqlite3

import psutil

from data.storage.datahub import get_datahub
from data.llm.usage import fetch_provider_balances, summarize_llm_project_usage
from web.api.services.system_common import json_value


HUB = get_datahub()
DB = HUB.system_monitor_path()
TOKEN_CACHE = HUB.token_usage_path()


def query_metrics(sql: str, params=()):
    if not DB.exists():
        return []
    try:
        with sqlite3.connect(str(DB)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


def read_token_usage():
    default = {
        "hermes": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "sessions": 0,
            "messages": 0,
            "tool_calls": 0,
            "api_calls": 0,
            "cost_usd": 0,
        },
        "external": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
            "cost_usd": 0,
            "sources": [],
        },
        "total": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0},
        "updated_at": None,
    }
    return HUB.read_json(TOKEN_CACHE, default)


def live_system_totals() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cores_physical": psutil.cpu_count(logical=False) or psutil.cpu_count() or 0,
        "cores_logical": psutil.cpu_count() or 0,
        "memory_total_gb": round(mem.total / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "disk_used_gb": round(disk.used / 1024**3, 1),
    }


def system_monitor_payload() -> dict:
    rows = query_metrics("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")
    procs = query_metrics(
        "SELECT * FROM top_processes WHERE ts = (SELECT MAX(ts) FROM top_processes) ORDER BY rank LIMIT 10"
    )

    if not rows:
        return {"status": "no_data"}
    r = rows[0]
    token = read_token_usage()
    totals = live_system_totals()

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
        "top_processes": [
            {"pid": p["pid"], "name": p["name"], "cpu": p["cpu_pct"], "mem": p["mem_pct"]}
            for p in procs
        ],
        "token": token,
    }


def system_history_payload(hours: int) -> dict:
    rows = query_metrics(f"""
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


def llm_usage_payload(provider: str | None = None) -> dict:
    balances = fetch_provider_balances(provider)
    usage = summarize_llm_project_usage(days=30, provider=provider)
    records = [{k: json_value(v) for k, v in row.items()} for row in usage.get("daily", [])]
    balance_status_ok = any(item.get("status") == "ok" for item in balances.values())
    status = "ok" if balance_status_ok or usage.get("status") == "ok" else usage.get("status", "no_data")
    primary_balance = next(iter(balances.values()), {})
    return {
        "source": "provider_balance_api+project_usage_ledger",
        "provider": provider or "all",
        "balances": balances,
        "balance": primary_balance,
        "usage": usage,
        "data": records,
        "providers": usage.get("providers", []),
        "models": usage.get("models", []),
        "dates": usage.get("dates", []),
        "total_cost": float(usage.get("totals", {}).get("estimated_cost_cny", 0) or 0),
        "status": status,
    }


def deepseek_usage_payload() -> dict:
    """Backward-compatible alias for older API/UI callers."""
    return llm_usage_payload(provider="deepseek")
