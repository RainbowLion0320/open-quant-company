from __future__ import annotations

from core.env_secrets import secret_status

from astrolabe_cli.results import CliResult


def validate_config() -> CliResult:
    from core.settings import get_settings
    from data.strategy.catalog import get_enabled_strategies, load_registry

    cfg = get_settings()
    registry = load_registry(force_reload=True)
    enabled = get_enabled_strategies()
    required = {"strategies", "backtest", "risk_control"}
    missing = sorted(section for section in required if section not in cfg)
    ok = not missing
    return CliResult(
        ok=ok,
        command="config validate",
        message="Config valid" if ok else "Config missing required sections",
        data={
            "strategy_count": len(registry),
            "enabled_strategy_count": len(enabled),
            "missing_sections": missing,
        },
        errors=[f"missing section: {name}" for name in missing],
    )


def env_status() -> CliResult:
    """Inspect required process-environment secrets without exposing values."""
    from data.llm.usage import llm_config

    secrets: dict[str, dict[str, object]] = {
        "tushare": secret_status("TUSHARE_TOKEN", aliases=("TUSHARE_PRO_TOKEN",)),
    }

    providers = llm_config().get("providers", {})
    if isinstance(providers, dict):
        for name, cfg in providers.items():
            if not isinstance(cfg, dict) or not cfg.get("enabled", True):
                continue
            raw = cfg.get("api_key_env")
            if isinstance(raw, list):
                env_names = [str(item) for item in raw if item]
            elif isinstance(raw, str) and raw:
                env_names = [raw]
            else:
                env_names = []
            if env_names:
                secrets[f"llm.{name}"] = secret_status(env_names[0], aliases=env_names[1:])

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
