---
title: Paper Trading System (模拟交易系统)
created: 2026-05-17
updated: 2026-05-17
type: concept
tags: [paper-trading, broker, persistence, portfolio, execution]
---

# Paper Trading System

日频模拟交易系统。信号产出 → 次日模拟成交 → Parquet 持久化 → Web 展示，全链路零外部依赖。

## 设计原则

- **不需要盘中快照**：日频低频交易，用收盘价模拟次日开盘价即可
- **不依赖外部平台**：不用聚宽/QMT/Futu，自己用 PaperBroker 本地撮合
- **状态持久化**：Parquet 存储，服务器重启不丢持仓
- **现有架构嵌入**：复用 PaperBroker + RiskManager + AKShare 行情

## 核心流程

```
15:30 cron → compute_signals.py
                │
                ▼
        scripts/execute_paper_trades.py
        ├── 1. 从 state.parquet 恢复 PaperBroker 状态
        ├── 2. 读取 signals/{strategy}.parquet 最新信号
        ├── 3. AKShare 获取收盘价 → broker.set_prices()
        ├── 4. broker.submit_order() → RiskManager 预检
        ├── 5. append_nav() → nav.parquet (权益快照)
        ├── 6. append_trade() → trades.parquet (交易记录)
        └── 7. save_state() → state.parquet (持仓/现金/权益)
                │
                ▼
        Web API ← Parquet → Portfolio.vue
```

## 组件

### broker/persistence.py — 状态持久化

PaperBroker 所有状态序列化到 `var/store/paper/`：

| 文件 | 内容 | 模式 |
|------|------|------|
| `state.parquet` | 现金 + 持仓 dict + peak_equity | 覆盖写入 |
| `nav.parquet` | 每日净值: date/total_asset/cash/market_value | 追加 |
| `trades.parquet` | 交易记录: date/code/side/price/volume/amount/strategy | 追加 |

`load_state()` / `save_state()` 负责序列化。持仓 dict 以 JSON 字符串存入 Parquet 单列。

### scripts/execute_paper_trades.py — 日频执行

CLI 入口，支持：

```bash
# 初始化账户
python scripts/execute_paper_trades.py --setup --init-cash 1000000

# 执行当日 (限制笔数, 测试用)
python scripts/execute_paper_trades.py --limit 5

# 历史回放 (构建完整 NAV)
python scripts/execute_paper_trades.py --replay 2025-01-01

# 仅查看信号, 不交易
python scripts/execute_paper_trades.py --dry-run
```

信号读取：只遍历 `paper_trading.strategies` 配置内且策略注册表允许 paper 执行的策略，从 `var/store/signals/{strategy}.parquet` 取最新 `computed_at` 批次，并按 `paper_trading.max_signal_age_days` 跳过过期信号。最终过滤 `buy`/`strong_buy` → 每只买 100 股。

### Web API — /api/portfolio/*

| 端点 | 功能 |
|------|------|
| `GET /positions` | 当前持仓 (从 Parquet 恢复) |
| `GET /balance` | 资金概览 |
| `GET /nav` | NAV 历史 (权益曲线数据) |
| `GET /trades?limit=N` | 交易历史 |
| `GET /summary` | 综合摘要: 资金+收益+peak_equity |
| `POST /order` | 手动下单 (测试) |
| `POST /refresh` | 强制从 Parquet 刷新状态 |

`get_broker()` 在首次调用时从 `state.parquet` 恢复 PaperBroker，确保服务器重启后持仓不丢。

### Web UI — Portfolio.vue

模拟交易页面 `/portfolio`，5 项展示：

- **资金卡片 ×5**：总资产/可用现金/持仓市值/总收益/最高权益
- **权益曲线**：ECharts 折线图，青色填充，本金标记线
- **持仓表**：代码/名称/数量/成本/现价/市值/盈亏/比例
- **交易记录**：日期/代码/方向/价格/数量/金额/策略来源
- **手动下单**：代码/方向/数量 → submit (测试用)

「刷新状态」→ POST `/refresh` → 从 Parquet 重载。「载入数据」→ 并请求所有端点。

## 风控集成

每次买入前调用 RiskManager 5 规则预检：
- 单只仓位上限 (25%)
- 总敞口上限 (80%)
- 单日最大下单次数 (50)
- 最大回撤熔断 (-15%)
- 单笔最大金额 (¥500K)

T+1 限制由 PaperBroker 原生支持。

## 配置

```yaml
# config/settings.yaml → paper_trading
paper_trading:
  enabled: true
  initial_cash: 1000000
  commission_rate: 0.00081    # 完整 A 股买卖成本
  t_plus_1: true
  risk_enabled: true
  store_dir: var/store/paper
  strategies: [buffett, multifactor, cybernetic, ml_lgbm]
  max_signal_age_days: 2
  execution_price: close
  auto_execute: false          # cron 自动执行开关
```

## 关键文件

| 文件 | 角色 |
|------|------|
| `broker/persistence.py` | PaperBroker 状态序列化/反序列化 |
| `scripts/execute_paper_trades.py` | 日频执行脚本 (初始化/执行/回放/dry-run) |
| `web/api/routes/portfolio.py` | Web API 端点 (nav/trades/summary/refresh) |
| `web/frontend/src/views/Portfolio.vue` | 前端页面 (NAV 曲线+持仓+交易记录) |
| `broker/{base,paper_core,paper_orders}.py` | PaperBroker ABC、核心状态和下单/T+1逻辑 |
| `broker/risk.py` | RiskManager (5 规则预检) |
| `config/settings.yaml` | 模拟交易配置段 |

## See Also

- [[system-architecture]] — 系统分层 + 关键模块表
- [[web-architecture]] — Web 7 个一级入口结构
- [[buffett-filter]] — 巴菲特信号来源
- [[ml-pipeline]] — ML 信号来源
