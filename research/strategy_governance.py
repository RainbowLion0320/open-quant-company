"""Strategy research governance and promotion gates.

This module reframes the four built-in strategies as layers in one research
stack, then applies explicit evidence gates before a strategy moves into paper
or production use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class StrategyRole:
    name: str
    layer: str
    primary_use: str
    description: str
    allow_paper: bool = False
    allow_production: bool = False


@dataclass(frozen=True)
class StrategyMetrics:
    cagr: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    turnover: float = 0.0
    win_rate: float = 0.0
    ic: float = 0.0
    icir: float = 0.0
    oos_months: int = 0
    trades: int = 0


@dataclass(frozen=True)
class PromotionDecision:
    target_status: str
    passed: bool
    failed_rules: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rationale: str = ""


PROMOTION_RULES = {
    "validated": {
        "min_oos_months": 12,
        "min_trades": 10,
        "min_ic": 0.01,
        "min_icir": 0.10,
        "max_drawdown": 0.35,
    },
    "paper": {
        "min_oos_months": 24,
        "min_trades": 24,
        "min_sharpe": 0.50,
        "min_ic": 0.02,
        "min_icir": 0.20,
        "max_drawdown": 0.25,
        "max_turnover": 6.0,
    },
    "production": {
        "min_oos_months": 36,
        "min_trades": 36,
        "min_sharpe": 0.70,
        "min_ic": 0.025,
        "min_icir": 0.35,
        "max_drawdown": 0.20,
        "max_turnover": 4.0,
    },
}


def default_strategy_roles() -> dict[str, StrategyRole]:
    return {
        "buffett": StrategyRole(
            name="buffett",
            layer="quality_filter",
            primary_use="过滤财务质量和估值陷阱，不作为独立高频 alpha",
            description="能力圈、护城河、安全边际约束层。",
            allow_paper=True,
            allow_production=True,
        ),
        "multifactor": StrategyRole(
            name="multifactor",
            layer="primary_alpha",
            primary_use="主 Alpha 打分和横截面排序",
            description="质量、估值、技术、市场、行业动量的可解释综合打分。",
            allow_paper=True,
            allow_production=True,
        ),
        "ml_lgbm": StrategyRole(
            name="ml_lgbm",
            layer="auxiliary_alpha",
            primary_use="辅助 Alpha 和非线性关系捕捉，必须受 OOS/IC 门槛约束",
            description="PIT 特征训练的 LightGBM regime-aware 模型。",
            allow_paper=True,
            allow_production=False,
        ),
        "cybernetic": StrategyRole(
            name="cybernetic",
            layer="risk_overlay",
            primary_use="市场状态、仓位、风险预算和资产配置层",
            description="不再定位为独立选股主策略，而是 regime 风险控制层。",
            allow_paper=True,
            allow_production=True,
        ),
    }


def strategy_stack(roles: dict[str, StrategyRole] | None = None) -> dict[str, list[str]]:
    stack: dict[str, list[str]] = {}
    for role in (roles or default_strategy_roles()).values():
        stack.setdefault(role.layer, []).append(role.name)
    return stack


def evaluate_promotion(metrics: StrategyMetrics, target_status: str = "paper") -> PromotionDecision:
    rules = PROMOTION_RULES.get(target_status)
    if not rules:
        return PromotionDecision(
            target_status=target_status,
            passed=False,
            failed_rules=["target_status"],
            rationale=f"Unknown target status: {target_status}",
        )

    failed: list[str] = []
    warnings: list[str] = []
    drawdown = abs(metrics.max_drawdown)

    if metrics.oos_months < rules.get("min_oos_months", 0):
        failed.append("oos_months")
    if metrics.trades < rules.get("min_trades", 0):
        failed.append("trades")
    if metrics.sharpe < rules.get("min_sharpe", -999):
        failed.append("sharpe")
    if drawdown > rules.get("max_drawdown", 1.0):
        failed.append("max_drawdown")
    if metrics.turnover > rules.get("max_turnover", float("inf")):
        failed.append("turnover")
    if metrics.ic < rules.get("min_ic", -999):
        failed.append("ic")
    if metrics.icir < rules.get("min_icir", -999):
        failed.append("icir")

    if metrics.win_rate < 0.45:
        warnings.append("win_rate")
    if metrics.cagr <= 0:
        warnings.append("cagr")

    passed = not failed
    rationale = (
        f"{target_status} gate {'passed' if passed else 'blocked'}: "
        f"Sharpe={metrics.sharpe:.2f}, MaxDD={drawdown:.1%}, IC={metrics.ic:.3f}, "
        f"ICIR={metrics.icir:.2f}, OOS={metrics.oos_months}m"
    )
    return PromotionDecision(
        target_status=target_status,
        passed=passed,
        failed_rules=failed,
        warnings=warnings,
        rationale=rationale,
    )


def governance_summary(strategy_names: Iterable[str] | None = None) -> dict:
    roles = default_strategy_roles()
    selected = list(strategy_names) if strategy_names is not None else list(roles)
    return {
        "roles": [roles[name].__dict__ for name in selected if name in roles],
        "stack": strategy_stack({name: roles[name] for name in selected if name in roles}),
        "promotion_rules": PROMOTION_RULES,
    }
