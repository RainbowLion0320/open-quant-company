"""
独立风险分析模块 — 借鉴 qlib/rqalpha 的评估指标

设计理念:
  零依赖, 纯numpy实现, 未来可替换为rqrisk但不强制

指标清单:
  收益类: annual_return, cumulative_return, monthly_returns
  风险类: volatility, max_drawdown, downside_risk, VaR, CVaR
  风险调整: sharpe, sortino, calmar, information_ratio
  因子: alpha, beta, rank_IC, IC_IR
  交易: win_rate, profit_factor, avg_win_loss_ratio

用法:
  from backtest.analytics import RiskAnalytics
  metrics = RiskAnalytics.compute(daily_returns, benchmark_returns)
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, List
from dataclasses import dataclass, field


@dataclass
class FullReport:
    """完整风险报告"""
    # 收益
    annual_return: float = 0.0
    cumulative_return: float = 0.0
    total_return: float = 0.0

    # 风险
    volatility: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    downside_risk: float = 0.0
    var_95: float = 0.0

    # 风险调整收益
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0

    # 相对基准
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0
    tracking_error: float = 0.0
    excess_return: float = 0.0

    # 交易统计
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_loss_ratio: float = 0.0

    # 其他
    n_trading_days: int = 0
    monthly_returns: Optional[pd.Series] = None

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if k == "monthly_returns":
                continue
            if isinstance(v, float):
                d[k] = round(v, 4)
            else:
                d[k] = v
        return d

    def summary(self) -> str:
        lines = [
            "══════════════════════════════════",
            "  策略绩效报告",
            "══════════════════════════════════",
            f"  累计收益:    {self.cumulative_return*100:+.2f}%",
            f"  年化收益:    {self.annual_return*100:+.2f}%",
            f"  年化波动:    {self.volatility*100:.2f}%",
            f"  最大回撤:    {self.max_drawdown*100:.2f}%",
            f"  回撤持续:    {self.max_drawdown_duration} 天",
            f"  ─────────────────────────────",
            f"  Sharpe:      {self.sharpe:.2f}",
            f"  Sortino:     {self.sortino:.2f}",
            f"  Calmar:      {self.calmar:.2f}",
            f"  ─────────────────────────────",
            f"  Alpha:       {self.alpha*100:+.2f}%",
            f"  Beta:        {self.beta:.2f}",
            f"  Info Ratio:  {self.information_ratio:.2f}",
            f"  ─────────────────────────────",
            f"  胜率:        {self.win_rate*100:.1f}%",
            f"  盈亏比:      {self.win_loss_ratio:.2f}",
            f"  盈利因子:    {self.profit_factor:.2f}",
            f"══════════════════════════════════",
        ]
        return "\n".join(lines)


class RiskAnalytics:
    """风险分析 — 所有方法均为静态, 可直接import使用"""

    PERIODS_PER_YEAR = 252

    @classmethod
    def compute(
        cls,
        daily_returns: pd.Series,
        benchmark_returns: Optional[pd.Series] = None,
        risk_free: float = 0.03,
        periods_per_year: int = 252,
    ) -> FullReport:
        """一次性计算所有指标"""
        r = daily_returns.dropna().values
        if len(r) < 10:
            return FullReport()

        report = FullReport()
        report.n_trading_days = len(r)

        # 收益
        report.total_return = cls.total_return(r)
        report.annual_return = cls.annual_return(r, periods_per_year)
        report.cumulative_return = report.total_return

        # 风险
        report.volatility = cls.volatility(r, periods_per_year)
        report.max_drawdown, report.max_drawdown_duration = cls.max_drawdown_metrics(r)
        report.downside_risk = cls.downside_risk(r, periods_per_year)
        report.var_95 = cls.var_95(r)

        # 风险调整
        report.sharpe = cls.sharpe_ratio(r, risk_free, periods_per_year)
        report.sortino = cls.sortino_ratio(r, risk_free, periods_per_year)
        report.calmar = cls.calmar_ratio(r, periods_per_year)

        # 相对基准
        if benchmark_returns is not None:
            b = benchmark_returns.reindex(daily_returns.index).dropna().values
            if len(b) > 10:
                common_len = min(len(r), len(b))
                report.alpha, report.beta = cls.alpha_beta(
                    r[-common_len:], b[-common_len:], risk_free, periods_per_year
                )
                report.information_ratio = cls.information_ratio(
                    r[-common_len:], b[-common_len:], periods_per_year
                )
                report.tracking_error = cls.tracking_error(r[-common_len:], b[-common_len:], periods_per_year)
                report.excess_return = report.annual_return - cls.annual_return(b, periods_per_year)

        # 交易统计
        wins = r[r > 0]
        losses = r[r < 0]
        report.win_rate = len(wins) / len(r) if len(r) > 0 else 0
        report.avg_win = wins.mean() if len(wins) > 0 else 0
        report.avg_loss = losses.mean() if len(losses) > 0 else 0
        report.win_loss_ratio = abs(report.avg_win / report.avg_loss) if report.avg_loss != 0 else 0
        report.profit_factor = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")

        # 月度收益
        if isinstance(daily_returns.index, pd.DatetimeIndex):
            report.monthly_returns = daily_returns.resample("ME").apply(
                lambda x: np.prod(1 + x) - 1
            )

        return report

    # ── 收益指标 ──

    @staticmethod
    def total_return(r: np.ndarray) -> float:
        return np.prod(1 + r) - 1

    @staticmethod
    def annual_return(r: np.ndarray, periods: int = 252) -> float:
        return (1 + np.mean(r)) ** periods - 1

    # ── 风险指标 ──

    @staticmethod
    def volatility(r: np.ndarray, periods: int = 252) -> float:
        return np.std(r, ddof=1) * np.sqrt(periods)

    @staticmethod
    def max_drawdown_metrics(r: np.ndarray) -> tuple:
        """返回 (最大回撤, 最长回撤持续天数)"""
        cum = np.cumprod(1 + r)
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak

        max_dd = dd.min()

        # 最长回撤持续天数
        in_dd = dd < 0
        if not in_dd.any():
            return max_dd, 0
        durations = []
        count = 0
        for flag in in_dd:
            if flag:
                count += 1
            else:
                if count > 0:
                    durations.append(count)
                count = 0
        if count > 0:
            durations.append(count)
        max_duration = max(durations) if durations else 0

        return max_dd, max_duration

    @staticmethod
    def downside_risk(r: np.ndarray, periods: int = 252) -> float:
        downside = np.minimum(r, 0)
        return np.sqrt(np.mean(downside**2)) * np.sqrt(periods) if len(r) > 0 else 0

    @staticmethod
    def var_95(r: np.ndarray) -> float:
        return np.percentile(r, 5)

    @staticmethod
    def tracking_error(r: np.ndarray, benchmark_r: np.ndarray, periods: int = 252) -> float:
        excess = r - benchmark_r
        return np.std(excess, ddof=1) * np.sqrt(periods)

    # ── 风险调整收益 ──

    @staticmethod
    def sharpe_ratio(r: np.ndarray, rf: float = 0.03, periods: int = 252) -> float:
        excess = np.mean(r) - rf / periods
        std = np.std(r, ddof=1)
        return excess / std * np.sqrt(periods) if std > 0 else 0

    @staticmethod
    def sortino_ratio(r: np.ndarray, rf: float = 0.03, periods: int = 252) -> float:
        excess = np.mean(r) - rf / periods
        downside = RiskAnalytics.downside_risk(r, 1)  # daily downside
        return excess / downside * np.sqrt(periods) if downside > 0 else 0

    @staticmethod
    def calmar_ratio(r: np.ndarray, periods: int = 252) -> float:
        ann_ret = RiskAnalytics.annual_return(r, periods)
        max_dd, _ = RiskAnalytics.max_drawdown_metrics(r)
        return ann_ret / abs(max_dd) if max_dd != 0 else 0

    @staticmethod
    def information_ratio(r: np.ndarray, benchmark_r: np.ndarray, periods: int = 252) -> float:
        excess = r - benchmark_r
        te = np.std(excess, ddof=1) * np.sqrt(periods)
        return np.mean(excess) * periods / te if te > 0 else 0

    # ── 因子相关 ──

    @staticmethod
    def alpha_beta(r: np.ndarray, benchmark_r: np.ndarray, rf: float = 0.03, periods: int = 252) -> tuple:
        """返回 (alpha, beta)"""
        cov = np.cov(r, benchmark_r)
        if cov.shape != (2, 2):
            return 0.0, 1.0
        beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 1.0
        ann_r = RiskAnalytics.annual_return(r, periods)
        ann_b = RiskAnalytics.annual_return(benchmark_r, periods)
        alpha = ann_r - rf - beta * (ann_b - rf)
        return alpha, beta

    @staticmethod
    def rank_ic(predictions: np.ndarray, forward_returns: np.ndarray) -> float:
        """Spearman Rank IC"""
        from scipy.stats import spearmanr
        mask = ~(np.isnan(predictions) | np.isnan(forward_returns))
        if mask.sum() < 5:
            return 0.0
        return spearmanr(predictions[mask], forward_returns[mask]).correlation

    @staticmethod
    def ic_ir(ic_series: List[float]) -> float:
        """IC Information Ratio: mean(IC) / std(IC)"""
        ic = np.array(ic_series)
        return np.mean(ic) / np.std(ic, ddof=1) if len(ic) > 1 and np.std(ic, ddof=1) > 0 else 0


# ── 简化函数（方便直接import） ──

sharpe = RiskAnalytics.sharpe_ratio
max_dd = lambda r: RiskAnalytics.max_drawdown_metrics(r)[0]
annual_return = RiskAnalytics.annual_return
volatility = RiskAnalytics.volatility
