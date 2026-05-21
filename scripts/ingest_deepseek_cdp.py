#!/usr/bin/env python3
"""
DeepSeek Usage Daily Ingest via CDP — dual API capture.

Key insight: /api/v0/usage/cost amounts are in CNY (元), not tokens.
/api/v0/usage/amount has raw token counts (monthly).

Computes daily tokens by distributing monthly totals proportionally
to daily cost API values, and uses cost API values directly as CNY.

Usage: python scripts/ingest_deepseek_cdp.py
"""
import json, sys, time
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import websocket


CDP = "http://localhost:9222"

def _get_json(path):
    import urllib.request
    with urllib.request.urlopen(f"{CDP}{path}") as r:
        return json.loads(r.read().decode())

def _recv_all(ws, timeout=2):
    messages = []
    ws.sock.settimeout(timeout)
    try:
        while True:
            raw = ws.recv()
            raw = raw.decode() if isinstance(raw, bytes) else raw
            try: messages.append(json.loads(raw))
            except: pass
    except (websocket.WebSocketTimeoutException, OSError):
        pass
    return messages

def ingest():
    print(f"[{datetime.now():%H:%M:%S}] CDP → DeepSeek daily (dual API)")

    pages = _get_json("/json")
    ds = next((p for p in pages if "deepseek.com" in p.get("url","").lower()), None)
    if not ds:
        _get_json("/json/new?https://platform.deepseek.com/usage")
        time.sleep(4)
        pages = _get_json("/json")
        ds = next((p for p in pages if "deepseek.com" in p.get("url","").lower()), None)
    if not ds:
        print("✗ No DeepSeek page"); sys.exit(1)

    ws = websocket.create_connection(ds["webSocketDebuggerUrl"], timeout=30)
    mid = [0]

    def cmd(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
        while True:
            try: raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
                continue
            raw = raw.decode() if isinstance(raw, bytes) else raw
            try: msg = json.loads(raw)
            except: continue
            if msg.get("id") == mid[0]:
                if "error" in msg: raise RuntimeError(f"CDP: {msg['error']}")
                return msg.get("result", {})

    ws.sock.settimeout(3)

    try:
        cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable", {"maxTotalBufferSize": 100000000})

        r = cmd("Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
        if "sign_in" in r.get("result", {}).get("value", ""):
            print("✗ Not logged in"); sys.exit(1)

        print(f"[{datetime.now():%H:%M:%S}] Navigating...")
        cmd("Page.navigate", {"url": "https://platform.deepseek.com/usage"})

        all_events = []
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            all_events.extend(_recv_all(ws, timeout=1))

        print(f"[{datetime.now():%H:%M:%S}] {len(all_events)} events, extracting...")

        def _read_body(req_id):
            hash_id = 90000 + abs(hash(req_id)) % 9999
            ws.send(json.dumps({"id": hash_id, "method": "Network.getResponseBody", "params": {"requestId": req_id}}))
            while True:
                raw = ws.recv(); raw = raw.decode() if isinstance(raw, bytes) else raw
                try: resp = json.loads(raw)
                except: continue
                if resp.get("id") == hash_id:
                    return resp.get("result", {}).get("body", "")

        amount_body = cost_body = None
        for evt in all_events:
            if evt.get("method") == "Network.responseReceived":
                url = evt.get("params", {}).get("response", {}).get("url", "")
                req_id = evt["params"]["requestId"]
                if "/api/v0/usage/amount" in url and amount_body is None:
                    amount_body = _read_body(req_id)
                    print(f"  ✓ amount: {url.split('?')[-1]}")
                if "/api/v0/usage/cost" in url and cost_body is None:
                    cost_body = _read_body(req_id)
                    print(f"  ✓ cost: {url.split('?')[-1]}")

        if not cost_body: print("✗ No cost API"); sys.exit(1)
        if not amount_body: print("✗ No amount API"); sys.exit(1)

        daily = _parse_daily(json.loads(cost_body), json.loads(amount_body))
        if daily is None or len(daily) == 0:
            print("✗ Parse failed"); sys.exit(1)

        _save(daily)

    finally:
        ws.close()


def _parse_daily(cost_raw: dict, amount_raw: dict) -> pd.DataFrame | None:
    """
    cost API:  daily per-model amounts in CNY (元)
    amount API: monthly raw token counts per model
    Result:    daily tokens (proportional to daily cost) + daily cost (CNY)
    """
    # ── Monthly raw tokens from amount API ──
    amt_items = amount_raw.get("data", {}).get("biz_data", {}).get("total", [])
    m_tokens = {}  # model -> {type: raw_tokens}
    for item in amt_items:
        tokens = {}
        for u in item.get("usage", []):
            tokens[u["type"]] = int(float(u.get("amount", 0) or 0))
        m_tokens[item["model"]] = tokens

    # ── Daily cost from cost API (amounts are CNY!) ──
    cost_biz = cost_raw.get("data", {}).get("biz_data", {})
    if isinstance(cost_biz, list): cost_biz = cost_biz[0] if cost_biz else {}
    days = cost_biz.get("days", [])

    # Compute monthly total cost per model (sum of daily costs)
    m_cost_total = {}  # model -> total CNY for month
    for day in days:
        for m in day.get("data", []):
            model = m.get("model", "")
            d_sum = sum(float(u.get("amount", 0) or 0) for u in m.get("usage", []))
            m_cost_total[model] = m_cost_total.get(model, 0) + d_sum

    rows = []
    for day in days:
        date_val = str(day.get("date", ""))[:10]
        if not date_val: continue
        for m in day.get("data", []):
            model = m.get("model", "")
            if not model: continue

            # Daily cost units (CNY amounts)
            d_cost = {}
            for u in m.get("usage", []):
                d_cost[u["type"]] = float(u.get("amount", 0) or 0)

            d_hit = d_cost.get("PROMPT_CACHE_HIT_TOKEN", 0)
            d_miss = d_cost.get("PROMPT_CACHE_MISS_TOKEN", 0)
            d_prompt = d_cost.get("PROMPT_TOKEN", 0)
            d_out = d_cost.get("RESPONSE_TOKEN", 0)
            d_req = d_cost.get("REQUEST", 0)
            d_sum = d_hit + d_miss + d_prompt + d_out

            daily_cost_cny = round(d_sum, 6)

            # Distribute monthly tokens proportionally: daily_cost / monthly_total_cost
            if model in m_tokens and model in m_cost_total:
                mt = m_tokens[model]
                mc = m_cost_total[model]
                if d_sum > 0 and mc > 0:
                    ratio = d_sum / mc
                    rows.append({
                        "utc_date": date_val,
                        "model": model,
                        "input_cache_hit": int(round(mt.get("PROMPT_CACHE_HIT_TOKEN", 0) * ratio)),
                        "input_cache_miss": int(round(mt.get("PROMPT_CACHE_MISS_TOKEN", 0) * ratio)),
                        "input_tokens": int(round((mt.get("PROMPT_CACHE_MISS_TOKEN", 0) + mt.get("PROMPT_TOKEN", 0)) * ratio)),
                        "output_tokens": int(round(mt.get("RESPONSE_TOKEN", 0) * ratio)),
                        "total_tokens": int(round((mt.get("PROMPT_CACHE_HIT_TOKEN", 0) + mt.get("PROMPT_CACHE_MISS_TOKEN", 0) + mt.get("PROMPT_TOKEN", 0) + mt.get("RESPONSE_TOKEN", 0)) * ratio)),
                        "requests": int(round(mt.get("REQUEST", 0) * ratio)),
                        "cost_cny": daily_cost_cny,
                    })
                else:
                    rows.append({
                        "utc_date": date_val, "model": model,
                        "input_cache_hit": 0, "input_cache_miss": 0,
                        "input_tokens": 0, "output_tokens": 0,
                        "total_tokens": 0, "requests": 0,
                        "cost_cny": daily_cost_cny,
                    })

    if not rows:
        print("  No rows"); return None

    df = pd.DataFrame(rows)
    # Drop zero-all-tokens AND zero-cost days (future dates)
    df = df[(df["total_tokens"] > 0) | (df["cost_cny"] > 0.001)]
    df = df.sort_values(["utc_date", "model"])
    print(f"  Parsed: {len(df)} rows, {df['utc_date'].nunique()} days, {df['model'].nunique()} models")
    print(f"  Total tokens: {df['total_tokens'].sum():,}")
    print(f"  Total cost: ¥{df['cost_cny'].sum():.2f}")
    return df


def _save(df: pd.DataFrame):
    from data.datahub import get_datahub
    hub = get_datahub()
    pq = hub.deepseek_usage_path()
    pq.parent.mkdir(parents=True, exist_ok=True)

    existing = hub.read_parquet(pq, default=pd.DataFrame())
    if not existing.empty:
        keep = existing[~existing["utc_date"].isin(df["utc_date"].unique())]
        merged = pd.concat([keep, df], ignore_index=True)
        merged = merged.sort_values(["utc_date", "model"])
    else:
        merged = df

    hub.write_parquet(merged, pq)
    print(f"  ✓ Saved: {len(merged)} rows ({len(df)} new)")
    for _, r in merged.tail(8).iterrows():
        print(f"    {r['utc_date']}  {r['model']:22s}  ¥{r.get('cost_cny',0):.2f}")


if __name__ == "__main__":
    ingest()
