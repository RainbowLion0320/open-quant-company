#!/usr/bin/env python3
"""更新 Token 缓存 → 合并 Hermes state.db + factor_hypothesis log + Hindsight"""
import sqlite3, json, os
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.datahub import get_datahub

DB = os.path.expanduser("~/.hermes/state.db")
HUB = get_datahub()
OUT = HUB.token_usage_path()
LLM_LOG = HUB.llm_usage_path()


def read_hermes_usage():
    """从 Hermes state.db 读取今日会话统计"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    row = conn.execute("""
        SELECT COUNT(*) as sessions,
               COALESCE(SUM(message_count), 0) as messages,
               COALESCE(SUM(tool_call_count), 0) as tools,
               COALESCE(SUM(api_call_count), 0) as api_calls,
               COALESCE(SUM(input_tokens), 0) as input_tokens,
               COALESCE(SUM(output_tokens), 0) as output_tokens,
               COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
               COALESCE(SUM(estimated_cost_usd), 0) as cost_usd
        FROM sessions WHERE started_at >= ?
    """, (today_start,)).fetchone()
    conn.close()
    return dict(row)


def read_external_usage():
    """读取 factor_hypothesis / Hindsight 等外部 LLM 调用日志"""
    try:
        if LLM_LOG.exists():
            with open(LLM_LOG) as f:
                data = json.load(f)
            if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                return data
    except Exception:
        pass
    return {"total_input": 0, "total_output": 0, "total_cost": 0.0, "calls": 0, "items": []}


def update():
    h = read_hermes_usage()
    ext = read_external_usage()

    # 合并 Hindsight token
    hindsight_file = HUB.hindsight_tokens_path()
    hs = {"total_input": 0, "total_output": 0, "total_cost": 0.0, "calls": 0}
    try:
        if hindsight_file.exists():
            with open(hindsight_file) as f:
                d = json.load(f)
            hs["total_input"] = d["input_tokens"]
            hs["total_output"] = d["output_tokens"]
            hs["total_cost"] = d["cost_usd"]
            hs["calls"] = d["calls"]
    except Exception:
        pass

    ext["total_input"] += hs["total_input"]
    ext["total_output"] += hs["total_output"]
    ext["total_cost"] += hs["total_cost"]
    ext["calls"] += hs["calls"]
    ext_sources = list(set(item["source"] for item in ext.get("items", [])))
    if hs["calls"] > 0:
        ext_sources.append("hindsight")

    data = {
        "hermes": {
            "input_tokens": h["input_tokens"],
            "output_tokens": h["output_tokens"],
            "total_tokens": h["total_tokens"],
            "sessions": h["sessions"],
            "messages": h["messages"],
            "tool_calls": h["tools"],
            "api_calls": h["api_calls"],
            "cost_usd": round(h["cost_usd"], 4),
        },
        "external": {
            "input_tokens": ext["total_input"],
            "output_tokens": ext["total_output"],
            "total_tokens": ext["total_input"] + ext["total_output"],
            "calls": ext["calls"],
            "cost_usd": round(ext["total_cost"], 4),
            "sources": ext_sources,
        },
        "total": {
            "input_tokens": h["input_tokens"] + ext["total_input"],
            "output_tokens": h["output_tokens"] + ext["total_output"],
            "total_tokens": h["total_tokens"] + ext["total_input"] + ext["total_output"],
            "cost_usd": round(h["cost_usd"] + ext["total_cost"], 4),
        },
        "updated_at": datetime.now().isoformat(),
    }

    HUB.write_json(data, OUT)

    t = data["total"]
    print(f"Token updated: Hermes {h['input_tokens']:,} in + ext {ext['total_input']:,} in "
          f"= total ${t['cost_usd']:.4f} ({h['sessions']} sessions, {ext['calls']} external calls)")


if __name__ == "__main__":
    update()
