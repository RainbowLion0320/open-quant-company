# PortfolioTarget 流水线 — 设计文档

> 日期: 2026-05-22
> 来源: P1-6 架构边界升级
> 状态: 已归档；当前实现状态以代码和验收矩阵为准

## 目标

将策略(Alpha)→组合构建(Portfolio)→风控(Risk)→执行(Execution)的职责分离，
让回测和 paper trading 共享同一套流水线，消除当前两套独立代码路径。

## 设计决策

| 决策 | 选择 |
|------|------|
| 策略输出形态 | AlphaSignal（方向+置信度+理由），不输出 buy/hold |
| 组合构建复杂度 | 一步到位：等权 + 波动率倒数加权两种方法 |
| 调仓触发 | 混合模式：配置驱动的标准调度器 + 策略可覆写自定义触发 |

## 架构

```
策略(Alpha) → 组合构建(Portfolio) → 风控(Risk) → 执行(Execution)
                                                     ↓
                                         PaperBroker / 回测引擎
```

回测和 paper trading 共享从 Alpha → OrderIntent 的完整流水线，只在最终执行层分叉。

## 流水线 4 阶段

### Stage 1: AlphaModel — 策略评分

- 输入: universe list, prices, regime, date
- 输出: list[AlphaSignal]
- 策略的 score() 改名为 generate_alpha()，返回 AlphaSignal 列表
- 策略不再标记 buy/hold — 只输出方向 + 置信度

### Stage 2: PortfolioConstructor — 组合构建

- 输入: list[AlphaSignal], 当前持仓, 可用资金, prices
- 输出: list[PortfolioTarget]
- EqualWeightConstructor: Top-N 等权
- InverseVolatilityConstructor: 波动率倒数加权
- 从这一层开始回测和 paper 走同一代码

### Stage 3: RiskAdjuster — 风控调整

- 输入: list[PortfolioTarget], 账户状态
- 输出: list[PortfolioTarget] (调整后)
- 整合 broker/risk.py 的 5 条规则
- 超标目标缩减权重或移除

### Stage 4: ExecutionRouter — 执行分发

- 输入: list[PortfolioTarget]
- 输出: list[OrderIntent] → 提交给 Broker
- BacktestExecutor (回测模拟撮合) / PaperBroker.submit_order()

## 核心数据类型

```python
AlphaSignal     # symbol, direction, confidence(0-1), score(0-100),
                # horizon_days, reason, strategy, timestamp

PortfolioTarget # symbol, target_weight, target_shares, current_weight,
                # current_shares, delta_shares, reason

OrderIntent     # symbol, side, shares, price, urgency(market/limit),
                # max_slippage, strategy, portfolio_target_ref

FillResult      # order_intent, filled_shares, fill_price, commission,
                # slippage, status(filled/partial/rejected), timestamp
```

## 调仓调度器

- RebalanceConfig 持有 schedule / drift_threshold / min_overlap_pct
- RebalanceScheduler.should_rebalance() 实现所有标准调度逻辑
- 策略通过 rebalance_trigger(date, regime, holdings) 追加自定义条件
- 巴菲特年报季触发: month in (4,5) and year != last_rebalance_year

## 改造范围

| 文件 | 变更 |
|------|------|
| 新建 `pipeline/types.py` | AlphaSignal, PortfolioTarget, OrderIntent, FillResult |
| 新建 `pipeline/alpha.py` | AlphaModel 基类，4 策略适配器 |
| 新建 `pipeline/portfolio.py` | PortfolioConstructor 基类, EqualWeight, InverseVolatility |
| 新建 `pipeline/risk.py` | RiskAdjuster, 整合 broker/risk.py |
| 新建 `pipeline/execution.py` | ExecutionRouter, BacktestExecutor |
| 新建 `pipeline/scheduler.py` | RebalanceScheduler, RebalanceConfig |
| 修改 `backtest/run_all_strategies.py` | 核心循环替换为流水线调用 |
| 修改 `scripts/execute_paper_trades.py` | 手动下单替换为流水线调用 |
| 修改 `signals/selection.py` | 移除 buy/hold, 改为 AlphaSignal 转换 |
| 不修改 `broker/` | PaperBroker 保持作为执行层消费方 |

## 不做

- 不重写 PaperBroker
- 不引入实时事件总线（日频不需要）
- 不引入订单状态机（P1-7）
- 不改 Web API（signal parquet + portfolio API 结构不变）

## 测试策略

- 合约测试: AlphaSignal → PortfolioTarget → OrderIntent 类型转换正确性
- 等权 vs 波动率倒数加权：同一输入产生不同权重分配
- 调仓调度器: monthly/weekly/regime_change/drift 四种模式的行为验证
- 风控调整: 单票超限被缩减、总敞口超限被缩减
- 回测和 paper 共享流水线: 同一信号源在两路径产出相同持仓
