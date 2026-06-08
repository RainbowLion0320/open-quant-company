"""External integration status payload builders for system API routes."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.env_secrets import read_env_secret


def api_health_payload() -> dict:
    results = []

    try:
        import akshare
        results.append({"name": "AKShare", "status": "ok", "detail": f"v{akshare.__version__}"})
    except ImportError:
        results.append({"name": "AKShare", "status": "error", "detail": "未安装"})

    token = read_env_secret("TUSHARE_TOKEN")
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

    try:
        from data.llm.usage import provider_health_items
        results.extend(provider_health_items())
    except Exception as exc:
        results.append({"name": "LLM", "status": "warn", "detail": f"无法读取 provider 配置: {str(exc)[:60]}"})

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
