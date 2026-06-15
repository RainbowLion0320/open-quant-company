# Spec: 执行层 (Execution Layer)

> 版本: 1.2 | 日期: 2026-06-14 | 关联: [PRD](../product/prd.md) [Backtest Engine](03-backtest-engine.md) [Multi-Asset](06-multi-asset.md) [Agent Company OS](07-agent-company-os.md)

## 1. 概述

执行层负责将信号转化为模拟交易——PaperBroker 本地模拟撮合、RiskManager 5 规则风控、Persistence 层 Parquet 持久化状态和净值。Agent Company OS 可生成 PaperBroker 订单预览和审批卡，并且只能在 CEO 批准后通过专用 submit 路径重新预览、重新风控、写入运行和 reconciliation evidence 后提交 paper 订单。Cron 日频调度：15:30 扫描信号，09:30 执行模拟交易。

**设计原则：**
- **Facade Pattern** — Broker 抽象接口 → PaperBroker (当前模拟交易) / MiniQMT/QMT readiness + order preview (当前只读、不提交) / MiniQMT/QMT live adapter (后续实盘提交)
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
│   submit_order() → RiskManager.check_order() → 模拟撮合│
│   get_positions() / get_balance() / get_orders()      │
│   cancel_order() / get_today_trades() / end_of_day()  │
│   set_prices(prices) — 刷新行情；end_of_day() 盯市      │
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
    def submit_order(self, code: str, price: float, volume: int, side: str) -> str
    @abstractmethod
    def cancel_order(self, order_id) -> bool
    @abstractmethod
    def get_positions(self) -> list[Position]
    @abstractmethod
    def get_balance(self) -> Account
    @abstractmethod
    def get_orders(self) -> list[Order]
    @abstractmethod
    def get_today_trades(self) -> list[Order]
```

**模拟撮合逻辑：**
- 买入：以当日收盘价成交（日频无日内价格）
- 卖出：同价成交
- 约束：100 股整数倍（A 股规则）
- 成本：由 `broker/exchange.py` 的资产费率模型和 `trading.exchange.*` 配置驱动

**Agent preview / submit 逻辑：**
- `PaperBroker.preview_order(intent)` 只读取当前现金、持仓、价格和 RiskManager 状态，不创建订单、不改现金、不写 broker ledger。
- 预览输出 `submitted=false`、`approval_required=true`、`risk_gate`、费用估算、现金影响和持仓影响。
- `AgentRuntime.propose_paper_order()` 只在 preview 通过后创建 `paper_order` approval card 和 evidence artifact。
- `AgentRuntime.submit_paper_order_action()` 只接受已批准的 `paper_order` action，提交前必须重新运行 preview/risk gate；如果现金、持仓、价格或 evidence 已变化导致 preview 不通过，写 blocked run 和 reconciliation evidence，但不调用 `submit_order()`。
- 成功提交会写 `AgentRun.tool_name=paper.paper_order.submit`、`var/artifacts/agent/paper_reconciliation/` evidence，并通过当前 `ASTROLABE_VAR` 下的 PaperBroker persistence 写入 state/trades/NAV。

**订单生命周期：** `PENDING` → `FILLED`（成交）/ `REJECTED`（风控拒绝）/ `CANCELLED`（撤单）

### 2.2 RiskManager — 5 规则风控

| # | 规则 | 默认阈值 | 说明 |
|---|------|---------|------|
| 1 | `MaxSinglePositionRule` | 单只 ≤ 25% 总权益 | 计算持仓+拟购后的比例 |
| 2 | `MaxTotalExposureRule` | 总敞口 ≤ 80% | 预留 20% 现金缓冲 |
| 3 | `MaxOrdersPerDayRule` | 每日 ≤ 20 笔 | 防止过度交易 |
| 4 | `DrawdownCircuitBreaker` | 回撤超过 `max_drawdown_pct` | 回撤规则不通过时拒绝买单 |
| 5 | `MaxSingleOrderAmountRule` | 单笔金额 ≤ 配置上限 | 分散入场，避免冲击 |

**熔断机制：**
- 触发条件：`portfolio.drawdown_pct <= max_drawdown_pct`（当前默认 `-0.15`）
- 行为：作为 `RiskRule` 的一次性下单检查结果返回，不维护独立 latch 状态
- 恢复：由组合净值和 `peak_equity` 更新自然恢复；当前没有 `reset_circuit_breaker()` 公共接口

**可插拔设计：** 每个规则继承 `RiskRule` 基类，实现 `check(context) → RiskCheckResult`。新增规则只需创建子类并注册到配置。

### 2.3 Exchange — 多资产交易所

```python
class AShareExchange:
    commission: 0.00025       # 配置默认，最低佣金 5 元
    stamp_tax: 0.0005         # 卖出单向
    transfer_fee: 0.00001
    lot_size: 100             # 1手=100股

class ETFExchange:
    commission: 0.00005       # 配置默认，最低佣金 0.1 元
    lot_size: 100

class BondExchange:
    commission: 0.00002       # 配置默认，最低佣金 0.1 元
```

`calc_cost(price, shares, side)` → 统一计算当前资产的佣金、印花税和过户费等成本；费率从 `trading.exchange.*` 读取，可通过构造参数覆盖。

### 2.4 Persistence — 状态持久化

三张 Parquet 表：

| 表 | 路径 | Schema |
|----|------|--------|
| `trades` | `var/store/paper/trades.parquet` | date, code, name, side, price, volume, amount, strategy |
| `nav` | `var/store/paper/nav.parquet` | date, total_asset, cash, market_value |
| `state` | `var/store/paper/state.parquet` | cash, frozen_cash, peak_equity, positions(JSON), order_counter, updated_at |

**保存时机：**
- 每次 `submit_order()` 成交后 → 更新 trades + state
- 每日收盘后 → 追加 NAV 记录
- `set_prices(prices)` 刷新行情；`end_of_day()` 更新持仓可卖数量、峰值权益和 NAV 快照

### 2.5 Cron 调度

| 脚本 | 时间 | 功能 |
|------|------|------|
| `scripts/compute_signals.py` | 交易日 15:30 | 日频信号扫描 |
| `scripts/execute_paper_trades.py` | 交易日 09:30 | 模拟交易执行 |
| `scripts/weekly_retrain.py` | 周六 08:00 | ML 模型重训 |
| `scripts/cron_fetch_daily.py` | 交易日 16:00 | 日常数据拉取 |
| `scripts/cron_fetch_slow.py` | 每日 02:00 | 限流数据分批填充 |

所有 Cron 脚本集成 `cron_logger`，输出到 `var/store/_cron_log/{script}.jsonl`。

## 3. 数据流

```
15:30 — compute_signals.py
  var/store/signals/*.parquet (信号扫描)
          │
          ▼
09:30 — execute_paper_trades.py
  ┌──────────────────────────────┐
  │  读取信号 → 生成订单           │
  │  for signal in buy_signals:  │
  │    broker.set_prices(...)     │
  │    broker.submit_order(...)   │
  └────────────┬─────────────────┘
               │
               ▼
  RiskManager.check_order(code, amount, portfolio)
               │
       ┌───────┴───────┐
       ▼               ▼
    passed          rejected
       │               │
       ▼               ▼
  模拟撮合成交      记录拒绝原因
       │
       ▼
  append_trade() + save_state()
       │
       ▼
  append_nav(date, total_asset, cash, market_value)
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| Broker 抽象接口 | Facade Pattern | PaperBroker 与 MiniQMT/QMT live adapter 边界分离；当前只实现 default-disabled readiness probe 和不提交订单的 preview gate，实盘提交仍需独立 adapter |
| 风控预检 (pre-trade) | 下单前执行，非下单后 | 阻止违规订单进入执行队列 |
| 熔断只阻止买入 | 允许卖出不允许买入 | 熔断期间应允许减仓止损 |
| Parquet 持久化 | 非 SQLite | 与数据层统一格式，DuckDB 可直接查询 |
| 日末收盘价成交 | 非日内 VWAP | 日频策略不需要精细成交价模型 |

## 5. 接口合约

### Broker 接口

```python
broker = PaperBroker(initial_cash=1_000_000)

# 下单 — 自动过风控
order_id_or_reason = broker.submit_order("000001", price=12.5, volume=100, side="buy")
# 成功返回 PAPER_* order id；拒绝返回可读原因字符串

# 查询
broker.get_positions()    → [Position(code="000001", volume=100, avg_cost=12.5, ...)]
broker.get_balance()      → Account(cash=987500, market_value=1250, ...)
broker.get_orders()       → [Order(...), ...]
broker.get_today_trades() → [Order(...), ...]

# NAV 由 API 或持久化层读取
load_nav() / GET /api/portfolio/nav → pd.DataFrame / JSON
```

### RiskManager 接口

```python
rm = RiskManager(config)
passed, results = rm.check_order(code, amount, portfolio)
# passed: bool
# results: list[RiskCheckResult]，每条包含 rule / passed / reason / severity
rm.record_order(order_date)
rm.check_portfolio(portfolio) → list[RiskCheckResult]
```

## 6. 错误处理

- **风控拒绝：** `submit_order()` 返回拒绝原因，订单簿保留 REJECTED 订单和状态历史
- **资金不足：** 订单 REJECTED，不影响现有持仓
- **价格缺失：** `set_prices()` 可只更新有报价的标的，持仓保留上次 `current_price`
- **持仓状态文件丢失：** 从零开始（空持仓+初始资金），不崩溃
- **并发写 trades：** 通过 DataHub.append_parquet() 的 fcntl 锁保护

## 7. 测试策略

- **合约测试：** PaperBroker 实现 Broker ABC 所有抽象方法
- **风控规则测试：** 每条规则独立测试（单只超限/总敞口超限/回撤熔断/单笔超限/日频超限）
- **状态持久化测试：** 创建 Broker → 下单 → 保存 → 重新加载 → 验证状态一致
- **NAV 计算测试：** 手工计算 vs PaperBroker 输出对比
- **边界测试：** 零资金、全持仓卖出、回撤规则拒绝买单、空信号执行

## 8. 已知限制 & 未来方向

- **无日内成交模型：** 全部以收盘价成交，未考虑日内价格波动
- **无部分成交：** 模拟全额成交，实盘中限价单可能部分成交
- **风控无组合层面：** 未计算组合 VaR/CVaR 作为动态风控阈值
- **MiniQMT/QMT readiness + preview foundation：** `broker.live.qmt.MiniQmtLiveBroker` 只读探测 default-disabled / missing SDK / login / permission / kill-switch 状态，`paper_fallback=false`；`preview_order()` 只计算 intent、fees、现金/持仓影响和扩展 preview risk gate（现金、单票集中度、总敞口、日订单数、可交易性、数据新鲜度、券商账户一致性），始终 `submitted=false`
- **Agent paper execution foundation：** `PaperBroker.preview_order()`、`AgentRuntime.propose_paper_order()` 和 `AgentRuntime.submit_paper_order_action()` 已形成 preview → approval → re-preview → submit/reconciliation 的受控路径；CEO Office 可显示 paper preview/risk 摘要并提交已批准 action，仍需要更完整的对账视图和已提交订单取消语义。
- **未来方向：** 完成 MiniQMT/QMT drawdown/portfolio VaR 等更深风控、CEO approval、submission、reconciliation 和 kill switch 操作；不得回退到 PaperBroker
