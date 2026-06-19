from __future__ import annotations

import copy
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.env_secrets import read_env_secret
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_provider_model_discovery (
            provider TEXT PRIMARY KEY,
            models_json TEXT NOT NULL,
            status TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            error TEXT NOT NULL,
            discovered_at TEXT NOT NULL
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


def _configured_model_options(provider: str) -> list[str]:
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


def cached_model_discovery(provider: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT models_json, status, endpoint, error, discovered_at
            FROM llm_provider_model_discovery
            WHERE provider = ?
            """,
            (str(provider),),
        ).fetchone()
    if row is None:
        return {
            "status": "not_checked",
            "endpoint": "",
            "error": "",
            "discovered_at": "",
            "discovered_models": [],
        }
    try:
        models = json.loads(str(row["models_json"] or "[]"))
    except json.JSONDecodeError:
        models = []
    if not isinstance(models, list):
        models = []
    return {
        "status": str(row["status"] or "not_checked"),
        "endpoint": str(row["endpoint"] or ""),
        "error": str(row["error"] or ""),
        "discovered_at": str(row["discovered_at"] or ""),
        "discovered_models": sorted({str(model).strip() for model in models if str(model).strip()}),
    }


def _save_model_discovery(
    provider: str,
    *,
    status: str,
    endpoint: str,
    discovered_models: list[str] | None = None,
    error: str = "",
) -> dict[str, Any]:
    models = sorted({str(model).strip() for model in (discovered_models or []) if str(model).strip()})
    payload = {
        "provider": str(provider),
        "models_json": json.dumps(models, ensure_ascii=False),
        "status": str(status),
        "endpoint": str(endpoint),
        "error": str(error),
        "discovered_at": _now(),
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO llm_provider_model_discovery(provider, models_json, status, endpoint, error, discovered_at)
            VALUES(:provider, :models_json, :status, :endpoint, :error, :discovered_at)
            ON CONFLICT(provider) DO UPDATE SET
                models_json = excluded.models_json,
                status = excluded.status,
                endpoint = excluded.endpoint,
                error = excluded.error,
                discovered_at = excluded.discovered_at
            """,
            payload,
        )
    return {
        "provider": str(provider),
        "status": payload["status"],
        "endpoint": payload["endpoint"],
        "error": payload["error"],
        "discovered_at": payload["discovered_at"],
        "discovered_models": models,
    }


def _models_endpoint(provider_cfg: dict[str, Any]) -> str:
    base_url = str(provider_cfg.get("base_url") or "").strip().rstrip("/")
    request_cfg = provider_cfg.get("request") if isinstance(provider_cfg.get("request"), dict) else {}
    path = str(provider_cfg.get("models_path") or request_cfg.get("models_path") or "/models").strip() or "/models"
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base_url}{path}"


def _model_discovery_timeout(provider_cfg: dict[str, Any]) -> float:
    request_cfg = provider_cfg.get("request") if isinstance(provider_cfg.get("request"), dict) else {}
    raw = provider_cfg.get("model_discovery_timeout_seconds", request_cfg.get("model_discovery_timeout_seconds", 10.0))
    try:
        return max(1.0, min(float(raw), 30.0))
    except (TypeError, ValueError):
        return 10.0


def _parse_openai_models_payload(payload: Any) -> list[str]:
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    models: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            model = str(row.get("id") or "").strip()
        else:
            model = str(row or "").strip()
        if model:
            models.add(model)
    return sorted(models)


def discover_provider_models(provider: str) -> dict[str, Any]:
    provider = str(provider or "").strip()
    providers = _provider_map()
    cfg = providers.get(provider)
    if not isinstance(cfg, dict):
        raise RuntimeProfileError("provider_not_configured")
    endpoint = _models_endpoint(cfg)
    if not cfg.get("enabled", True):
        return _save_model_discovery(provider, status="provider_disabled", endpoint=endpoint)
    if str(cfg.get("protocol") or "openai_compatible") != "openai_compatible":
        return _save_model_discovery(provider, status="unsupported_protocol", endpoint=endpoint)
    if not str(cfg.get("base_url") or "").strip():
        return _save_model_discovery(provider, status="base_url_missing", endpoint=endpoint)
    credential_env = str(cfg.get("api_key_env") or "")
    if not credential_env:
        return _save_model_discovery(provider, status="api_key_env_missing", endpoint=endpoint)
    api_key = read_env_secret(credential_env)
    if not api_key:
        return _save_model_discovery(provider, status="missing_secret", endpoint=endpoint)

    request = urllib.request.Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_model_discovery_timeout(cfg)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _save_model_discovery(provider, status="http_error", endpoint=endpoint, error=str(exc.code))
    except urllib.error.URLError as exc:
        return _save_model_discovery(provider, status="network_error", endpoint=endpoint, error=str(exc.reason))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _save_model_discovery(provider, status="invalid_response", endpoint=endpoint, error=exc.__class__.__name__)

    discovered = _parse_openai_models_payload(payload)
    discovery = _save_model_discovery(provider, status="ok", endpoint=endpoint, discovered_models=discovered)
    discovery["models"] = model_options(provider)
    return discovery


def model_options(provider: str) -> list[str]:
    models = set(_configured_model_options(provider))
    discovery = cached_model_discovery(provider)
    if discovery.get("status") == "ok":
        models.update(str(model) for model in discovery.get("discovered_models", []) if str(model).strip())
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
                "model_discovery": cached_model_discovery(str(provider)),
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
