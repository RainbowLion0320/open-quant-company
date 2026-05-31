"""External integration status payload builders for system API routes."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def api_health_payload() -> dict:
    results = []

    try:
        import akshare
        results.append({"name": "AKShare", "status": "ok", "detail": f"v{akshare.__version__}"})
    except ImportError:
        results.append({"name": "AKShare", "status": "error", "detail": "未安装"})

    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")
    if token:
        try:
            import requests as _r
            resp = _r.post(
                "http://api.tushare.pro",
                json={"api_name": "stock_basic", "token": token, "params": {"limit": 1, "list_status": "L"}, "fields": "ts_code,name"},
                timeout=5,
            )
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

    ds_key = os.environ.get("DEEPSEEK_API_KEY")
    if ds_key:
        masked = ds_key[:4] + "****" + ds_key[-4:] if len(ds_key) > 8 else "****"
        results.append({"name": "DeepSeek", "status": "ok", "detail": f"已配置 ({masked})"})
    else:
        results.append({"name": "DeepSeek", "status": "missing", "detail": "未配置 DEEPSEEK_API_KEY"})

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

    try:
        from core.settings import load_yaml_config
        cfg_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "notify.yaml"
        cfg = load_yaml_config(cfg_path, default={})
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


def cron_jobs_payload() -> dict:
    cron_path = Path.home() / ".hermes" / "cron" / "jobs.json"
    if not cron_path.exists():
        return {"jobs": [], "status": "no_data"}

    try:
        with open(cron_path) as f:
            data = json.load(f)
    except Exception as exc:
        return {"jobs": [], "status": "error", "message": f"无法读取 cron jobs: {str(exc)[:120]}"}

    compact = []
    for job in data.get("jobs", []):
        compact.append({
            "name": job.get("name", ""),
            "schedule": job.get("schedule_display", ""),
            "last_run": job.get("last_run_at") or "",
            "last_status": job.get("last_status") or "",
            "next_run": job.get("next_run_at") or "",
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


def service_status_payload() -> dict:
    import httpx

    items = []
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

    cookie_ok = False
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
                            ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
                            while True:
                                raw = ws.recv()
                                if isinstance(raw, bytes):
                                    raw = raw.decode()
                                try:
                                    msg = json.loads(raw)
                                except Exception:
                                    continue
                                if msg.get("id") == mid[0]:
                                    return msg.get("result", {})

                        _cmd("Runtime.enable")
                        r = _cmd("Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
                        url = r.get("result", {}).get("value", "")
                        is_auth = "sign_in" not in url and "login" not in url.lower()
                    finally:
                        ws.close()

                    cookie_path = Path("/tmp/chrome-cdp/Default/Cookies")
                    if cookie_path.exists():
                        cookie_mtime = cookie_path.stat().st_mtime
                        cookie_age_days = (datetime.now().timestamp() - cookie_mtime) / 86400
                        cookie_remaining = max(0, 30 - cookie_age_days)

                    if is_auth:
                        cookie_ok = True
                        cookie_detail = "已认证"
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
