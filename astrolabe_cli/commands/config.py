from __future__ import annotations

from astrolabe_cli.results import CliResult


def validate_config() -> CliResult:
    from core.settings import get_settings
    from data.registry import get_enabled_strategies, load_registry

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
