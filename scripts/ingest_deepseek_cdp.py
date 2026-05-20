#!/usr/bin/env python3
"""DeepSeek Usage Auto-Ingest via CDP — synchronous version."""
import json, sys, time, threading
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

def _cdp(ws, method, params=None):
    """Send CDP command, collect events into global list, return result."""
    mid = getattr(_cdp, "_id", 0) + 1; _cdp._id = mid
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    # Read until we get our response, collecting events
    _raw_events = []
    while True:
        try:
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        if isinstance(raw, bytes): raw = raw.decode()
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == mid:
            with _evt_lock:
                _events.extend(_raw_events)
            if "error" in msg:
                raise RuntimeError(f"CDP error: {msg['error']}")
            return msg.get("result", {})
        else:
            _raw_events.append(msg)

_events = []
_evt_lock = threading.Lock()

def ingest():
    print(f"[{datetime.now():%H:%M:%S}] CDP → DeepSeek usage")
    pages = _get_json("/json")
    page = next((p for p in pages if "deepseek.com" in p.get("url", "")), None)
    if not page:
        print("✗ No DeepSeek page"); sys.exit(1)

    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
    ws.sock.settimeout(3)

    try:
        _cdp(ws, "Runtime.enable")
        _cdp(ws, "Page.enable")

        # Check if logged in
        r = _cdp(ws, "Runtime.evaluate", {
            "expression": "document.title + ' | ' + (document.querySelector('[class*=balance]')?.textContent || 'no balance')",
            "returnByValue": True,
        })
        print(f"  {r['result']['value']}")

        # Enable Network with large buffer
        _cdp(ws, "Network.enable", {"maxTotalBufferSize": 50000000, "maxResourceBufferSize": 25000000})
        with _evt_lock: _events.clear()

        # Navigate to usage
        _cdp(ws, "Page.navigate", {"url": "https://platform.deepseek.com/usage"})
        time.sleep(2)

        # Wait for complete
        for _ in range(10):
            r = _cdp(ws, "Runtime.evaluate", {"expression": "document.readyState", "returnByValue": True})
            if r.get("result", {}).get("value") == "complete":
                break
            time.sleep(1)
        time.sleep(2)

        # Click current month to trigger API
        _cdp(ws, "Runtime.evaluate", {
            "expression": "(()=>{ for(let el of document.querySelectorAll('div,span,button')){ if(el.textContent.trim().match(/2026.*5月?$/)){ el.click(); break; } } })()",
            "returnByValue": True,
        })
        time.sleep(4)

        # Collect network events
        with _evt_lock:
            evts = list(_events)

        # Find usage API calls and read bodies
        api_bodies = []
        for evt in evts:
            if evt.get("method") == "Network.responseReceived":
                params = evt.get("params", {})
                url = params.get("response", {}).get("url", "")
                req_id = params.get("requestId", "")
                if "/api/v0/usage/" in url and "amount" in url:
                    try:
                        body = _cdp(ws, "Network.getResponseBody", {"requestId": req_id})
                        api_bodies.append({"url": url, "body": body.get("body", "")})
                        print(f"  ✓ {url.split('?')[-1]}")
                    except Exception as e:
                        print(f"  ✗ body read failed: {e}")

        if not api_bodies:
            # Fallback: page might have loaded data without click
            r = _cdp(ws, "Runtime.evaluate", {
                "expression": """
                (async () => {
                    try {
                        const r = await (await fetch('/api/v0/usage/amount?month=5&year=2026', {credentials: 'include'})).text();
                        return r.substring(0, 5000);
                    } catch(e) { return 'ERR:'+e.message; }
                })()
                """,
                "returnByValue": True,
                "awaitPromise": True,
            })
            body = r.get("result", {}).get("value", "")
            if body and not body.startswith("ERR:"):
                api_bodies.append({"url": "fetch(month=5)", "body": body})

        if not api_bodies:
            print("✗ No usage API data captured"); sys.exit(1)

        # Parse and save
        dfs = []
        for r in api_bodies:
            try:
                data = json.loads(r["body"])
                df = _parse_monthly(data)
                if df is not None: dfs.append(df)
            except Exception as e:
                print(f"  Parse error: {e}")

        if not dfs:
            print("✗ Parse failed"); sys.exit(1)

        df = pd.concat(dfs, ignore_index=True)
        df = df.drop_duplicates(subset=["utc_date", "model"], keep="last")
        _save(df)

    finally:
        ws.close()


def _parse_monthly(data):
    """Parse monthly usage API response into DataFrame."""
    inner = data.get("data", data)
    biz = inner.get("biz_data", inner)
    total = biz.get("total", [])
    if not total:
        print(f"  Unknown format: {json.dumps(data)[:200]}")
        return None

    rows = []
    for item in total:
        model = item.get("model", "")
        usage = {u["type"]: int(float(u.get("amount", 0) or 0)) for u in item.get("usage", [])}
        # Extract month from API URL or item metadata
        month_str = str(item.get("month", "")).zfill(2) or "05"
        rows.append({
            "utc_date": f"2026-{month_str}-15",
            "model": model,
            "input_cache_hit": usage.get("PROMPT_CACHE_HIT_TOKEN", 0),
            "input_cache_miss": usage.get("PROMPT_CACHE_MISS_TOKEN", 0),
            "input_tokens": usage.get("PROMPT_CACHE_MISS_TOKEN", 0) + usage.get("PROMPT_TOKEN", 0),
            "output_tokens": usage.get("RESPONSE_TOKEN", 0),
            "total_tokens": sum(v for k, v in usage.items() if "TOKEN" in k),
            "requests": usage.get("API_REQUEST_COUNT", 0),
            "cost_cny": float(item.get("cost", 0) or 0),
        })

    df = pd.DataFrame(rows)
    print(f"  Parsed: {len(df)} models")
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
    print(f"  ✓ Saved: {len(merged)} rows")
    for _, r in merged.tail(4).iterrows():
        print(f"    {r['utc_date']}  {r['model']:20s}  ¥{r.get('cost_cny',0):.2f}")


if __name__ == "__main__":
    ingest()
