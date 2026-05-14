---
title: System Architecture (系统架构总览)
created: 2026-05-12
updated: 2026-05-12
type: concept
tags: [architecture, system-overview, extensibility, strategy-registry]
---

# System Architecture

A股量化交易系统架构总览。巴菲特价值投资为决策约束层，钱学森控制论为运行机制层——两者正交不冲突。所有代码在 `~/quant-agent/`，Web 在 8501 端口，日频 cron 在 15:30 CST。

## 设计哲学

```
巴菲特层 (做什么/不做什么)      控制论层 (怎么做)
━━━━━━━━━━━━━━━━━━━━━━━     ━━━━━━━━━━━━━━━━━━━━
能力圈 → 行业白名单           多层递阶 → 任务分层执行
安全边际 → DCF 估值门槛        反馈回路 → 持续改进机制
护城河 → ROE/毛利/D-E 筛选    自适应   → 参数动态调整
不亏钱 → 操作安全底线          前馈     → 预防性检查
长期主义 → 技能沉淀           稳定性   → 硬限制保护
```

- **决策约束层**（`buffett/filters.py`）：定义什么能做、什么不能做——价值观驱动的硬约束
- **运行机制层**（`cybernetics/orchestrator.py`）：在能做的事范围内，怎么做得更好——工程驱动的执行系统
- 两者在**回测反馈回路**交汇：每次行动的成果和教训被记录、沉淀、修正，形成闭环

## 系统分层

```
┌──────────────────────────────────────────────────────────┐
│  Web Dashboard (port 8501)                               │
│  Vue 3 + Pinia + ECharts + Tailwind                      │
│  8 dynamic pages configured from Strategy Registry       │
├──────────────────────────────────────────────────────────┤
│  FastAPI Backend                                         │
│  N route modules + WebSocket + async job queue            │
│  DuckDB Query Engine (:memory: read-only — NEVER locked)  │
│  Strategy Registry → dynamic routing, not hardcoded names│
├──────────────────────────────────────────────────────────┤
│  Execution Layer                                         │
│  compute_signals.py (daily, 15:30 CST cron)              │
│  iterate Strategy Registry → run scorer → save to Parquet │
│  Telegram @buffett0320_bot (signal push)                 │
├──────────────────────────────────────────────────────────┤
│  Strategy Registry (config/settings.yaml → strategies)   │
│  ┌──────────────┬──────────────────┬──────────────────┐  │
│  │ Strategy[0]  │ Strategy[1]      │ ... Strategy[N]  │  │
│  │ name, label  │ name, label      │                  │  │
│  │ scorer_path  │ scorer_path      │  pluggable       │  │
│  │ config_key   │ config_key       │  standard        │  │
│  │ color, icon  │ color, icon      │  interface       │  │
│  └──────────────┴──────────────────┴──────────────────┘  │
├──────────────────────────────────────────────────────────┤
│  Backtest Layer                                          │
│  run_all_strategies.py → iterate Registry → compare all  │
│  N × rolling scorers (no look-ahead bias)                │
│  analytics.py — 15 risk metrics (Sharpe/Sortino/Calmar…) │
├──────────────────────────────────────────────────────────┤
│  Data Layer                                              │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐      │
│  │ AKShare  │  │ Tushare MCP  │  │ Parquet Cache │      │
│  │ OHLCV    │  │ Financials   │  │ 3-tier        │      │
│  │ 同花顺财务│  │ PE/PB/行业   │  │ mem→disk→API  │      │
│  └──────────┘  └──────────────┘  └───────────────┘      │
│  DuckDB: quant_results.duckdb                             │
│    strategy_signals (strategy_name column, not per-table) │
└──────────────────────────────────────────────────────────┘
```

## 策略注册表（可扩展架构）

**目标设计**——新增策略只需在 config 中注册，不改代码：

```yaml
# config/settings.yaml
strategies:
  buffett:
    name: buffett
    label: 巴菲特价值精选
    color: "#06b6d4"
    scorer: backtest.buffett_real_scorer.create_buffett_real_scorer
    compute: scripts.compute_signals.run_buffett
    config_key: buffett           # 对应的 settings 段
    enabled: true
  multifactor:
    name: multifactor
    label: 多因子月度调仓
    color: "#10b981"
    scorer: backtest.run_all_strategies.multifactor_scorer
    compute: scripts.compute_signals.run_multifactor
    config_key: signals.multifactor
    enabled: true
  cybernetic:
    name: cybernetic
    label: 控制论自适应
    color: "#f59e0b"
    scorer: backtest.run_all_strategies.cybernetic_scorer
    compute: scripts.compute_signals.run_cybernetic
    config_key: cybernetic
    enabled: true
```

### 策略接口合约

每个策略模块必须实现：

| 接口 | 签名 | 说明 |
|------|------|------|
| `scorer(sym, series, idx, regime) → float` | 回测评分的标准接口 | 返回 0-100 分 |
| `compute(pool, config) → list[dict]` | 日频扫描的标准接口 | 返回信号列表 |
| 配置段 | `settings.yaml` 中的独立 section | 参数存储 |

### 当前状态（已全部改造）

| 层 | 改造后 |
|----|--------|
| 策略列表 | Strategy Registry 统一注册，`config/settings.yaml` → `strategies` |
| 回测 | `for s in get_enabled_strategies(): run(s)` |
| Web 路由 | 从 registry 动态计算 valid names |
| Web 前端 | Backtest 页同屏叠加所有策略曲线 + 点击高亮，Market 页 `v-if` 显隐控制 |
| 信号存储 | `for s in registry: save(s.name, ...)` |
| 数据库 | `strategy_signals` 表，`strategy_name` 列，无需改 schema |

## 数据流

```
1. 数据采集
   AKShare → stock_zh_a_daily → data/cache/*.parquet (OHLCV)
   AKShare → stock_financial_abstract_ths → data/cache/financials/*.parquet
   Tushare → fina_indicator/daily_basic/margin... → Parquet cache → pandas

2. 策略计算 (compute_signals.py, 每日 15:30)
   for each strategy in Registry:
     scorer(pool, config) → signals → Parquet (data/store/signals/{strategy}.parquet)

3. 信号推送
   DuckDB → 对比昨日 → 变更信号 → Telegram

4. 回测验证 (独立运行)
   for each strategy in Registry:
     scorer × rolling window → 月度调仓 → 绩效报告

5. Web 展示
   FastAPI ← DuckDB(in-memory) + read_parquet() views → Vue 3 SPA (N策略动态渲染)
```

## 关键模块

| 模块 | 文件 | 角色 |
|------|------|------|
| 策略注册表 | `config/settings.yaml` → `strategies` | N策略元数据，唯一真理源 |
| 配置 | `config/settings.yaml` | 全部可调参数，无硬编码 |
| 数据获取 | `data/fetcher.py` | AKShare 3源 fallback + parquet 缓存 |
| 财务数据 | `data/financials.py` | 同花顺 → ROE/毛利/D-E，三层缓存 |
| 股票池 | `data/symbols.py` | 1000只，申万31行业，板块分类 |
| 数据库 | `data/db.py` + `data/results_db.py` | Parquet 存储 + DuckDB 查询引擎 |
| 巴菲特过滤 | `buffett/filters.py` | 三重过滤 + 板块感知 |
| 控制论协调 | `cybernetics/orchestrator.py` | Regime 检测 + 自适应参数 |
| 多因子引擎 | `signals/multifactor.py` | 四维加权打分 |
| 因子 DSL | `signals/factors.py` | qlib-inspired 声明式因子 |
| 回测运行 | `backtest/run_all_strategies.py` | 遍历 Registry，N策略对比 |
| 滚动回测 | `backtest/buffett_real_scorer.py` | 按年滚动，消除前视偏差 |
| 风险分析 | `backtest/analytics.py` | 15 项风险指标 |
| 模拟交易 | `broker/__init__.py` | PaperBroker，T+1，佣金 |
| 日频扫描 | `scripts/compute_signals.py` | Cron 15:30 触发 |
| Web 后端 | `web/api/` | FastAPI + WebSocket |
| Web 前端 | `web/frontend/` | Vue 3 + Pinia + ECharts，动态渲染 |

## 回测对比 (2015-2026, 100只, 示例)

| 策略 | 收益 | Sharpe | MaxDD | 交易 |
|------|------|--------|-------|------|
| 巴菲特真实过滤 | **+37.61%** | 0.05 | -14.1% | 9 |
| 基准(上证) | +24.76% | — | — | — |
| 多因子 | +1.23% | -0.02 | -51.8% | 1208 |
| 控制论 | +0.63% | -0.06 | -34.3% | 842 |

## 关键设计约束

- **策略可插拔**：新增策略 = config 注册 + scorer 实现，不改现有代码
- **Web 动态渲染**：前端从 `/api/strategies` 获取 Registry，动态生成卡片和曲线
- **Schema 不随策略增长**：`strategy_signals` 表用 `strategy_name` 列区分，不创建新表
- **回测通用引擎**：`run_backtest(name, pool, prices, bench, scorer, ...)` 接受任意 scorer，不关心策略类型
- **参数全在 config**：每个策略的阈值/权重独立存放在各自的 `config_key` 段

## 关键决策

- [[duckdb-migration|DuckDB 迁移]] — 列存 + Parquet 原生 + 读写分离
- [[web-architecture|Web 架构]] — Vue 3 SPA + FastAPI，动态渲染
- [[financial-cache|财务三层缓存]] — 内存 → parquet → API
- [[buffett-rolling-backtest|滚动回测]] — 消除前视偏差

## 阶段路线

| Phase | 状态 | 内容 |
|-------|:--:|------|
| 1 分析助手 | ✅ | 数据 + 过滤 + 评分 + Web |
| 2 信号系统 | ✅ | 多策略 + 回测 + 日频 cron + Telegram |
| 2.5 可扩展重构 | ✅ | Strategy Registry + 消除全部硬编码（10文件改造） |
| 3 半自动交易 | 🔜 | PaperBroker → MiniQMT实盘 |

## 已改造文件清单

| 文件 | 改动 |
|------|------|
| `config/settings.yaml` | 新增 `strategies` 注册表段 |
| `data/registry.py` | **新建** — 统一加载/查询接口 |
| `data/results_db.py` | `_strategy_label()` 改为 registry 查找 |
| `backtest/run_all_strategies.py` | 策略列表从硬编码改为遍历 registry |
| `scripts/compute_signals.py` | `--strategy choices` + if-elif 链改为 registry 遍历 |
| `web/api/jobs.py` | if-elif 分发改为 registry 映射派发 |
| `web/api/routes/strategies.py` | `valid` set + `/api/strategies` 返回 registry |
| `web/api/routes/stocks.py` | 硬编码策略名列表改为遍历 registry |
| `web/api/routes/market.py` | `/api/market` 返回 registry 元数据 |
| `web/frontend/src/stores/index.ts` | 新增 `registry` store 字段 |
| `web/frontend/src/views/Backtest.vue` | tab 切换 → N策略同屏叠加曲线 |
| `web/frontend/src/views/Market.vue` | 卡片显隐绑定 registry `enabled` 状态 |

## 相关

- [[buffett-filter]] — 过滤逻辑详解
- [[cybernetics-regime]] — Regime 检测
- [[multifactor-scoring]] — 多因子引擎
- [[strategy-evolution]] — 策略迭代历史
- [[dcf-valuation]] — DCF 估值方法
- SCHEMA.md — Wiki 组织结构
