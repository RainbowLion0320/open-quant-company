# Spec: 执行层 (Execution Layer)

> 版本: 1.0 | 日期: 2026-05-21 | 关联: [[PRD.md]] [[03-backtest-engine.md]] [[06-multi-asset.md]]

## 1. 概述

执行层负责将信号转化为模拟交易——PaperBroker 本地模拟撮合、RiskManager 5 规则风控、Persistence 层 Parquet 持久化状态和净值。Cron 日频调度：15:30 扫描信号，09:30 执行模拟交易。

**设计原则：**
- **Facade Pattern** — Broker 抽象接口 → PaperBroker (当前) / MiniQMTBroker (Phase 5 实盘)
- **配置驱动风控** — 规则在 `settings.yaml` 中可开关、可调参
- **状态持久化** — 所有持仓/订单/NAV 写入 Parquet，重启不丢失

## 2. 组件架构

```
┌─────────────────────────────────────────────────────┐
│                  config/settings.yaml                 │
│          risk_control: 5 rules + circuit_breaker      │
│          broker: commission/slippage/cron              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                   PaperBroker                         │
│   submit_order() → RiskManager.check() → 模拟撮合     │
│   get_positions() / get_balance() / get_orders()      │
│   record_order() / cancel_order()                     │
│   update_positions(prices) — 日末盯市                  │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────────────┐
│  risk.py    │ │exchange   │ │ persistence.py      │
│ 5 规则风控   │ │ 多资产交易所│ │ Parquet 状态持久化   │
│ 熔断机制    │ │ 手续费计算 │ │ trades/NAV/state    │
└─────────────┘ └───────────┘ └────────────────────┘
```

### 2.1 PaperBroker — 模拟券商

**核心接口 (ABC)：**

```python
class Broker(ABC):
    @abstractmethod
    def submit_order(self, symbol, price, volume, side) -> Order
    @abstractmethod
    def cancel_order(self, order_id) -> bool
    @abstractmethod
    def get_positions(self) -> dict[str, Position]
    @abstractmethod
    def get_balance(self) -> Account
    @abstractmethod
    def get_orders(self) -> list[Order]
```

**模拟撮合逻辑：**
- 买入：以当日收盘价成交（日频无日内价格）
- 卖出：同价成交
- 约束：100 股整数倍（A 股规则）
- 成本：印花税 0.1%（卖出）+ 佣金 0.03%（买卖）+ 滑点 0.1%

**订单生命周期：** `PENDING` → `FILLED`（成交）/ `REJECTED`（风控拒绝）/ `CANCELLED`（撤单）

### 2.2 RiskManager — 5 规则风控

| # | 规则 | 默认阈值 | 说明 |
|---|------|---------|------|
| 1 | `MaxSinglePositionRule` | 单只 ≤ 25% 总权益 | 计算持仓+拟购后的比例 |
| 2 | `MaxTotalExposureRule` | 总敞口 ≤ 80% | 预留 20% 现金缓冲 |
| 3 | `MaxOrdersPerDayRule` | 每日 ≤ 20 笔 | 防止过度交易 |
| 4 | `DrawdownCircuitBreaker` | 回撤 > 20% 熔断 | 熔断后所有买单自动拒绝 |
| 5 | `MaxSingleOrderAmountRule` | 单笔 ≤ 10% 总资金 | 分散入场，避免冲击 |

**熔断机制：**
- 触发条件：`1 - NAV/NAV_peak > circuit_breaker_threshold`（默认 0.20）
- 熔断后行为：所有买单自动拒绝，只允许卖出
- 恢复条件：需手动重置（`reset_circuit_breaker()`）

**可插拔设计：** 每个规则继承 `RiskRule` 基类，实现 `check(context) → RiskCheckResult`。新增规则只需创建子类并注册到配置。

### 2.3 Exchange — 多资产交易所

```python
class AShareExchange:
    commission_rate: 0.0003   # 万三
    stamp_tax: 0.001          # 千一 (仅卖出)
    min_lot: 100              # 1手=100股
    slippage: 0.001           # 千一滑点

class ETFExchange:
    commission_rate: 0.0001   # 万一
    stamp_tax: 0.0            # ETF 免印花税
    min_lot: 100
```

`calc_cost(price, volume, side)` → 统一计算含印花税+佣金+滑点的总成本。

### 2.4 Persistence — 状态持久化

三张 Parquet 表：

| 表 | 路径 | Schema |
|----|------|--------|
| `trades` | `data/store/paper/trades.parquet` | order_id, symbol, side, price, volume, cost, timestamp |
| `nav` | `data/store/paper/nav.parquet` | date, nav, cash, market_value, daily_return |
| `state` | `data/store/paper/state.parquet` | symbol, shares, avg_cost, last_price, market_value |

**保存时机：**
- 每次 `submit_order()` 成交后 → 更新 trades + state
- 每日收盘后 → 追加 NAV 记录
- `update_positions(prices)` → 更新 state 中 last_price 和 market_value

### 2.5 Cron 调度

| 脚本 | 时间 | 功能 |
|------|------|------|
| `scripts/compute_signals.py` | 交易日 15:30 | 日频信号扫描 |
| `scripts/execute_paper_trades.py` | 交易日 09:30 | 模拟交易执行 |
| `scripts/weekly_retrain.py` | 周六 08:00 | ML 模型重训 |
| `scripts/cron_fetch_daily.py` | 交易日 16:00 | 日常数据拉取 |
| `scripts/cron_fetch_slow.py` | 每日 02:00 | 限流数据分批填充 |

所有 Cron 脚本集成 `cron_logger`，输出到 `data/store/_cron_log/{script}.jsonl`。

## 3. 数据流

```
15:30 — compute_signals.py
  data/store/signals/*.parquet (信号扫描)
          │
          ▼
09:30 — execute_paper_trades.py
  ┌──────────────────────────────┐
  │  读取信号 → 生成订单           │
  │  for signal in buy_signals:  │
  │    order = Order(symbol, ...) │
  │    broker.submit_order(order) │
  └────────────┬─────────────────┘
               │
               ▼
  RiskManager.check_order(order, portfolio)
               │
       ┌───────┴───────┐
       ▼               ▼
    passed          rejected
       │               │
       ▼               ▼
  模拟撮合成交      记录拒绝原因
       │
       ▼
  Persistence.save_trade() + update_state()
       │
       ▼
  Persistence.save_nav(date, nav)
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| Broker 抽象接口 | Facade Pattern | Phase 5 对接 MiniQMT 时只需实现新 Broker，策略代码零改动 |
| 风控预检 (pre-trade) | 下单前执行，非下单后 | 阻止违规订单进入执行队列 |
| 熔断只阻止买入 | 允许卖出不允许买入 | 熔断期间应允许减仓止损 |
| Parquet 持久化 | 非 SQLite | 与数据层统一格式，DuckDB 可直接查询 |
| 日末收盘价成交 | 非日内 VWAP | 日频策略不需要精细成交价模型 |

## 5. 接口合约

### Broker 接口

```python
broker = PaperBroker(initial_cash=1_000_000)

# 下单 — 自动过风控
order = broker.submit_order("000001", price=12.5, volume=100, side="buy")
# order.status ∈ {"filled", "rejected"}

# 查询
broker.get_positions()    → {"000001": Position(shares=100, avg_cost=12.5, ...)}
broker.get_balance()      → Account(cash=987500, market_value=1250, ...)
broker.get_orders()       → [Order(...), ...]
broker.get_nav_history()  → pd.DataFrame
```

### RiskManager 接口

```python
rm = RiskManager(config)
result: RiskCheckResult = rm.check_order(symbol, amount, portfolio)
# result.passed: bool, result.reason: str

# 熔断
rm.is_circuit_breaker_triggered() → bool
rm.reset_circuit_breaker()
```

## 6. 错误处理

- **风控拒绝：** 订单状态设为 REJECTED，记录拒绝原因到 order.reason
- **资金不足：** 订单 REJECTED，不影响现有持仓
- **价格缺失：** `update_positions()` 保持上次已知价格，不抛异常
- **持仓状态文件丢失：** 从零开始（空持仓+初始资金），不崩溃
- **并发写 trades：** 通过 DataHub.append_parquet() 的 fcntl 锁保护

## 7. 测试策略

- **合约测试：** PaperBroker 实现 Broker ABC 所有抽象方法
- **风控规则测试：** 每条规则独立测试（单只超限/总敞口超限/回撤熔断/单笔超限/日频超限）
- **状态持久化测试：** 创建 Broker → 下单 → 保存 → 重新加载 → 验证状态一致
- **NAV 计算测试：** 手工计算 vs PaperBroker 输出对比
- **边界测试：** 零资金、全持仓卖出、熔断后恢复、空信号执行

## 8. 已知限制 & 未来方向

- **无日内成交模型：** 全部以收盘价成交，未考虑日内价格波动
- **无部分成交：** 模拟全额成交，实盘中限价单可能部分成交
- **风控无组合层面：** 未计算组合 VaR/CVaR 作为动态风控阈值
- **未来 Phase 5：** 对接 MiniQMT 实盘接口，增加人工确认环节（弹窗确认 → 下单）
