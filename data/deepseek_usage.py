"""DeepSeek official balance API and project-local usage ledger."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from core.settings import get_settings
from data.datahub import get_datahub


BALANCE_URL = "https://api.deepseek.com/user/balance"
PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"

# Fallback defaults — overridden by config/settings.yaml → deepseek.pricing
_DEFAULT_USD_CNY = 7.2
_DEFAULT_MODELS: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {"cache_hit": 0.0028, "cache_miss": 0.14, "output": 0.28},
    "deepseek-v4-pro": {"cache_hit": 0.003625, "cache_miss": 0.435, "output": 0.87},
}
_DEFAULT_ALIASES: dict[str, str] = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-flash",
}


def _pricing_config() -> dict:
    """Load pricing from settings.yaml, falling back to hardcoded defaults."""
    cfg = get_settings().get("deepseek", {}).get("pricing", {})
    return cfg if isinstance(cfg, dict) else {}


def _models() -> dict[str, dict[str, float]]:
    cfg = _pricing_config().get("models")
    if isinstance(cfg, dict) and cfg:
        return cfg
    return _DEFAULT_MODELS


def _aliases() -> dict[str, str]:
    cfg = _pricing_config().get("aliases")
    if isinstance(cfg, dict) and cfg:
        return cfg
    return _DEFAULT_ALIASES


def load_deepseek_api_key() -> str:
    """Load DeepSeek API key from environment, falling back to ~/.hermes/.env."""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def fetch_deepseek_balance(api_key: str | None = None, *, timeout: float = 5.0) -> dict[str, Any]:
    """Fetch current account balance through DeepSeek's official API key endpoint."""
    key = (api_key or load_deepseek_api_key()).strip()
    if not key:
        return {"status": "missing", "is_available": False, "balance_infos": [], "message": "DEEPSEEK_API_KEY not configured"}

    request = urllib.request.Request(BALANCE_URL, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"status": "error", "is_available": False, "balance_infos": [], "http_status": exc.code, "message": exc.reason}
    except Exception as exc:
        return {"status": "error", "is_available": False, "balance_infos": [], "message": type(exc).__name__}

    infos = payload.get("balance_infos") if isinstance(payload, dict) else []
    return {
        "status": "ok",
        "is_available": bool(payload.get("is_available")) if isinstance(payload, dict) else False,
        "balance_infos": infos if isinstance(infos, list) else [],
    }


def _usage_value(usage: Any, key: str, default: int = 0) -> int:
    if usage is None:
        return default
    if isinstance(usage, dict):
        value = usage.get(key, default)
    else:
        value = getattr(usage, key, default)
        if value is default and hasattr(usage, "model_dump"):
            try:
                value = usage.model_dump().get(key, default)
            except Exception:
                value = default
    try:
        return int(value or 0)
    except Exception:
        return default


def _pricing_model(model: str) -> str:
    aliases = _aliases()
    models = _models()
    canonical = aliases.get(str(model), str(model))
    return canonical if canonical in models else "deepseek-v4-flash"


def _fx_rate() -> float:
    cfg_rate = _pricing_config().get("usd_cny")
    if cfg_rate is not None:
        try:
            return float(cfg_rate)
        except Exception:
            pass
    try:
        return float(os.environ.get("DEEPSEEK_USD_CNY", _DEFAULT_USD_CNY))
    except Exception:
        return _DEFAULT_USD_CNY


def normalize_deepseek_usage(
    model: str,
    usage: Any,
    *,
    source: str = "unknown",
    request_id: str = "",
    created_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Normalize one official response usage object into a ledger row."""
    if isinstance(created_at, datetime):
        ts = created_at.astimezone(timezone.utc)
    elif created_at:
        ts = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).astimezone(timezone.utc)
    else:
        ts = datetime.now(timezone.utc)

    prompt_tokens = _usage_value(usage, "prompt_tokens")
    hit = _usage_value(usage, "prompt_cache_hit_tokens")
    miss = _usage_value(usage, "prompt_cache_miss_tokens")
    if prompt_tokens and hit + miss == 0:
        miss = prompt_tokens
    output = _usage_value(usage, "completion_tokens")
    total = _usage_value(usage, "total_tokens", hit + miss + output) or (hit + miss + output)

    pricing_model = _pricing_model(model)
    pricing = _models()[pricing_model]
    cost_usd = (
        hit * pricing["cache_hit"]
        + miss * pricing["cache_miss"]
        + output * pricing["output"]
    ) / 1_000_000

    return {
        "ts": ts.isoformat(),
        "utc_date": ts.date().isoformat(),
        "model": str(model),
        "pricing_model": pricing_model,
        "source": source,
        "request_id": request_id,
        "usage_source": "api_response",
        "input_cache_hit": hit,
        "input_cache_miss": miss,
        "input_tokens": hit + miss,
        "output_tokens": output,
        "total_tokens": total,
        "requests": 1,
        "estimated_cost_usd": round(cost_usd, 9),
        "estimated_cost_cny": round(cost_usd * _fx_rate(), 9),
        "pricing_source": PRICING_SOURCE,
    }


def append_deepseek_usage(
    model: str,
    usage: Any,
    *,
    source: str = "unknown",
    request_id: str = "",
    created_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Append one DeepSeek API response usage record to the project ledger."""
    row = normalize_deepseek_usage(model, usage, source=source, request_id=request_id, created_at=created_at)
    hub = get_datahub()
    path = hub.deepseek_project_usage_path()
    existing = hub.read_parquet(path, default=pd.DataFrame())
    frame = pd.DataFrame([row])
    if existing is not None and not existing.empty:
        frame = pd.concat([existing, frame], ignore_index=True)
    frame = frame.sort_values(["utc_date", "ts", "model"]).reset_index(drop=True)
    hub.write_parquet(frame, path)
    return row


def record_deepseek_response_usage(response: Any, *, model: str, source: str, request_id: str = "") -> dict[str, Any] | None:
    """Record usage from an OpenAI-compatible DeepSeek response object."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    return append_deepseek_usage(model, usage, source=source, request_id=request_id)


def summarize_deepseek_project_usage(days: int = 30) -> dict[str, Any]:
    """Return daily project usage aggregated from the local response ledger."""
    hub = get_datahub()
    path = hub.deepseek_project_usage_path()
    if not path.exists():
        return _empty_usage_summary("no_data")

    df = hub.read_parquet(path, default=pd.DataFrame())
    if df is None or df.empty:
        return _empty_usage_summary("no_data")

    required = {"utc_date", "model"}
    if not required.issubset(df.columns):
        return _empty_usage_summary("invalid")

    numeric = [
        "input_cache_hit",
        "input_cache_miss",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "requests",
        "estimated_cost_usd",
        "estimated_cost_cny",
    ]
    for col in numeric:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["utc_date"] = df["utc_date"].astype(str).str.slice(0, 10)
    df["model"] = df["model"].astype(str)

    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=max(1, int(days)) - 1)).isoformat()
    df = df[df["utc_date"] >= cutoff]
    if df.empty:
        return _empty_usage_summary("no_data")

    daily = (
        df.groupby(["utc_date", "model"], as_index=False)[numeric]
        .sum()
        .sort_values(["utc_date", "model"])
    )
    daily["usage_source"] = "api_response"
    daily["cost_cny"] = daily["estimated_cost_cny"]
    records = daily.to_dict(orient="records")

    return {
        "status": "ok",
        "days": days,
        "daily": records,
        "models": daily["model"].unique().tolist(),
        "dates": sorted(daily["utc_date"].unique().tolist()),
        "totals": {
            "tokens": int(daily["total_tokens"].sum()),
            "requests": int(daily["requests"].sum()),
            "estimated_cost_usd": round(float(daily["estimated_cost_usd"].sum()), 6),
            "estimated_cost_cny": round(float(daily["estimated_cost_cny"].sum()), 4),
        },
        "pricing_source": PRICING_SOURCE,
    }


def _empty_usage_summary(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "days": 30,
        "daily": [],
        "models": [],
        "dates": [],
        "totals": {"tokens": 0, "requests": 0, "estimated_cost_usd": 0.0, "estimated_cost_cny": 0.0},
        "pricing_source": PRICING_SOURCE,
    }
