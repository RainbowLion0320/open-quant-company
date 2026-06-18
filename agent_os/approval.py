from __future__ import annotations

from agent_os.schemas import ApprovalPolicy


ACTION_EXPIRES_AFTER_SECONDS = 900
AUTO_RUN_RISK_LEVELS = {"read_only", "dry_run"}
APPROVAL_RISK_LEVELS = {
    "write_data",
    "write_config",
    "write_artifact",
    "run_backtest",
    "paper_order",
    "live_order",
    "code_change",
}
ALL_RISK_LEVELS = AUTO_RUN_RISK_LEVELS | APPROVAL_RISK_LEVELS
RISK_LEVEL_ORDER = [
    "read_only",
    "dry_run",
    "write_data",
    "write_config",
    "write_artifact",
    "run_backtest",
    "paper_order",
    "live_order",
    "code_change",
]


APPROVAL_POLICIES: dict[str, ApprovalPolicy] = {
    "read_only": ApprovalPolicy(
        policy_id="agent_policy.read_only",
        risk_level="read_only",
        default_decision="auto_run",
        required_role="",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="Read-only actions may run automatically through fixed registry commands.",
        approval_required=False,
    ),
    "dry_run": ApprovalPolicy(
        policy_id="agent_policy.dry_run",
        risk_level="dry_run",
        default_decision="auto_run",
        required_role="",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="Dry-run actions may run automatically when they do not mutate production data or broker state.",
        approval_required=False,
    ),
    "write_data": ApprovalPolicy(
        policy_id="agent_policy.write_data",
        risk_level="write_data",
        default_decision="approval_required",
        required_role="ceo",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="Data writes, repairs, and backfills require CEO approval before execution.",
        approval_required=True,
    ),
    "write_config": ApprovalPolicy(
        policy_id="agent_policy.write_config",
        risk_level="write_config",
        default_decision="approval_required",
        required_role="ceo",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="Configuration changes require CEO approval and diff evidence.",
        approval_required=True,
    ),
    "write_artifact": ApprovalPolicy(
        policy_id="agent_policy.write_artifact",
        risk_level="write_artifact",
        default_decision="approval_required",
        required_role="ceo",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="Agent-generated report or audit artifacts require CEO approval before writing local evidence.",
        approval_required=True,
    ),
    "run_backtest": ApprovalPolicy(
        policy_id="agent_policy.run_backtest",
        risk_level="run_backtest",
        default_decision="approval_required",
        required_role="ceo",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="Official or long-running backtests require approval because they write evidence artifacts.",
        approval_required=True,
    ),
    "paper_order": ApprovalPolicy(
        policy_id="agent_policy.paper_order",
        risk_level="paper_order",
        default_decision="approval_required",
        required_role="ceo",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="PaperBroker orders require CEO approval and risk-gate evidence before submission.",
        approval_required=True,
    ),
    "live_order": ApprovalPolicy(
        policy_id="agent_policy.live_order",
        risk_level="live_order",
        default_decision="approval_required",
        required_role="ceo",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="MiniQMT/QMT live orders require explicit CEO approval, live readiness, risk gates, and kill-switch checks.",
        approval_required=True,
    ),
    "code_change": ApprovalPolicy(
        policy_id="agent_policy.code_change",
        risk_level="code_change",
        default_decision="work_order_required",
        required_role="maintainer",
        expires_after_seconds=ACTION_EXPIRES_AFTER_SECONDS,
        reason="The Web runtime cannot edit the repository; code changes must become engineering work orders.",
        approval_required=True,
    ),
}


def approval_policy_for_risk(risk_level: str) -> ApprovalPolicy:
    level = str(risk_level).strip()
    policy = APPROVAL_POLICIES.get(level)
    if policy is None:
        raise ValueError(f"Unknown agent action risk level: {risk_level}")
    return policy


def list_approval_policies() -> list[dict[str, object]]:
    return [APPROVAL_POLICIES[level].to_dict() for level in RISK_LEVEL_ORDER]


def approval_required_for_risk(risk_level: str) -> bool:
    return approval_policy_for_risk(risk_level).approval_required
