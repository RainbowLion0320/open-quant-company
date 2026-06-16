"""Generic LLM provider balance, pricing, and project-local usage ledger."""

from __future__ import annotations

import copy
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from core.env_secrets import read_env_secret
from core.settings import get_settings
from data.storage.datahub import get_datahub


DEFAULT_PROVIDER = "deepseek"
DEFAULT_USAGE_SCHEMA = "openai_cache"
DEFAULT_LEDGER_SOURCE = "provider_balance_api+project_usage_ledger"
DEFAULT_LLM_PROTOCOL = "openai_compatible"
DEFAULT_CHAT_PATH = "/chat/completions"
SUPPORTED_LLM_PROTOCOLS = {DEFAULT_LLM_PROTOCOL}

DEFAULT_LLM_CONFIG: dict[str, Any] = {
    "default_provider": DEFAULT_PROVIDER,
    "use_cases": {
        "factor_hypothesis": {"provider": DEFAULT_PROVIDER, "model": "deepseek-v4-pro"},
        "agent_planning": {"provider": DEFAULT_PROVIDER, "model": "deepseek-v4-pro"},
    },
    "providers": {
        "deepseek": {
            "enabled": True,
            "label": "DeepSeek",
            "protocol": DEFAULT_LLM_PROTOCOL,
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-v4-flash",
            "request": {
                "chat_path": DEFAULT_CHAT_PATH,
                "response_format_json": True,
                "temperature": 0.1,
                "timeout_seconds": 20.0,
            },
            "balance_url": "https://api.deepseek.com/user/balance",
            "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing",
            "usage_schema": DEFAULT_USAGE_SCHEMA,
            "pricing": {
                "usd_cny": 7.2,
                "models": {
                    "deepseek-v4-flash": {"input_cache_hit": 0.0028, "input_cache_miss": 0.14, "output": 0.28},
                    "deepseek-v4-pro": {"input_cache_hit": 0.003625, "input_cache_miss": 0.435, "output": 0.87},
                },
                "aliases": {
                    "deepseek-chat": "deepseek-v4-flash",
                    "deepseek-reasoner": "deepseek-v4-flash",
                },
            },
        }
    }
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def llm_config() -> dict[str, Any]:
    """Load generic LLM provider config."""
    settings = get_settings()
    cfg = settings.get("llm", {}) if isinstance(settings.get("llm"), dict) else {}
    return _deep_merge(DEFAULT_LLM_CONFIG, cfg)


def enabled_providers() -> list[str]:
    providers = llm_config().get("providers", {})
    return [name for name, cfg in providers.items() if isinstance(cfg, dict) and cfg.get("enabled", True)]


def default_provider() -> str:
    cfg = llm_config()
    provider = str(cfg.get("default_provider") or DEFAULT_PROVIDER)
    return provider


def provider_config(provider: str = DEFAULT_PROVIDER) -> dict[str, Any]:
    providers = llm_config().get("providers", {})
    cfg = providers.get(provider) if isinstance(providers, dict) else None
    if isinstance(cfg, dict):
        return cfg
    return {}


def _provider_request_config(provider_cfg: dict[str, Any]) -> dict[str, Any]:
    request = provider_cfg.get("request", {})
    request = request if isinstance(request, dict) else {}
    try:
        temperature = float(request.get("temperature", 0.1))
    except (TypeError, ValueError):
        temperature = 0.1
    try:
        timeout_seconds = float(request.get("timeout_seconds", 20.0))
    except (TypeError, ValueError):
        timeout_seconds = 20.0
    return {
        "chat_path": str(request.get("chat_path") or DEFAULT_CHAT_PATH),
        "response_format_json": bool(request.get("response_format_json", True)),
        "temperature": temperature,
        "timeout_seconds": timeout_seconds,
    }


def _blocked_runtime(use_case: str, provider: str, model: str, reason: str) -> dict[str, Any]:
    return {
        "use_case": use_case,
        "provider": provider,
        "label": provider,
        "model": model,
        "base_url": "",
        "credential_env": "",
        "usage_schema": DEFAULT_USAGE_SCHEMA,
        "configured": False,
        "enabled": False,
        "protocol": "",
        "chat_path": DEFAULT_CHAT_PATH,
        "response_format_json": True,
        "temperature": 0.1,
        "timeout_seconds": 20.0,
        "block_reason": reason,
    }


def resolve_llm_use_case(use_case: str, *, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Resolve provider runtime settings for an LLM use case without hard-coding one vendor."""
    cfg = llm_config()
    use_cases = cfg.get("use_cases", {})
    use_case_cfg = use_cases.get(use_case, {}) if isinstance(use_cases, dict) else {}
    providers = cfg.get("providers", {})
    candidate_provider = str(provider or use_case_cfg.get("provider") or default_provider())
    candidate_model = str(model or use_case_cfg.get("model") or "")
    if not isinstance(providers, dict) or candidate_provider not in providers or not isinstance(providers.get(candidate_provider), dict):
        return _blocked_runtime(use_case, candidate_provider, candidate_model, "provider_not_configured")
    resolved_provider = candidate_provider
    pcfg = provider_config(resolved_provider)
    request_cfg = _provider_request_config(pcfg)
    protocol = str(pcfg.get("protocol") or DEFAULT_LLM_PROTOCOL)
    enabled = bool(pcfg.get("enabled", True))
    resolved_model = str(model or use_case_cfg.get("model") or pcfg.get("default_model") or "")
    block_reason = ""
    if not enabled:
        block_reason = "provider_disabled"
    elif protocol not in SUPPORTED_LLM_PROTOCOLS:
        block_reason = "unsupported_protocol"
    elif not str(pcfg.get("base_url") or pcfg.get("chat_base_url") or "").strip():
        block_reason = "base_url_missing"
    elif not resolved_model:
        block_reason = "model_missing"
    return {
        "use_case": use_case,
        "provider": resolved_provider,
        "label": str(pcfg.get("label") or resolved_provider),
        "model": resolved_model,
        "base_url": str(pcfg.get("base_url") or pcfg.get("chat_base_url") or ""),
        "credential_env": _env_name(resolved_provider),
        "usage_schema": str(pcfg.get("usage_schema") or DEFAULT_USAGE_SCHEMA),
        "configured": True,
        "enabled": enabled,
        "protocol": protocol,
        "chat_path": request_cfg["chat_path"],
        "response_format_json": request_cfg["response_format_json"],
        "temperature": request_cfg["temperature"],
        "timeout_seconds": request_cfg["timeout_seconds"],
        "block_reason": block_reason,
    }


def _normalize_pricing_config(pricing: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(pricing or {})
    models = out.get("models", {})
    if isinstance(models, dict):
        normalized: dict[str, dict[str, float]] = {}
        for model, raw in models.items():
            if not isinstance(raw, dict):
                continue
            normalized[model] = {
                "input_cache_hit": float(raw.get("input_cache_hit", raw.get("cache_hit", 0)) or 0),
                "input_cache_miss": float(raw.get("input_cache_miss", raw.get("cache_miss", raw.get("input", 0))) or 0),
                "input": float(raw.get("input", raw.get("input_cache_miss", raw.get("cache_miss", 0))) or 0),
                "output": float(raw.get("output", 0) or 0),
                "total": float(raw.get("total", 0) or 0),
                "request": float(raw.get("request", 0) or 0),
            }
        out["models"] = normalized
    return out


def _pricing(provider: str) -> dict[str, Any]:
    return _normalize_pricing_config(provider_config(provider).get("pricing", {}))


def _models(provider: str) -> dict[str, dict[str, float]]:
    models = _pricing(provider).get("models")
    if isinstance(models, dict) and models:
        return models
    return {}


def _aliases(provider: str) -> dict[str, str]:
    aliases = _pricing(provider).get("aliases")
    return aliases if isinstance(aliases, dict) else {}


def pricing_model(provider: str, model: str) -> str:
    models = _models(provider)
    canonical = _aliases(provider).get(str(model), str(model))
    if canonical in models:
        return canonical
    return ""


def pricing_source(provider: str = DEFAULT_PROVIDER) -> str:
    return str(provider_config(provider).get("pricing_source") or "")


def fx_rate(provider: str = DEFAULT_PROVIDER) -> float:
    pricing = _pricing(provider)
    try:
        return float(pricing.get("usd_cny", 7.2))
    except Exception:
        return 7.2


def _env_name(provider: str) -> str:
    value = provider_config(provider).get("api_key_env")
    if isinstance(value, str) and value:
        return value
    return ""


def load_provider_api_key(provider: str = DEFAULT_PROVIDER) -> str:
    """Load provider API key from process environment only."""
    name = _env_name(provider)
    if not name:
        return ""
    return read_env_secret(name)


def provider_health_items() -> list[dict[str, str]]:
    """Return generic LLM provider configuration status items for API health."""
    items: list[dict[str, str]] = []
    providers = llm_config().get("providers", {})
    for name, cfg in providers.items():
        if not isinstance(cfg, dict) or not cfg.get("enabled", True):
            continue
        label = str(cfg.get("label") or name)
        key = load_provider_api_key(name)
        if key:
            masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
            items.append({"name": f"LLM:{label}", "status": "ok", "detail": f"已配置 ({masked})"})
        else:
            env_hint = _env_name(name) or "provider API key"
            items.append({"name": f"LLM:{label}", "status": "missing", "detail": f"未配置 {env_hint}"})
    return items


def fetch_provider_balance(provider: str = DEFAULT_PROVIDER, api_key: str | None = None, *, timeout: float = 5.0) -> dict[str, Any]:
    """Fetch provider account balance when the provider exposes a supported API."""
    cfg = provider_config(provider)
    key = (api_key or load_provider_api_key(provider)).strip()
    label = str(cfg.get("label") or provider)
    if not key:
        return {"provider": provider, "label": label, "status": "missing", "is_available": False, "balance_infos": [], "message": "API key not configured"}

    balance_url = str(cfg.get("balance_url") or "").strip()
    if not balance_url:
        return {"provider": provider, "label": label, "status": "unsupported", "is_available": False, "balance_infos": [], "message": "balance API not configured"}

    request = urllib.request.Request(balance_url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"provider": provider, "label": label, "status": "error", "is_available": False, "balance_infos": [], "http_status": exc.code, "message": exc.reason}
    except Exception as exc:
        return {"provider": provider, "label": label, "status": "error", "is_available": False, "balance_infos": [], "message": type(exc).__name__}

    infos = payload.get("balance_infos") if isinstance(payload, dict) else []
    return {
        "provider": provider,
        "label": label,
        "status": "ok",
        "is_available": bool(payload.get("is_available")) if isinstance(payload, dict) else False,
        "balance_infos": infos if isinstance(infos, list) else [],
    }


def fetch_provider_balances(provider: str | None = None) -> dict[str, Any]:
    providers_cfg = llm_config().get("providers", {})
    if provider:
        if not isinstance(providers_cfg, dict) or provider not in providers_cfg:
            return {
                provider: {
                    "provider": provider,
                    "label": provider,
                    "status": "unknown",
                    "is_available": False,
                    "balance_infos": [],
                    "message": "provider not configured",
                }
            }
        return {provider: fetch_provider_balance(provider)}
    return {name: fetch_provider_balance(name) for name in enabled_providers()}


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


def _coerce_ts(created_at: str | datetime | None) -> datetime:
    if isinstance(created_at, datetime):
        return created_at.astimezone(timezone.utc)
    if created_at:
        return datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def normalize_llm_usage(
    provider: str,
    model: str,
    usage: Any,
    *,
    source: str = "unknown",
    request_id: str = "",
    created_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Normalize one provider usage object into a generic ledger row."""
    ts = _coerce_ts(created_at)
    prompt_tokens = _usage_value(usage, "prompt_tokens")
    hit = _usage_value(usage, "prompt_cache_hit_tokens")
    miss = _usage_value(usage, "prompt_cache_miss_tokens")
    if prompt_tokens and hit + miss == 0:
        miss = prompt_tokens
    output = _usage_value(usage, "completion_tokens")
    total = _usage_value(usage, "total_tokens", hit + miss + output) or (hit + miss + output)

    provider_models = _models(provider)
    priced_model = pricing_model(provider, model)
    pricing_status = "ok"
    cost_usd = 0.0
    if not provider_models:
        pricing_status = "missing_provider_pricing"
    elif not priced_model:
        pricing_status = "missing_model_pricing"
        priced_model = str(model)
    else:
        price = provider_models[priced_model]
        input_uncached_rate = price.get("input_cache_miss", price.get("input", 0.0))
        has_split_rate = bool(price.get("input_cache_hit") or input_uncached_rate or price.get("output"))
        cost_usd = (
            hit * price.get("input_cache_hit", 0.0)
            + miss * input_uncached_rate
            + output * price.get("output", 0.0)
        ) / 1_000_000
        if price.get("total") and not has_split_rate:
            cost_usd += total * price.get("total", 0.0) / 1_000_000
        if price.get("request"):
            cost_usd += price.get("request", 0.0)

    return {
        "ts": ts.isoformat(),
        "utc_date": ts.date().isoformat(),
        "provider": provider,
        "model": str(model),
        "pricing_model": priced_model,
        "pricing_status": pricing_status,
        "source": source,
        "request_id": request_id,
        "usage_source": "api_response",
        "usage_schema": str(provider_config(provider).get("usage_schema") or DEFAULT_USAGE_SCHEMA),
        "input_cache_hit": hit,
        "input_cache_miss": miss,
        "input_tokens": hit + miss,
        "output_tokens": output,
        "total_tokens": total,
        "requests": 1,
        "estimated_cost_usd": round(cost_usd, 9),
        "estimated_cost_cny": round(cost_usd * fx_rate(provider), 9),
        "pricing_source": pricing_source(provider),
    }


def append_llm_usage(
    provider: str,
    model: str,
    usage: Any,
    *,
    source: str = "unknown",
    request_id: str = "",
    created_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Append one provider response usage record to the generic project ledger."""
    row = normalize_llm_usage(provider, model, usage, source=source, request_id=request_id, created_at=created_at)
    hub = get_datahub()
    path = hub.llm_project_usage_path()
    existing = hub.read_parquet(path, default=pd.DataFrame())
    frame = pd.DataFrame([row])
    if existing is not None and not existing.empty:
        frame = pd.concat([existing, frame], ignore_index=True)
    frame = frame.sort_values(["utc_date", "ts", "provider", "model"]).reset_index(drop=True)
    hub.write_parquet(frame, path)
    return row


def record_llm_response_usage(response: Any, *, provider: str, model: str, source: str, request_id: str = "") -> dict[str, Any] | None:
    """Record usage from an OpenAI-compatible response object."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    return append_llm_usage(provider, model, usage, source=source, request_id=request_id)


def _read_usage_frames() -> list[pd.DataFrame]:
    hub = get_datahub()
    frames: list[pd.DataFrame] = []
    path = hub.llm_project_usage_path()
    if not path.exists():
        return frames
    df = hub.read_parquet(path, default=pd.DataFrame())
    if df is None or df.empty:
        return frames
    if "provider" not in df.columns:
        df["provider"] = DEFAULT_PROVIDER
    frames.append(df)
    return frames


def summarize_llm_project_usage(days: int = 30, provider: str | None = None) -> dict[str, Any]:
    """Return daily usage aggregated from the generic local ledger."""
    frames = _read_usage_frames()
    if not frames:
        return empty_usage_summary("no_data", days=days)
    df = pd.concat(frames, ignore_index=True)
    required = {"utc_date", "model", "provider"}
    if not required.issubset(df.columns):
        return empty_usage_summary("invalid", days=days)
    if provider:
        df = df[df["provider"].astype(str) == provider]
        if df.empty:
            return empty_usage_summary("no_data", days=days, provider=provider)

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
    df["provider"] = df["provider"].astype(str)
    df["model"] = df["model"].astype(str)
    if "pricing_status" not in df.columns:
        df["pricing_status"] = "ok"
    df["pricing_status"] = df["pricing_status"].astype(str).replace({"": "ok"})

    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=max(1, int(days)) - 1)).isoformat()
    df = df[df["utc_date"] >= cutoff]
    if df.empty:
        return empty_usage_summary("no_data", days=days, provider=provider)

    daily = (
        df.groupby(["utc_date", "provider", "model"], as_index=False)[numeric]
        .sum()
        .sort_values(["utc_date", "provider", "model"])
    )
    daily["usage_source"] = "api_response"
    daily["cost_cny"] = daily["estimated_cost_cny"]
    records = daily.to_dict(orient="records")
    pricing_statuses = sorted({status for status in df["pricing_status"].unique().tolist() if status != "ok"})
    unpriced_rows = int((df["pricing_status"] != "ok").sum())

    return {
        "status": "ok",
        "days": days,
        "provider": provider or "all",
        "daily": records,
        "providers": daily["provider"].unique().tolist(),
        "models": daily["model"].unique().tolist(),
        "dates": sorted(daily["utc_date"].unique().tolist()),
        "totals": {
            "tokens": int(daily["total_tokens"].sum()),
            "requests": int(daily["requests"].sum()),
            "estimated_cost_usd": round(float(daily["estimated_cost_usd"].sum()), 6),
            "estimated_cost_cny": round(float(daily["estimated_cost_cny"].sum()), 4),
        },
        "pricing_status": "partial" if pricing_statuses else "ok",
        "unpriced_rows": unpriced_rows,
        "unpriced_reasons": pricing_statuses,
        "pricing_source": ",".join(sorted({pricing_source(name) for name in daily["provider"].unique()})),
    }


def empty_usage_summary(status: str, *, days: int = 30, provider: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "days": days,
        "provider": provider or "all",
        "daily": [],
        "providers": [] if provider is None else [provider],
        "models": [],
        "dates": [],
        "totals": {"tokens": 0, "requests": 0, "estimated_cost_usd": 0.0, "estimated_cost_cny": 0.0},
        "pricing_status": "ok",
        "unpriced_rows": 0,
        "unpriced_reasons": [],
        "pricing_source": pricing_source(provider or DEFAULT_PROVIDER),
    }
