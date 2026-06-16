from __future__ import annotations

from typing import Any

from core.env_secrets import secret_status

from astrolabe_cli.results import CliResult


SUPPORTED_LLM_PROTOCOLS = {"openai_compatible"}


def _validate_llm_config(cfg: dict[str, Any]) -> list[str]:
    llm = cfg.get("llm", {})
    if not isinstance(llm, dict):
        return []
    errors: list[str] = []
    providers = llm.get("providers", {})
    providers = providers if isinstance(providers, dict) else {}
    use_cases = llm.get("use_cases", {})
    use_cases = use_cases if isinstance(use_cases, dict) else {}
    default_provider = str(llm.get("default_provider") or "").strip()
    if default_provider and default_provider not in providers:
        errors.append(f"llm.default_provider unknown: {default_provider}")
    for use_case, raw in use_cases.items():
        if not isinstance(raw, dict):
            errors.append(f"llm.use_cases.{use_case} invalid")
            continue
        provider = str(raw.get("provider") or "").strip()
        model = str(raw.get("model") or "").strip()
        if not provider:
            errors.append(f"llm.use_cases.{use_case}.provider missing")
        elif provider not in providers:
            errors.append(f"llm.use_cases.{use_case}.provider unknown: {provider}")
        if not model:
            errors.append(f"llm.use_cases.{use_case}.model missing")
    for provider, raw in providers.items():
        if not isinstance(raw, dict):
            errors.append(f"llm.providers.{provider} invalid")
            continue
        if not raw.get("enabled", True):
            continue
        protocol = str(raw.get("protocol") or "openai_compatible").strip()
        if protocol not in SUPPORTED_LLM_PROTOCOLS:
            errors.append(f"llm.providers.{provider}.protocol unsupported: {protocol}")
        for key in ("api_key_env", "base_url", "default_model"):
            if not str(raw.get(key) or "").strip():
                errors.append(f"llm.providers.{provider}.{key} missing")
    return errors


def validate_config() -> CliResult:
    from core.settings import get_settings
    from data.strategy.catalog import get_enabled_strategies, load_registry

    cfg = get_settings()
    registry = load_registry(force_reload=True)
    enabled = get_enabled_strategies()
    required = {"strategies", "backtest", "risk_control"}
    missing = sorted(section for section in required if section not in cfg)
    errors = [f"missing section: {name}" for name in missing]
    errors.extend(_validate_llm_config(cfg))
    ok = not errors
    return CliResult(
        ok=ok,
        command="config validate",
        message="Config valid" if ok else "Config missing required sections",
        data={
            "strategy_count": len(registry),
            "enabled_strategy_count": len(enabled),
            "missing_sections": missing,
            "llm_provider_count": len((cfg.get("llm", {}).get("providers", {}) if isinstance(cfg.get("llm"), dict) else {}) or {}),
        },
        errors=errors,
    )


def env_status() -> CliResult:
    """Inspect required process-environment secrets without exposing values."""
    from data.llm.usage import llm_config

    secrets: dict[str, dict[str, object]] = {
        "tushare": secret_status("TUSHARE_TOKEN"),
    }

    providers = llm_config().get("providers", {})
    if isinstance(providers, dict):
        for name, cfg in providers.items():
            if not isinstance(cfg, dict) or not cfg.get("enabled", True):
                continue
            raw = cfg.get("api_key_env")
            if isinstance(raw, str) and raw:
                secrets[f"llm.{name}"] = secret_status(raw)

    missing = sorted(key for key, item in secrets.items() if item.get("status") != "ok")
    ok = not missing
    return CliResult(
        ok=ok,
        command="config env",
        message="Environment secrets configured" if ok else "Missing required environment secrets",
        data={
            "secrets": secrets,
            "ok_count": len(secrets) - len(missing),
            "missing_count": len(missing),
            "missing": missing,
        },
        errors=[f"missing secret: {key}" for key in missing],
    )
