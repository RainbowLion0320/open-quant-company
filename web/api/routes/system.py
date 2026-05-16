"""系统活动监视器 — SQLite 时序库 + 历史趋势"""
from fastapi import APIRouter, Query
import sqlite3, json, os
from datetime import datetime

router = APIRouter(prefix="/api/system", tags=["System"])

DB = "/Users/fushao/quant-agent/data/store/system_monitor.db"
TOKEN_CACHE = "/Users/fushao/quant-agent/data/cache/token_usage.json"


def _query(sql: str, params=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _read_token():
    try:
        if os.path.exists(TOKEN_CACHE):
            with open(TOKEN_CACHE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"hermes": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                       "sessions": 0, "messages": 0, "tool_calls": 0, "api_calls": 0, "cost_usd": 0},
            "external": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "calls": 0, "cost_usd": 0, "sources": []},
            "total": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0},
            "updated_at": None}


@router.get("/monitor")
async def system_monitor():
    """当前快照 (读最新一行 SQLite)"""
    rows = _query("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")
    procs = _query("SELECT * FROM top_processes WHERE ts = (SELECT MAX(ts) FROM top_processes) ORDER BY rank LIMIT 10")

    if not rows:
        return {"status": "no_data"}
    r = rows[0]
    token = _read_token()

    return {
        "timestamp": r["ts"],
        "cpu": {
            "percent": r["cpu_pct"],
            "cores_physical": 10,
            "cores_logical": 10,
            "load_avg": [r["load_1m"], r["load_5m"], r["load_15m"]],
        },
        "memory": {
            "total_gb": 16.0,
            "used_gb": r["mem_used_gb"],
            "percent": r["mem_pct"],
        },
        "disk": {
            "total_gb": 460.4,
            "used_gb": 11.7,
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
