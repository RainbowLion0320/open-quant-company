"""
回测管道 — 借鉴 rqalpha mod系统 + zvt Factor pipeline

所有策略参数从 config/settings.yaml 读取，不做硬编码。
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from core.settings import get_section

# ── 加载配置 ──
def _load_backtest_config() -> dict:
    return get_section("backtest", {}) or {}

_BC = _load_backtest_config()
_PC = _BC.get("pipeline", {})
_DEFAULT_BENCHMARK = _BC.get("benchmark", "sh000001")
_DEFAULT_COMMISSION = _BC.get("commission", 0.00081)
_DEFAULT_TOP_N = _PC.get("signal", {}).get("top_n", 20)
_DEFAULT_REBALANCE_FREQ = _PC.get("portfolio", {}).get("rebalance_freq", "ME")


@dataclass
class Context:
    """管道上下文 — 各阶段输入输出"""
    # 数据
    data: Optional[pd.DataFrame] = None
    universe: List[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""

    # 因子
    factors: Dict[str, pd.DataFrame] = field(default_factory=dict)

    # 信号
    signals: Optional[pd.DataFrame] = None  # index=date, cols=stock, value=buy_weight

    # 组合
    portfolio_weights: Optional[pd.DataFrame] = None

    # 订单
    orders: List[Dict] = field(default_factory=list)

    # 收益
    daily_returns: Optional[pd.Series] = None
    benchmark_returns: Optional[pd.Series] = None

    # 日志
    log: List[str] = field(default_factory=list)

    def info(self, msg: str):
        self.log.append(msg)


class Stage(ABC):
    """管道阶段基类"""

    def start_up(self, ctx: Context) -> None:
        pass

    @abstractmethod
    def process(self, ctx: Context) -> Context:
        pass

    def tear_down(self, ctx: Context) -> None:
        pass


class Pipeline:
    """管道执行器"""

    def __init__(self, stages: List[Stage], name: str = "Pipeline"):
        self.stages = stages
        self.name = name

    def run(self, ctx: Optional[Context] = None) -> Context:
        if ctx is None:
            ctx = Context()

        ctx.info(f"[{self.name}] Starting with {len(self.stages)} stages")

        for stage in self.stages:
            stage_name = stage.__class__.__name__
            ctx.info(f"  → {stage_name}.start_up()")
            stage.start_up(ctx)
            ctx.info(f"  → {stage_name}.process()")
            ctx = stage.process(ctx)
            stage.tear_down(ctx)
            ctx.info(f"  ← {stage_name} done")

        ctx.info(f"[{self.name}] Finished")
        return ctx


# ── 示例阶段实现 ──

class DataLoader(Stage):
    """数据加载阶段"""

    def __init__(self, symbols: List[str], start: str, end: str, source: str = "akshare"):
        self.symbols = symbols
        self.start = start
        self.end = end
        self.source = source

    def process(self, ctx: Context) -> Context:
        ctx.universe = self.symbols
        ctx.start_date = self.start
        ctx.end_date = self.end
        ctx.info(f"DataLoader: {len(self.symbols)} stocks, {self.start} → {self.end}")

        # 从缓存/API加载数据
        try:
            from data.fetcher import get_stock_daily
            dfs = {}
            for sym in self.symbols:
                df = get_stock_daily(sym)
                if df is not None and len(df) > 100:
                    col_name = f"{sym}_close"
                    dfs[col_name] = df.set_index("date")["close"].rename(col_name)
            if dfs:
                ctx.data = pd.concat(dfs.values(), axis=1)
                ctx.data.index = pd.to_datetime(ctx.data.index)
                ctx.data = ctx.data.sort_index()
                ctx.info(f"  Loaded {len(dfs)} stocks, {len(ctx.data)} rows")
            else:
                ctx.info("  ⚠️ No data loaded")
        except ImportError:
            ctx.info("  ⚠️ akshare not available, using empty data")
            ctx.data = pd.DataFrame()

        return ctx


class FactorStage(Stage):
    """因子计算阶段 — 用signals/factors.py的表达式引擎"""

    def __init__(self, factors: List, names: Optional[List[str]] = None):
        self.factors = factors
        self.names = names or [f"factor_{i}" for i in range(len(factors))]

    def process(self, ctx: Context) -> Context:
        if ctx.data is None or ctx.data.empty:
            ctx.info("FactorStage: no data, skipping")
            return ctx

        ctx.info(f"FactorStage: computing {len(self.factors)} factors")

        for factor, name in zip(self.factors, self.names):
            try:
                result = factor.load(ctx.data)
                ctx.factors[name] = result
                ctx.info(f"  {name}: mean={result.mean():.4f}, std={result.std():.4f}")
            except Exception as e:
                ctx.info(f"  {name}: ERROR — {e}")

        return ctx


class MultiFactorSignal(Stage):
    """多因子信号生成"""

    def __init__(self, weights: Dict[str, float], top_n: int = None, mode: str = "score"):
        """
        weights: {"factor_name": weight}
        top_n: 选前N只 (默认从config读)
        mode: "score" (加权打分) or "filter" (逐步过滤)
        """
        self.weights = weights
        self.top_n = top_n if top_n is not None else _DEFAULT_TOP_N
        self.mode = mode

    def process(self, ctx: Context) -> Context:
        if not ctx.factors:
            ctx.info("MultiFactorSignal: no factors, skipping")
            return ctx

        # 合并因子得分
        composite = None
        for name, weight in self.weights.items():
            if name not in ctx.factors:
                continue
            factor = ctx.factors[name].fillna(0)
            # 归一化到 [0,1]
            if factor.std() > 0:
                factor = (factor - factor.min()) / (factor.max() - factor.min() + 1e-9)
            weighted = factor * weight
            composite = weighted if composite is None else composite + weighted

        if composite is None:
            return ctx

        ctx.signals = composite
        ctx.info(f"MultiFactorSignal: composite score ready, top_n={self.top_n}")
        return ctx


class EqualWeightPortfolio(Stage):
    """等权组合构建"""

    def __init__(self, rebalance_freq: str = None):
        self.rebalance_freq = rebalance_freq if rebalance_freq else _DEFAULT_REBALANCE_FREQ

    def process(self, ctx: Context) -> Context:
        if ctx.signals is None:
            ctx.info("Portfolio: no signals, skipping")
            return ctx

        # 每月选TopN
        top_signals = ctx.signals.resample(self.rebalance_freq).last()
        ctx.portfolio_weights = pd.DataFrame(index=top_signals.index)
        ctx.info(f"Portfolio: {self.rebalance_freq} rebalancing, {len(top_signals)} periods")
        return ctx


class BacktestStage(Stage):
    """回测收益计算"""

    def __init__(self, benchmark_symbol: str = None, commission_rate: float = None):
        self.benchmark = benchmark_symbol if benchmark_symbol else _DEFAULT_BENCHMARK
        self.commission = commission_rate if commission_rate is not None else _DEFAULT_COMMISSION

    def process(self, ctx: Context) -> Context:
        if ctx.portfolio_weights is None or ctx.data is None:
            ctx.info("Backtest: no portfolio or data, skipping")
            return ctx

        # 简单演示: 用组合权重 × 收益率计算每日收益
        ctx.info(f"Backtest: commission={self.commission*100:.3f}%")

        try:
            from backtest.analytics import RiskAnalytics
            # 这里做实际回测计算...
            # 简化: 假设已计算出 daily_returns
            if ctx.daily_returns is not None:
                report = RiskAnalytics.compute(ctx.daily_returns)
                ctx.info(report.summary())
        except ImportError:
            pass

        return ctx


class EvidenceReportStage(Stage):
    """Write a strategy evidence report from a completed pipeline context."""

    def __init__(self, strategy: str, status: str = "candidate"):
        self.strategy = strategy
        self.status = status

    def process(self, ctx: Context) -> Context:
        from research.strategy_evaluation import build_evidence_report, write_strategy_evidence_report

        returns = ctx.daily_returns if ctx.daily_returns is not None else pd.Series(dtype="float64")
        metrics = {
            "cagr": float((1 + returns).prod() - 1) if len(returns) else 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "turnover": 0.0,
            "trades": len(ctx.orders),
        }
        report = build_evidence_report(
            strategy=self.strategy,
            status=self.status,
            metrics=metrics,
            oos={"months": 0, "start": ctx.start_date, "end": ctx.end_date},
        )
        path = write_strategy_evidence_report(report)
        ctx.info(f"EvidenceReport: wrote {path}")
        return ctx
