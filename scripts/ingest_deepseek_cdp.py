#!/usr/bin/env python3
"""
DeepSeek Usage Daily Ingest via CDP — cost API interception.

Navigates to DeepSeek usage page, intercepts /api/v0/usage/cost
response (DAILY per-model token breakdown), parses, saves to parquet.

Usage: python scripts/ingest_deepseek_cdp.py
"""
import json, sys, time
from pathlib import Path
from datetime import datetime
import pandas as pd
import websocket

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CDP = "http://localhost:9222"

def _get_json(path):
    import urllib.request
    with urllib.request.urlopen(f"{CDP}{path}") as r:
        return json.loads(r.read().decode())

def _recv_all(ws, timeout=2):
    """Read all available messages from websocket."""
    messages = []
    ws.sock.settimeout(timeout)
    try:
        while True:
            raw = ws.recv()
            raw = raw.decode() if isinstance(raw, bytes) else raw
            try: messages.append(json.loads(raw))
            except: pass
    except websocket.WebSocketTimeoutException:
        pass
    except Exception:
        pass
    return messages

def ingest():
    print(f"[{datetime.now():%H:%M:%S}] CDP -> daily cost API")

    # Connect
    pages = _get_json("/json")
    ds = next((p for p in pages if "deepseek.com" in p.get("url", "").lower()), None)
    if not ds:
        _get_json("/json/new?https://platform.deepseek.com/usage")
        time.sleep(4)
        pages = _get_json("/json")
        ds = next((p for p in pages if "deepseek.com" in p.get("url", "").lower()), None)
    if not ds:
        print("✗ No DeepSeek page"); sys.exit(1)

    ws = websocket.create_connection(ds["webSocketDebuggerUrl"], timeout=30)
    mid = [0]

    def cmd(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
        # Read until we get our response, collect all events
        all_msgs = []
        while True:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                # Resend and continue
                ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
                continue
            raw = raw.decode() if isinstance(raw, bytes) else raw
            try: msg = json.loads(raw)
            except: continue
            if msg.get("id") == mid[0]:
                if "error" in msg: raise RuntimeError(f"CDP: {msg['error']}")
                return msg.get("result", {}), all_msgs
            all_msgs.append(msg)

    ws.sock.settimeout(3)

    try:
        _, _ = cmd("Runtime.enable")
        _, _ = cmd("Page.enable")
        _, _ = cmd("Network.enable", {"maxTotalBufferSize": 100000000})

        # Check auth
        r, _ = cmd("Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
        if "sign_in" in r.get("result", {}).get("value", ""):
            print("✗ Not logged in"); sys.exit(1)

        # Clear network buffer then navigate to trigger fresh API calls
        print(f"[{datetime.now():%H:%M:%S}] Navigating to usage page...")
        _, _ = cmd("Page.navigate", {"url": "https://platform.deepseek.com/usage"})

        # Read ALL events for the next few seconds in a loop
        all_events = []
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            msgs = _recv_all(ws, timeout=1)
            all_events.extend(msgs)

        # Find /api/v0/usage/cost responses
        print(f"[{datetime.now():%H:%M:%S}] Searching {len(all_events)} events...")
        cost_bodies = []
        for evt in all_events:
            if evt.get("method") == "Network.responseReceived":
                params = evt.get("params", {})
                url = params.get("response", {}).get("url", "")
                if "/api/v0/usage/cost" in url:
                    req_id = params["requestId"]
                    try:
                        # Need to send a command to get body - use fresh ws state
                        ws.send(json.dumps({"id": 9999, "method": "Network.getResponseBody", "params": {"requestId": req_id}}))
                        while True:
                            raw = ws.recv()
                            raw = raw.decode() if isinstance(raw, bytes) else raw
                            try: resp = json.loads(raw)
                            except: continue
                            if resp.get("id") == 9999:
                                cost_bodies.append(resp.get("result", {}).get("body", ""))
                                print(f"  ✓ captured: {url.split('?')[-1]}")
                                break
                    except Exception as e:
                        print(f"  body read error: {e}")

        if not cost_bodies:
            print("✗ No cost API response found in events")
            # Try other months too - the page might load multiple
            for month in [4, 3]:
                _, evt_msgs = cmd("Page.navigate", {"url": f"https://platform.deepseek.com/usage?month={month}&year=2026"})
                time.sleep(3)
                msgs = _recv_all(ws, timeout=2)
                all_events = evt_msgs + msgs
                for evt in all_events:
                    if evt.get("method") == "Network.responseReceived":
                        params = evt.get("params", {})
                        url = params.get("response", {}).get("url", "")
                        if "/api/v0/usage/cost" in url:
                            req_id = params["requestId"]
                            try:
                                ws.send(json.dumps({"id": 9998, "method": "Network.getResponseBody", "params": {"requestId": req_id}}))
                                while True:
                                    raw = ws.recv()
                                    raw = raw.decode() if isinstance(raw, bytes) else raw
                                    try: resp = json.loads(raw)
                                    except: continue
                                    if resp.get("id") == 9998:
                                        body = resp.get("result", {}).get("body", "")
                                        if body:
                                            cost_bodies.append(body)
                                            print(f"  ✓ month={month}: {url.split('?')[-1]}")
                                        break
                            except: pass
            if not cost_bodies:
                print("✗ Still no data"); sys.exit(1)

        # Parse
        dfs = []
        for body in cost_bodies:
            data = json.loads(body)
            df = _parse(data)
            if df is not None and len(df) > 0:
                dfs.append(df)

        if not dfs:
            print("✗ Parse failed"); sys.exit(1)

        all_df = pd.concat(dfs, ignore_index=True)
        all_df = all_df.drop_duplicates(subset=["utc_date", "model"], keep="last")
        _save(all_df)

    finally:
        ws.close()


def _parse(data):
    """Parse /api/v0/usage/cost response — daily per-model data.
    Structure: biz_data[{total: [...], days: [{date, data: [{model, usage}]}]}]
    Amounts are DeepSeek cost units (token count / internal factor).
    """
    inner = data.get("data", data)
    biz = inner.get("biz_data", inner)
    if isinstance(biz, list):
        biz = biz[0] if biz else {}

    rows = []
    for day in biz.get("days", []):
        date_val = str(day.get("date", ""))[:10]
        if not date_val: continue
        for m in day.get("data", []):
            model = m.get("model", "")
            usage = {}
            for u in m.get("usage", []):
                usage[u.get("type", "")] = int(float(u.get("amount", 0) or 0) * 1e7)  # scale to raw tokens

            rows.append({
                "utc_date": date_val,
                "model": model,
                "input_cache_hit": usage.get("PROMPT_CACHE_HIT_TOKEN", 0),
                "input_cache_miss": usage.get("PROMPT_CACHE_MISS_TOKEN", 0),
                "input_tokens": usage.get("PROMPT_CACHE_MISS_TOKEN", 0) + usage.get("PROMPT_TOKEN", 0),
                "output_tokens": usage.get("RESPONSE_TOKEN", 0),
                "total_tokens": sum(usage.values()),
                "requests": usage.get("REQUEST", 0),
                "cost_cny": 0.0,
            })

    if not rows:
        # Try biz_data as list of items directly
        items = biz if isinstance(biz, list) else biz.get("total", [])
        if items:
            # Fallback to monthly data
            for item in items:
                if isinstance(item, dict) and "days" in item:
                    for day in item.get("days", []):
                        date_val = str(day.get("date", ""))[:10]
                        for m in day.get("data", []):
                            usage = {u["type"]: int(float(u.get("amount",0) or 0) * 1e7) for u in m.get("usage", [])}
                            rows.append({"utc_date": date_val, "model": m["model"], **usage, "cost_cny": 0.0})
        
    if not rows:
        print(f"  Unknown format: {json.dumps(data)[:500]}")
        return None

    df = pd.DataFrame(rows)
    if "cost_cny" in df.columns:
        # Convert cost from API amounts to CNY (the amount field is usually in 0.0001 units)
        pass  # keep as-is for now, cost not in this API
    print(f"  Parsed: {len(df)} rows, {df['utc_date'].nunique()} days, {df['model'].nunique()} models")
    return df


def _save(df):
    from data.datahub import get_datahub
    hub = get_datahub()
    pq = hub.deepseek_usage_path()
    pq.parent.mkdir(parents=True, exist_ok=True)

    existing = hub.read_parquet(pq, default=pd.DataFrame())
    if not existing.empty:
        merged = pd.concat([existing, df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["utc_date", "model"], keep="last")
        merged = merged.sort_values(["utc_date", "model"])
    else:
        merged = df

    hub.write_parquet(merged, pq)
    print(f"  ✓ Saved: {len(merged)} rows ({len(df)} new)")
    for _, r in merged.tail(8).iterrows():
        print(f"    {r['utc_date']}  {r['model']:22s}  ¥{r.get('cost_cny',0):.2f}")


if __name__ == "__main__":
    ingest()
