from __future__ import annotations

import copy
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.env_secrets import secret_status
from core.settings import get_settings
from data.storage.datahub import get_datahub


CONTROLLED_LLM_USE_CASES = (
    "agent_routing",
    "agent_tool_planning",
    "agent_response",
    "agent_planning",
    "factor_hypothesis",
)
DEFAULT_PROFILE_ID = "global"


class RuntimeProfileError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    path = get_datahub().db_path("llm_runtime.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_runtime_profiles (
            profile_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            reasoning_mode TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def active_profile() -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT provider, model, reasoning_mode, updated_at FROM llm_runtime_profiles WHERE profile_id = ?",
            (DEFAULT_PROFILE_ID,),
        ).fetchone()
    if row is None:
        return None
    return {
        "source": "global_override",
        "provider": str(row["provider"]),
        "model": str(row["model"]),
        "reasoning_mode": str(row["reasoning_mode"] or "default"),
        "updated_at": str(row["updated_at"]),
    }


def save_active_profile(*, provider: str, model: str, reasoning_mode: str = "default") -> dict[str, Any]:
    payload = {
        "profile_id": DEFAULT_PROFILE_ID,
        "provider": str(provider).strip(),
        "model": str(model).strip(),
        "reasoning_mode": str(reasoning_mode or "default").strip() or "default",
        "updated_at": _now(),
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO llm_runtime_profiles(profile_id, provider, model, reasoning_mode, updated_at)
            VALUES(:profile_id, :provider, :model, :reasoning_mode, :updated_at)
            ON CONFLICT(profile_id) DO UPDATE SET
                provider = excluded.provider,
                model = excluded.model,
                reasoning_mode = excluded.reasoning_mode,
                updated_at = excluded.updated_at
            """,
            payload,
        )
    return {
        "source": "global_override",
        "provider": payload["provider"],
        "model": payload["model"],
        "reasoning_mode": payload["reasoning_mode"],
        "updated_at": payload["updated_at"],
    }


def clear_active_profile() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM llm_runtime_profiles WHERE profile_id = ?", (DEFAULT_PROFILE_ID,))


def llm_settings() -> dict[str, Any]:
    settings = get_settings()
    llm = settings.get("llm", {}) if isinstance(settings.get("llm"), dict) else {}
    return llm if isinstance(llm, dict) else {}


def controlled_use_case(use_case: str) -> bool:
    return str(use_case) in CONTROLLED_LLM_USE_CASES


def configured_profile_for_use_case(use_case: str) -> dict[str, Any]:
    cfg = llm_settings()
    use_cases = cfg.get("use_cases", {})
    use_case_cfg = use_cases.get(use_case, {}) if isinstance(use_cases, dict) else {}
    providers = cfg.get("providers", {})
    provider = str(use_case_cfg.get("provider") or cfg.get("default_provider") or "").strip()
    provider_cfg = providers.get(provider) if isinstance(providers, dict) else {}
    model = str(use_case_cfg.get("model") or (provider_cfg or {}).get("default_model") or "").strip()
    request = use_case_cfg.get("request") if isinstance(use_case_cfg, dict) else {}
    provider_request = provider_cfg.get("request") if isinstance(provider_cfg, dict) else {}
    request = request if isinstance(request, dict) else provider_request if isinstance(provider_request, dict) else {}
    return {
        "source": "settings",
        "provider": provider,
        "model": model,
        "reasoning_mode": str(request.get("reasoning_level") or request.get("reasoning_effort") or "default"),
        "updated_at": "",
    }


def effective_profile(use_case: str = "agent_response") -> dict[str, Any]:
    saved = active_profile() if controlled_use_case(use_case) else None
    return saved or configured_profile_for_use_case(use_case)


def _provider_map() -> dict[str, dict[str, Any]]:
    providers = llm_settings().get("providers", {})
    return providers if isinstance(providers, dict) else {}


def model_options(provider: str) -> list[str]:
    provider_cfg = _provider_map().get(provider, {})
    if not isinstance(provider_cfg, dict):
        return []
    models: set[str] = set()
    default_model = str(provider_cfg.get("default_model") or "").strip()
    if default_model:
        models.add(default_model)
    pricing = provider_cfg.get("pricing", {})
    pricing_models = pricing.get("models") if isinstance(pricing, dict) else {}
    if isinstance(pricing_models, dict):
        models.update(str(name) for name in pricing_models if str(name).strip())
    use_cases = llm_settings().get("use_cases", {})
    if isinstance(use_cases, dict):
        for raw in use_cases.values():
            if isinstance(raw, dict) and str(raw.get("provider") or "") == provider:
                model = str(raw.get("model") or "").strip()
                if model:
                    models.add(model)
    return sorted(models)


def reasoning_mode_options(provider: str) -> list[dict[str, Any]]:
    provider_cfg = _provider_map().get(provider, {})
    modes = provider_cfg.get("reasoning_modes") if isinstance(provider_cfg, dict) else {}
    options = [
        {
            "key": "default",
            "label": "Default",
            "description": "Use provider/use-case default reasoning settings",
            "enabled": True,
        }
    ]
    if isinstance(modes, dict):
        for key, raw in modes.items():
            if not isinstance(raw, dict):
                continue
            options.append(
                {
                    "key": str(key),
                    "label": str(raw.get("label") or key),
                    "description": str(raw.get("description") or ""),
                    "enabled": bool(raw.get("enabled", True)),
                }
            )
    return options


def provider_options() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for provider, raw in sorted(_provider_map().items()):
        if not isinstance(raw, dict):
            continue
        credential_env = str(raw.get("api_key_env") or "")
        status = secret_status(credential_env) if credential_env else {"status": "missing", "source": credential_env}
        protocol = str(raw.get("protocol") or "openai_compatible")
        configured = bool(str(raw.get("base_url") or "").strip() and str(raw.get("default_model") or "").strip())
        out.append(
            {
                "provider": str(provider),
                "label": str(raw.get("label") or provider),
                "enabled": bool(raw.get("enabled", True)),
                "configured": configured,
                "protocol": protocol,
                "credential_env": credential_env,
                "secret_status": str(status.get("status") or "missing"),
                "models": model_options(str(provider)),
                "reasoning_modes": reasoning_mode_options(str(provider)),
            }
        )
    return out


def runtime_options() -> dict[str, Any]:
    return {
        "providers": provider_options(),
        "controlled_use_cases": list(CONTROLLED_LLM_USE_CASES),
    }


def validate_profile(*, provider: str, model: str, reasoning_mode: str) -> None:
    provider = str(provider or "").strip()
    model = str(model or "").strip()
    reasoning_mode = str(reasoning_mode or "default").strip() or "default"
    providers = _provider_map()
    if provider not in providers or not isinstance(providers.get(provider), dict):
        raise RuntimeProfileError("provider_not_configured")
    cfg = providers[provider]
    if not cfg.get("enabled", True):
        raise RuntimeProfileError("provider_disabled")
    if str(cfg.get("protocol") or "openai_compatible") != "openai_compatible":
        raise RuntimeProfileError("unsupported_protocol")
    if not str(cfg.get("base_url") or "").strip():
        raise RuntimeProfileError("base_url_missing")
    if not model:
        raise RuntimeProfileError("model_missing")
    if model not in model_options(provider):
        raise RuntimeProfileError("model_not_configured")
    credential_env = str(cfg.get("api_key_env") or "")
    if not credential_env:
        raise RuntimeProfileError("api_key_env_missing")
    if secret_status(credential_env).get("status") != "ok":
        raise RuntimeProfileError("missing_secret")
    mode_keys = {str(mode.get("key") or "") for mode in reasoning_mode_options(provider) if mode.get("enabled", True)}
    if reasoning_mode not in mode_keys:
        raise RuntimeProfileError("reasoning_mode_not_configured")


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _mode_request(provider: str, reasoning_mode: str) -> dict[str, Any]:
    if not reasoning_mode or reasoning_mode == "default":
        return {}
    provider_cfg = _provider_map().get(provider, {})
    modes = provider_cfg.get("reasoning_modes") if isinstance(provider_cfg, dict) else {}
    raw = modes.get(reasoning_mode) if isinstance(modes, dict) else None
    if not isinstance(raw, dict) or not bool(raw.get("enabled", True)):
        return {}
    request = raw.get("request", {})
    return copy.deepcopy(request) if isinstance(request, dict) else {}


def apply_reasoning_mode(request_cfg: dict[str, Any], *, provider: str, reasoning_mode: str) -> dict[str, Any]:
    mode_request = _mode_request(provider, reasoning_mode)
    if not mode_request:
        return request_cfg
    merged = copy.deepcopy(request_cfg)
    extra_body = mode_request.pop("extra_body", {})
    for key, value in mode_request.items():
        merged[key] = copy.deepcopy(value)
    if isinstance(extra_body, dict):
        current_extra = merged.get("extra_body") if isinstance(merged.get("extra_body"), dict) else {}
        merged["extra_body"] = _deep_merge(current_extra, extra_body)
    return merged

