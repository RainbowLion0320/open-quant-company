"""
风险控制层 — Risk Manager

对标 vnpy RiskManager 设计。可插拔风险规则，配置驱动。
在 PaperBroker 下单前执行预检，阻止违规订单。

风险规则:
  1. 单只股票仓位上限 (max_single_position_pct)
  2. 总权益风险敞口上限 (max_total_exposure_pct)
  3. 单日最大下单次数 (max_orders_per_day)
  4. 最大回撤熔断 (max_drawdown_circuit_breaker)
  5. 单笔订单最大金额 (max_single_order_amount)

用法:
  from broker.risk import RiskManager
  rm = RiskManager(config)
  if rm.check_order(symbol, amount, portfolio):
      broker.submit(order)
"""
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from core.settings import get_settings, get_section


@dataclass
class RiskCheckResult:
    """单次风险检查结果"""
    passed: bool
    rule_name: str = ""
    reason: str = ""
    current_value: float = 0.0
    limit_value: float = 0.0


class RiskRule:
    """单个风险规则"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.enabled = config.get("enabled", True)
        self._config = config

    def check(self, context: dict) -> RiskCheckResult:
        """子类重写。context 包含 order/portfolio/history 等。"""
        return RiskCheckResult(passed=True, rule_name=self.name)


class MaxSinglePositionRule(RiskRule):
    """单只股票仓位上限"""

    def check(self, context: dict) -> RiskCheckResult:
        limit = self._config.get("max_pct", 0.25)
        order = context.get("order", {})
        portfolio = context.get("portfolio", {})

        symbol = order.get("symbol", "")
        order_amount = order.get("amount", 0)
        total_equity = portfolio.get("total_equity", 1)

        # 计算该股票当前仓位
        current_holding = portfolio.get("positions", {}).get(symbol, {}).get("market_value", 0)
        proposed_total = current_holding + order_amount
        proposed_pct = proposed_total / total_equity if total_equity > 0 else 1.0

        if proposed_pct > limit:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"{symbol} 仓位 {proposed_pct:.1%} 超过上限 {limit:.1%}",
                current_value=proposed_pct,
                limit_value=limit,
            )
        return RiskCheckResult(passed=True, rule_name=self.name)


class MaxTotalExposureRule(RiskRule):
    """总权益风险敞口上限"""

    def check(self, context: dict) -> RiskCheckResult:
        limit = self._config.get("max_pct", 0.80)
        portfolio = context.get("portfolio", {})

        total_exposure = portfolio.get("total_exposure", 0)
        total_equity = portfolio.get("total_equity", 1)
        order_amount = context.get("order", {}).get("amount", 0)
        proposed_exposure = total_exposure + order_amount
        exposure_pct = proposed_exposure / total_equity if total_equity > 0 else 0

        if exposure_pct > limit:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"总敞口 {exposure_pct:.1%} 超过上限 {limit:.1%}",
                current_value=exposure_pct,
                limit_value=limit,
            )
        return RiskCheckResult(passed=True, rule_name=self.name)


class MaxOrdersPerDayRule(RiskRule):
    """单日最大下单次数"""

    def check(self, context: dict) -> RiskCheckResult:
        limit = self._config.get("max_count", 50)
        today_orders = context.get("today_orders", 0)

        if today_orders >= limit:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"当日下单 {today_orders} 次已达上限 {limit}",
                current_value=today_orders,
                limit_value=limit,
            )
        return RiskCheckResult(passed=True, rule_name=self.name)


class MaxDrawdownCircuitBreaker(RiskRule):
    """最大回撤熔断"""

    def check(self, context: dict) -> RiskCheckResult:
        limit = self._config.get("max_drawdown_pct", -0.15)
        portfolio = context.get("portfolio", {})

        peak_equity = portfolio.get("peak_equity", 0)
        current_equity = portfolio.get("total_equity", 0)

        if peak_equity <= 0:
            return RiskCheckResult(passed=True, rule_name=self.name)

        drawdown = (current_equity - peak_equity) / peak_equity

        if drawdown < limit:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"回撤 {drawdown:.1%} 触发熔断 (阈值 {limit:.1%})",
                current_value=drawdown,
                limit_value=limit,
            )
        return RiskCheckResult(passed=True, rule_name=self.name)


class MaxSingleOrderAmountRule(RiskRule):
    """单笔订单最大金额"""

    def check(self, context: dict) -> RiskCheckResult:
        limit = self._config.get("max_amount", 500000)
        order = context.get("order", {})
        amount = order.get("amount", 0)

        if amount > limit:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"订单金额 ¥{amount:,.0f} 超过上限 ¥{limit:,.0f}",
                current_value=amount,
                limit_value=limit,
            )
        return RiskCheckResult(passed=True, rule_name=self.name)


# ── Rule registry ──

RULE_CLASSES: Dict[str, type] = {
    "max_single_position": MaxSinglePositionRule,
    "max_total_exposure": MaxTotalExposureRule,
    "max_orders_per_day": MaxOrdersPerDayRule,
    "max_drawdown_circuit_breaker": MaxDrawdownCircuitBreaker,
    "max_single_order_amount": MaxSingleOrderAmountRule,
}


class RiskManager:
    """
    风险管理器。

    从 config/settings.yaml → risk_control 段加载规则。
    预检通过后才能下单。所有不通过的原因汇总返回。
    """

    def __init__(self, config_path: Optional[Path] = None):
        risk_cfg = (
            get_settings(config_path).get("risk_control", {})
            if config_path is not None
            else get_section("risk_control", {})
        )
        self._rules: List[RiskRule] = []
        self._daily_order_count: int = 0
        self._last_reset_date: str = ""

        for rule_name, rule_cls in RULE_CLASSES.items():
            rule_config = risk_cfg.get(rule_name, {})
            if rule_config.get("enabled", True):
                self._rules.append(rule_cls(rule_name, rule_config))

    def check_order(
        self,
        symbol: str,
        amount: float,
        portfolio: dict,
    ) -> Tuple[bool, List[RiskCheckResult]]:
        """
        检查一笔订单是否通过所有风险规则。

        Args:
            symbol: 股票代码
            amount: 订单金额 (买入为正, 卖出为负)
            portfolio: 当前组合状态

        Returns:
            (passed, [results]) — passed 为 True 表示全部通过
        """
        self._maybe_reset_daily()

        context = {
            "order": {"symbol": symbol, "amount": abs(amount)},
            "portfolio": portfolio,
            "today_orders": self._daily_order_count,
        }

        results = []
        for rule in self._rules:
            result = rule.check(context)
            results.append(result)
            if not result.passed:
                return False, results

        return True, results

    def record_order(self):
        """记录一笔通过检查的订单"""
        self._daily_order_count += 1

    def check_portfolio(self, portfolio: dict) -> List[RiskCheckResult]:
        """
        检查整个组合是否有风险违规 (不依赖具体订单)。
        用于定时监控。
        """
        self._maybe_reset_daily()

        context = {
            "order": {"symbol": "", "amount": 0},
            "portfolio": portfolio,
            "today_orders": self._daily_order_count,
        }

        results = []
        for rule in self._rules:
            if isinstance(rule, MaxOrdersPerDayRule):
                continue  # 不适用组合级检查
            result = rule.check(context)
            results.append(result)

        return results

    def _maybe_reset_daily(self):
        """跨天重置日计数器"""
        today = time.strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._daily_order_count = 0
            self._last_reset_date = today

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def summary(self) -> str:
        lines = [f"RiskManager: {len(self._rules)} active rules"]
        for r in self._rules:
            lines.append(f"  ✓ {r.name} (enabled={r.enabled})")
        return "\n".join(lines)
