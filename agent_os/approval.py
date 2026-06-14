from __future__ import annotations

AUTO_RUN_RISK_LEVELS = {"read_only", "dry_run"}
APPROVAL_RISK_LEVELS = {
    "write_data",
    "write_config",
    "run_backtest",
    "paper_order",
    "live_order",
    "code_change",
}
ALL_RISK_LEVELS = AUTO_RUN_RISK_LEVELS | APPROVAL_RISK_LEVELS


def approval_required_for_risk(risk_level: str) -> bool:
    level = str(risk_level).strip()
    if level not in ALL_RISK_LEVELS:
        raise ValueError(f"Unknown agent action risk level: {risk_level}")
    return level in APPROVAL_RISK_LEVELS
