# Spec: 回测引擎 (Backtest Engine)

> 版本: 1.2 | 日期: 2026-06-03 | 关联: [PRD](../PRD.md) [Signal System](02-signal-system.md) [Execution Layer](04-execution-layer.md)

## 1. 概述

回测引擎是策略验证的核心——在历史数据上模拟策略执行，输出风险收益指标。支持 N 策略同时跑对比（锦标赛模式），严格 PIT（Point-in-Time）无前视偏差。

**设计原则：**
- **PIT 零容忍** — 任何前视偏差都是 bug，不是 feature
- **策略可插拔** — `backtest/strategies/base.py` 定义评分/调仓接口，生产锦标赛复用信号层 scorer 和注册表
- **自研非 Backtrader** — 需要 PIT 特征存储和锦标赛对比，Backtrader 不满足
- **证据先行** — 候选策略晋级必须有强基准、OOS、walk-forward、成本模型和 regime 分解证据

## 2. 组件架构

```
┌─────────────────────────────────────────────────────┐
│            run_all_strategies.py                      │
│         N 策略锦标赛 — 统一入口                        │
└──────────────────────┬──────────────────────────────┘
                       │
       ┌───────────────┼───────────────┬───────────────┐
       │               │               │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│ base.py     │ │ml_strategy  │ │buffett_real │ │ pipeline.py │
│ BaseStrategy│ │ LightGBM    │ │ _scorer.py  │ │ 可插拔流水线 │
│ + Registry  │ │ 月度调仓     │ │ 滚动PIT评分  │ │ 自定义组合   │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │               │
       └───────────────┼───────────────┴───────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  analytics.py                         │
│              15 项风险指标计算                          │
│  收益率/CAGR/波动率/Sharpe/Sortino/Calmar             │
│  Alpha/Beta/MaxDD/DD Duration/VaR/CVaR               │
│  WinRate/ProfitFactor/RecoveryTime                    │
└─────────────────────────────────────────────────────┘
```

### 2.1 回测引擎核心 (run_all_strategies.py)

**日频逐日模拟：**
1. 加载价格矩阵（N 只股票 × T 个交易日）
2. 每月初运行策略评分 → 调仓
3. 每日计算持仓市值 → NAV
4. 通过 `pipeline.execution.ExecutionRouter` / `AShareExchange` 扣除交易成本（默认回测 commission_rate=0.00081、卖出 stamp_duty=0.0005，可注入交易所覆盖）

**锦标赛模式：** 同一时间区间内运行所有已注册策略，输出对比排名表。

**PIT 安全保障：**
- 评分只使用调仓日之前的数据
- Regime 检测用 `build_production_regime_map()` — 历史回放生产 champion policy，并将上一期已可见的 confirmed/raw 结果映射到当月
- 巴菲特评分用滚动窗口逐年评估，不跨年引用

### 2.2 策略基类 (strategies/base.py)

**BaseStrategy：** 统一策略抽象和注册表。
- `score(symbol, prices, idx, regime, **kwargs)` 输出 0-100 横截面评分
- `should_rebalance()` 默认月度再平衡，可由子类覆写
- `get_positions()` 根据评分、当前持仓、价格和资金生成 100 股整数倍目标持仓

### 2.3 ML 策略 (strategies/ml_strategy.py)

- `MLFeatureStoreAlphaModel` 按调仓日选择不晚于该日的最新 PIT as-of 特征视图，批量预测全股票池 score map
- 模型加载复用 `models/lgbm_runtime.py`，支持 global 与 regime-aware LightGBM 模型
- 特征矩阵进入 LightGBM 前统一数值化，避免 Parquet 对象 dtype 破坏正式回测
- Pipeline 继续负责 Top-N 组合构建、风控和成交模拟

### 2.4 可插拔流水线 (pipeline.py)

```python
from backtest.pipeline import (
    Context,
    Pipeline,
    DataLoader,
    FactorStage,
    MultiFactorSignal,
    EqualWeightPortfolio,
    BacktestStage,
)

ctx = Pipeline([
    DataLoader(["000001", "600519"], "2020-01-01", "2026-05-31"),
    FactorStage(factors, names),
    MultiFactorSignal({"momentum": 0.6, "value": 0.4}, top_n=10),
    EqualWeightPortfolio(),
    BacktestStage(),
]).run(Context())
```

### 2.5 风险分析 (analytics.py)

**15 项指标：**

| 类别 | 指标 | 公式/说明 |
|------|------|----------|
| 收益 | 总收益率 | (NAV[-1]/NAV[0] - 1) × 100% |
| 收益 | 年化收益率 (CAGR) | (NAV[-1]/NAV[0])^(252/n) - 1 |
| 风险 | 年化波动率 | std(daily_returns) × √252 |
| 风险 | 下行风险 | RMS(min(0, daily_returns)) × √252 |
| 风险收益 | Sharpe Ratio | mean(daily_returns - daily_rf) / std(daily_returns) × √252 |
| 风险收益 | Sortino Ratio | mean(daily_returns - daily_rf) / downside_risk × √252 |
| 风险收益 | Calmar Ratio | CAGR / MaxDD |
| 回撤 | Max Drawdown | max(1 - NAV/cummax(NAV)) |
| 回撤 | MaxDD Duration | 最长水下天数 |
| 回归 | Alpha | Jensen's Alpha vs 基准 |
| 回归 | Beta | cov(strategy, benchmark) / cov(benchmark, benchmark) |
| 尾部 | VaR 95% | 日收益 5% 分位数 |
| 尾部 | CVaR 95% | VaR 尾部均值 |
| 交易 | Win Rate | 盈利交易占比 |
| 交易 | Profit Factor | 总盈利/总亏损 |

**关键公式修复（v4.5）：**
- Sortino 下行风险：`np.sqrt(np.mean(downside**2))` — 使用 RMS 法而非 std
- Beta：`cov[0,1] / cov[1,1]` — 分母使用 cov[1,1] 保持 ddof 一致

### 2.6 基准

**默认基准：** 上证综指（`sh000001`），非个股（之前版本错误使用了平安银行 `000001`）。

### 2.7 候选策略证据报告

候选策略不能只凭单次收益曲线晋级。进入 `paper` 或 `production` 前必须输出证据报告并通过研究治理门槛：

- 强基准比较：`buy_and_hold`、`fixed_weight`、`ma_timing`、`trend_only`、`trend_breadth`、`current_champion`
- 样本外 OOS 月数与 walk-forward 结果
- 成本模型：佣金、滑点、A 股交易约束
- regime 分解：bull / sideways / bear 下的收益、回撤、交易频率
- promotion decision：目标状态、是否通过、失败规则和理由

证据报告写入：

```text
data/store/research/strategy_evidence/<strategy>.json
```

报告字段由 `research/strategy_evaluation.py` 统一构建，runner 只负责把回测结果映射到该契约。

## 3. 数据流

```
data/store/signals/*.parquet  (预计算信号)
          │
          ▼
    load_prices(pool, start, end)
          │ price matrix
          ▼
    ┌─────────────────┐
    │  逐日回测循环      │
    │  for dt in dates: │
    │    if 月初:        │
    │      regime检测    │
    │      策略评分       │
    │      调仓执行       │
    │    NAV计算         │
    └────────┬────────┘
             │ NAV series
             ▼
    RiskAnalytics.compute(daily_returns, benchmark_returns, risk_free_rates=rf_curve)
             │
             ▼
    FullReport: {metrics, trades, monthly_returns}
             │
             ▼
    data/tournament/{date}.json
             │
             ▼
    data/store/research/strategy_evidence/{strategy}.json
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 回测框架 | 自研（非 Backtrader） | 需要 PIT 特征存储 + 多策略锦标赛，Backtrader 不支持 |
| Regime 检测 | 生产 policy 历史回放 + 滞后一期 | 避免前视偏差，同时保证回测、锦标赛和 Web/API 采用同一套 regime 语义 |
| 调仓频率 | 月初第一个交易日 | 日频调仓成本过高，月度再平衡是行业惯例 |
| 基准选择 | 上证综指 (sh000001) | 全市场代表性最强 |
| 无风险利率 | 本地收益率曲线 (默认 CN 2Y) | Sharpe/Sortino/Alpha 不能使用固定值或静默 fallback |
| 交易约束 | 100 股整数倍 + 手续费 | 模拟真实 A 股交易规则 |
| 巴菲特评分 | 滚动窗口逐年评估 | 避免全局数据泄露 |
| 候选晋级证据 | 统一 JSON artifact | 避免 UI、文档和研究脚本各自解释策略是否可晋级 |

## 5. 接口合约

### 策略接口

```python
class BaseStrategy(ABC):
    @abstractmethod
    def score(
        self,
        symbol: str,
        prices: pd.Series | pd.DataFrame,
        idx: int,
        regime: str,
        **kwargs,
    ) -> float:
        """返回 0-100 横截面评分。"""
        ...

    def should_rebalance(self, dt, regime, last_regime=None, *args, **kwargs) -> bool:
        ...

    def get_positions(
        self,
        scores: dict[str, float],
        current_holdings: dict[str, int],
        prices: pd.Series,
        capital: float,
        max_positions: int = 8,
        position_ratio: float = 0.30,
    ) -> tuple[dict[str, int], float]:
        ...
```

### 分析接口

```python
from backtest.analytics import RiskAnalytics, FullReport
from data.risk_free_rates import risk_free_series_for_index

rf_curve = risk_free_series_for_index(daily_returns.index)
report: FullReport = RiskAnalytics.compute(
    daily_returns,
    benchmark_returns,
    risk_free_rates=rf_curve,
    periods_per_year=252,
)
metrics: dict = report.to_dict()
```

无风险利率必须来自本地曲线数据，默认配置为 `backtest.risk_free.mode=curve`、`market=CN`、`tenor=2Y`。缺少或过期的曲线数据会抛出 `RiskFreeRateDataError` 并停止指标计算，不允许固定值或 fallback rate。

## 6. 错误处理

- **股票池为空：** 返回 0 收益，不崩溃
- **价格数据缺失：** `get_stock_daily()` 返回空 DataFrame → 该股票被跳过
- **基准数据缺失：** 相对基准指标不计算，收益类指标照常计算
- **无风险曲线缺失/过期：** 抛出 `RiskFreeRateDataError`，停止风险收益指标计算
- **除零保护：** 所有比率计算前检查分母 > 0
- **全局状态污染：** 巴菲特滚动评分器在每次策略评分前重置年度缓存，避免跨策略/跨窗口复用状态

## 7. 测试策略

- **合约测试：** `BaseStrategy.score()` / `get_positions()` 和 Pipeline stage 契约保持稳定
- **PIT 测试：** 在已知未来暴涨的数据上运行回测，验证策略不会提前买入
- **公式测试：** Sortino/Beta/Sharpe、退化收益序列和 NaN 边界由 `tests/test_boundary.py` 覆盖
- **边界测试：** 单日回测、单只股票、负价格、全 NaN NAV
- **回归测试：** 固定随机种子 + 固定数据，回测结果可复现
- **证据测试：** `tests/test_strategy_backtest_evidence.py` 验证强基准和晋级门槛字段完整

## 8. 已知限制 & 未来方向

- **无分钟级回测：** 当前仅支持日频，分钟级需要完全不同的事件驱动架构
- **多资产联合回测独立入口：** 股票/ETF 联合回测在 `scripts/multi_asset_tournament.py` 中实现，未并入主 N 策略锦标赛入口
- **无交易成本模型细化：** 未考虑冲击成本（大单对市场价格的影响）
- **未来：** 在当前 `backtest.benchmark` 单基准配置之外，支持沪深300/中证500/自定义组合等对比篮子
