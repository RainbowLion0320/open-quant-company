# Spec: 回测引擎 (Backtest Engine)

> 版本: 1.0 | 日期: 2026-05-21 | 关联: [PRD](../PRD.md) [Signal System](02-signal-system.md) [Execution Layer](04-execution-layer.md)

## 1. 概述

回测引擎是策略验证的核心——在历史数据上模拟策略执行，输出风险收益指标。支持 N 策略同时跑对比（锦标赛模式），严格 PIT（Point-in-Time）无前视偏差。

**设计原则：**
- **PIT 零容忍** — 任何前视偏差都是 bug，不是 feature
- **策略可插拔** — `backtest/strategies/` 下每个策略独立文件
- **自研非 Backtrader** — 需要 PIT 特征存储和锦标赛对比，Backtrader 不满足

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
│ 动量+等权    │ │ LightGBM    │ │ _scorer.py  │ │ 可插拔流水线 │
│ 基准策略     │ │ 月度调仓     │ │ 滚动PIT评分  │ │ 自定义组合   │
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
4. 扣除交易成本（印花税 0.1% + 佣金 0.03% + 滑点 0.1%）

**锦标赛模式：** 同一时间区间内运行所有已注册策略，输出对比排名表。

**PIT 安全保障：**
- 评分只使用调仓日之前的数据
- Regime 检测用 `build_monthly_regime()` — 使用上月末收盘价判断当月 regime（`monthly.values[i-1]`）
- 巴菲特评分用滚动窗口逐年评估，不跨年引用

### 2.2 策略基类 (strategies/base.py)

**DefaultStrategy：** 等权动量策略，作为基准对比。
- 每月选择动量最强的前 N 只
- 等权分配资金
- 100 股整数倍约束

### 2.3 ML 策略 (strategies/ml_strategy.py)

- 每月从 PIT 特征切片加载特征
- LightGBM 预测未来 20 日收益概率
- 按预测概率排序选 Top-N

### 2.4 可插拔流水线 (pipeline.py)

```python
Pipeline([
    DataStep("load_prices"),
    StrategyStep("compute_signals"),
    SelectionStep("top_n", n=10),
    RiskStep("max_position_20pct"),
    ExecutionStep("equal_weight"),
])
```

### 2.5 风险分析 (analytics.py)

**15 项指标：**

| 类别 | 指标 | 公式/说明 |
|------|------|----------|
| 收益 | 总收益率 | (NAV[-1]/NAV[0] - 1) × 100% |
| 收益 | 年化收益率 (CAGR) | (NAV[-1]/NAV[0])^(252/n) - 1 |
| 风险 | 年化波动率 | std(daily_returns) × √252 |
| 风险 | 下行风险 | RMS(min(0, daily_returns)) × √252 |
| 风险收益 | Sharpe Ratio | (CAGR - Rf) / 年化波动率 |
| 风险收益 | Sortino Ratio | (CAGR - Rf) / 下行风险 |
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
    RiskAnalytics.compute(nav, benchmark)
             │
             ▼
    FullReport: {metrics, trades, monthly_returns}
             │
             ▼
    data/tournament/{date}.json
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 回测框架 | 自研（非 Backtrader） | 需要 PIT 特征存储 + 多策略锦标赛，Backtrader 不支持 |
| Regime 检测 | 月度 K 线 + 滞后一期 | 避免前视偏差（不能用当月数据判断当月 regime） |
| 调仓频率 | 月初第一个交易日 | 日频调仓成本过高，月度再平衡是行业惯例 |
| 基准选择 | 上证综指 (sh000001) | 全市场代表性最强 |
| 交易约束 | 100 股整数倍 + 手续费 | 模拟真实 A 股交易规则 |
| 巴菲特评分 | 滚动窗口逐年评估 | 避免全局数据泄露 |

## 5. 接口合约

### 策略接口

```python
class Strategy(ABC):
    @abstractmethod
    def generate_signals(
        self,
        prices: pd.DataFrame,     # N stocks × T days
        date: pd.Timestamp,
        holdings: dict,           # current positions
        cash: float,
    ) -> list[Signal]:            # buy/sell signals
        ...

@dataclass
class Signal:
    symbol: str
    action: str       # "buy" | "sell"
    weight: float     # 0.0 ~ 1.0
    reason: str = ""
```

### 分析接口

```python
from backtest.analytics import RiskAnalytics, FullReport

analytics = RiskAnalytics(nav_series, benchmark_series, risk_free_rate=0.02)
metrics: dict = analytics.compute_all()
report = FullReport(metrics, trades, monthly_returns)
```

## 6. 错误处理

- **股票池为空：** 返回 0 收益，不崩溃
- **价格数据缺失：** `get_stock_daily()` 返回空 DataFrame → 该股票被跳过
- **基准数据缺失：** Alpha/Beta/IR 返回 NaN，收益类指标照常计算
- **除零保护：** 所有比率计算前检查分母 > 0
- **全局状态污染：** 巴菲特滚动评分器在每次策略评分前重置年度缓存，避免跨策略/跨窗口复用状态

## 7. 测试策略

- **合约测试：** 所有策略的 `generate_signals()` 返回 `list[Signal]` 类型
- **PIT 测试：** 在已知未来暴涨的数据上运行回测，验证策略不会提前买入
- **公式测试：** Sortino/Beta/Sharpe 计算结果与 `empyrical` 库对比（误差 < 1e-6）
- **边界测试：** 单日回测、单只股票、负价格、全 NaN NAV
- **回归测试：** 固定随机种子 + 固定数据，回测结果可复现

## 8. 已知限制 & 未来方向

- **无分钟级回测：** 当前仅支持日频，分钟级需要完全不同的事件驱动架构
- **无多资产联合回测：** 股票/ETF 联合回测在 `multi_asset_tournament.py` 中独立实现，未集成到主回测引擎
- **无交易成本模型细化：** 未考虑冲击成本（大单对市场价格的影响）
- **未来：** 支持自定义基准（沪深300/中证500/自定义组合）
