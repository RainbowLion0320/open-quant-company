---
title: System Architecture (系统架构总览)
created: 2026-05-12
updated: 2026-05-16
type: concept
tags: [architecture, system-overview, extensibility, strategy-registry, ML, Factor-DSL, PIT, LightGBM, LLM]
---

# System Architecture

A股量化交易系统架构总览。巴菲特价值投资为决策约束层，钱学森控制论为运行机制层——两者正交不冲突。所有代码在 `~/quant-agent/`，Web 在 8501 端口，日频 cron 在 15:30 CST。

**当前版本: v4.0** — 从手调规则演进到 AI/ML 驱动的自动化 R&D 框架。

## 设计哲学：三层正交架构

三层正交不是三个策略的分工——它穿透所有组件，定义系统在任何时刻的运作方式。

```
认知层 (系统如何感知与进化)   约束层 (系统边界与安全)     执行层 (系统如何运行)
━━━━━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━━
Data Registry → 28维度自感知  RiskManager → 5规则预检    Cron 15:30 → 日频扫描
Factor DSL → 声明式计算       Data Cleaner → 6规则清洗    Tournament → 4策略对比
Feature Pipeline → PIT存储    PIT零前视 → 严格20交易日    Workflow → qrun YAML
Model Registry → 版本化/复现  Rate Limit → API稳定保障    Telegram → 信号推送
IC/OOS → 因子有效性评估       Safety Margin → 先验后行    WebSocket → 实时进度
LLM Research → 自动化R&D      Circuit Breaker → -15%熔断  Self-healing → 重试/降级
```

**每一层都穿透所有策略，而非某一层对应某一策略：**

- **认知层**运行在：`compute_signals.py` 调 ML 模型时 → build_features 构建特征时 → factor_hypothesis 评估新因子时 → tournament 比较策略时。它不专属于 ML——巴菲特策略也通过 PIT 特征存储获取财务数据。
- **约束层**运行在：`PaperBroker.submit_order()` 提交前 → `build_features.py` 构建特征前清洗 → `tune_model.py` 滚动窗口 CV 防过拟合 → cron 遵守 API rate limit。它不专属于巴菲特——ML 策略同样受 5 规则风控。
- **执行层**运行在：cron 调度扫描 → workflow 引擎执行 pipeline → WebSocket 推送进度 → telegram 发送信号 → DuckDB :memory: 零锁查询。它不专属于控制论——所有策略共享同一执行基础设施。

三层在**四回路反馈**交汇：
- 市场反馈：regime 变化 → 策略自适应 → RiskManager 调整参数（约束+执行）
- 策略反馈：tournament 排名 → 模型重训 → 特征重要性反馈 LLM（认知+执行→认知）
- 模型反馈：IC/OOS 评估 → 因子选择 → alpha_factors() 进化（认知→认知）
- 数据反馈：registry status 变更 → cron 补拉 → 富化特征重建（认知+执行→认知）

## 系统分层

```
┌──────────────────────────────────────────────────────────┐
│  Web Dashboard (port 8501)                               │
│  Vue 3 + Pinia + ECharts + Tailwind — Quantum Terminal   │
│  N dynamic pages from Strategy Registry                  │
├──────────────────────────────────────────────────────────┤
│  FastAPI Backend                                         │
│  N route modules + WebSocket + async job queue            │
│  DuckDB :memory: read-only → read_parquet() views        │
│  /api/health → db_locked monitoring                      │
├──────────────────────────────────────────────────────────┤
│  Risk Control Layer ★ NEW (Phase 4.3)                    │
│  broker/risk.py — 5 pluggable rules                      │
│  max_single_position / max_total_exposure / circuit_breaker│
├──────────────────────────────────────────────────────────┤
│  Execution Layer (compute_signals.py, 15:30 CST cron)    │
│  4 strategies: buffett / multifactor / cybernetic / ml_lgbm │
│  iterate Registry → scorer → save to Parquet             │
│  Telegram @buffett0320_bot (signal push)                 │
├──────────────────────────────────────────────────────────┤
│  Workflow Layer ★ NEW (Phase 4.3)                        │
│  run_workflow.py + config/workflows/*.yaml                │
│  research_pipeline / factor_discovery — qrun-style        │
├──────────────────────────────────────────────────────────┤
│  ML / AI Layer (Phase 3.0-4.2)                           │
│  ┌─────────────────┬────────────────┬─────────────────┐  │
│  │ Feature Store   │ Model Registry │ LLM Hypothesis  │  │
│  │ PIT 35 factors  │ LightGBM+Optuna│ DSL Parser      │  │
│  │ 200 stocks×100m │ save/load/ver  │ Auto Research   │  │
│  └─────────────────┴────────────────┴─────────────────┘  │
├──────────────────────────────────────────────────────────┤
│  Strategy Layer                                          │
│  BaseStrategy interface + StrategyRegistry               │
│  Exchange (AShareExchange: stamp/commission/transfer)    │
│  4 strategies: buffett / multifactor / cybernetic / ml_lgbm │
├──────────────────────────────────────────────────────────┤
│  Data Layer                                              │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ AKShare  │  │ Tushare MCP  │  │ Parquet Store ★   │  │
│  │ OHLCV    │  │ daily_basic  │  │ data/store/        │  │
│  │ 同花顺财务│  │ PE/PB/估值   │  │ stock/macro/...    │  │
│  │ 宏观/资金│  │ moneyflow    │  │ 多资产分区          │  │
│  └──────────┘  └──────────────┘  └───────────────────┘  │
│  Data Cleaning (6 rules) → enrich_from_registry (9因子)  │
│  Data Registry (28维度)                                    │
└──────────────────────────────────────────────────────────┘
```

## 策略注册表

当前注册 4 策略，新增策略只需在 config 注册：

```yaml
strategies:
  buffett:     {color: '#06b6d4', label: 巴菲特价值精选}
  cybernetic:  {color: '#f59e0b', label: 控制论自适应}
  multifactor: {color: '#10b981', label: 多因子月度调仓}
  ml_lgbm:     {color: '#8b5cf6', label: LightGBM ML}  ★ NEW
```

策略接口 (`backtest/strategies/base.py`):
- `score(symbol, prices, idx, regime) → float` — 0-100 分
- `should_rebalance(date, regime, last_regime) → bool`
- `get_positions(scores, holdings, capital) → dict`

## 数据流

```
1. 数据采集
   AKShare → stock_zh_a_daily → data/cache/*.parquet
   AKShare → stock_financial_abstract_ths → 同花顺财务
   Tushare → daily_basic (PE/PB/市值) → data/store/

2. 数据清洗 (data/cleaner.py)
   OHLCV 完整性 → 异常值检测(保留涨跌停) → 停牌过滤 → 缺失值填充
   → 清洗报告 (丢弃/填充/缩尾统计)

3. 特征构建 (build_features.py)
   因子 × 股票 × 月数 → data/store/features/YYYY-MM.parquet (PIT, 零前视, 严格20交易日前向收益)
   → data/store/features/YYYY-MM.parquet (PIT, 零前视)

4. 模型训练 (tune_model.py) ★ NEW
   LightGBM + Optuna + 滚动窗口CV (48月训练/6月测试)
   → data/models/lgbm_best.pkl

5. 策略计算 (compute_signals.py, 每日 15:30)
   for each strategy in Registry:
     scorer → signals → data/store/signals/{strategy}.parquet

6. 信号推送 → Telegram @buffett0320_bot

7. 因子研究 (factor_hypothesis.py)
   LLM (deepseek-v4-pro) → 因子假说 → DSL解析器计算 → IC评估 → 多轮迭代 + OOS验证
   通过因子自动注册到 alpha_factors()

8. Web 展示
   FastAPI ← DuckDB(:memory:) + read_parquet() views → Vue 3 SPA
```

## 关键模块

| 模块 | 文件 | 角色 |
|------|------|------|
| 策略接口 | `backtest/strategies/base.py` | BaseStrategy + StrategyRegistry ★ |
| 交易所 | `broker/exchange.py` | AShareExchange 成本模型 ★ |
| 因子 DSL | `signals/expression.py` | 26因子声明式表达式 ★ |
| DSL 解析器 | `signals/dsl_parser.py` | LLM公式→计算 ★ |
| ML 信号 | `signals/ml_signals.py` | 模型预测→买卖信号 ★ |
| 特征存储 | `data/feature_store.py` | PIT特征构建 + 时间序列CV ★ |
| 模型层 | `models/__init__.py` | LightGBM + BaseModel + 注册表 ★ |
| ML 策略 | `backtest/strategies/ml_strategy.py` | LightGBM→BaseStrategy ★ |
| 批量特征 | `scripts/build_features.py` | 200股×100月特征构建 ★ |
| 模型训练 | `scripts/tune_model.py` | Optuna优化 + 模型训练 ★ |
| 锦标赛 | `scripts/strategy_tournament.py` | 多策略自动对比 ★ |
| 因子发现 | `scripts/factor_hypothesis.py` | LLM因子假说→验证 ★ |
| 数据获取 | `data/fetchers/moneyflow.py` | 资金流向 (AKShare+Tushare) ★ |
| 筹码获取 | `data/fetchers/holders.py` | 股东户数+增减持 ★ |
| 宏观获取 | `data/fetchers/macro.py` | PMI/M2/Shibor等7指标 ★ |
| 多资产 | `data/assets/base.py` | AssetAdapter + AssetRegistry ★ |
| 数据注册 | `data/data_registry.py` | 28维度统一管理 ★ |
| Tushare | `data/tushare_utils.py` | 统一token(环境变量优先→config兜底) |
| 数据富化 | `data/feature_store.py` | PIT特征 + enrich_from_registry ★ |
| 数据清洗 | `data/cleaner.py` | DataCleaner 6规则 (保留涨跌停异常值检测) |
| 风险控制 | `broker/risk.py` | RiskManager 5规则预检 ★ |
| 工作流 | `scripts/run_workflow.py` | qrun-style pipeline ★ NEW |
| 日频扫描 | `scripts/compute_signals.py` | Cron 15:30, 4策略 |
| 配置 | `config/settings.yaml` | 全部可调参数 |
| 数据获取 | `data/fetcher.py` | AKShare 3源 fallback |
| 财务数据 | `data/financials.py` | 同花顺 → ROE/毛利/D-E |
| 股票池 | `data/symbols.py` | 1000只, 申万31行业 |
| 数据库 | `data/db.py` + `data/results_db.py` | Parquet存储 + DuckDB视图 |
| 巴菲特过滤 | `buffett/filters.py` | 三重过滤 + 板块感知 |
| 控制论 | `cybernetics/orchestrator.py` | 月线Regime检测 ★ |
| 回测引擎 | `backtest/run_all_strategies.py` | 日频引擎 + 策略自主调仓 |
| 风险分析 | `backtest/analytics.py` | 15项风险指标 |

## 因子体系

因子分三层来源。具体数量见源码 `signals/expression.py::alpha_factors()` 和 `data/feature_store.py::enrich_from_registry()`。

### 价量因子 (Factor DSL)

| 类别 | 数量 | 来源 | 示例 |
|------|:--:|------|------|
| 收益率 | 5 | Qlib Alpha158 | ret_1d, ret_5d, ret_20d, ret_60d |
| 均线偏离 | 4 | Qlib Alpha158 | ma5_bias, ma20_bias, ma60_bias |
| 波动率 | 3 | Qlib Alpha158 | vol_5d, vol_20d, vol_60d |
| 成交量 | 2 | Qlib Alpha158 | volume_ratio_5, volume_ratio_20 |
| 价格范围 | 2 | Qlib Alpha158 | amplitude, high_low_ratio |
| 趋势 | 2 | Qlib Alpha158 | ma5_20_cross, ma20_60_cross |
| 动量 | 1 | Qlib Alpha158 | rsi_14 |
| **LLM发现** | **7** | **deepseek-v4-pro** ★ | vol_adj_mom_5d, midpoint_bias 等 |

### 外部富化因子 (9, enrich_from_registry)

| 维度 | 数量 | 来源 | 因子 |
|------|:--:|------|------|
| 资金流向 | 3 | Tushare moneyflow | mf_net_amount, mf_inst_net, mf_smart_ratio |
| 筹码集中 | 2 | Tushare holders | holder_change_pct, holder_concentration |
| 宏观经济 | 4 | AKShare macro | macro_pmi, macro_shibor_3m, macro_shibor_on, macro_cpi |

### 基本面+估值 (14, build_features.py)

| 维度 | 数量 | 来源 | 因子 |
|------|:--:|------|------|
| 基本面 | 8 | 同花顺财务 | fund_roe, fund_gross_margin, fund_de_ratio 等 |
| 估值 | 6 | Tushare daily_basic | val_pe, val_pb, val_ps, val_pe_percentile 等 |

## 策略验证

策略绩效通过锦标赛（`scripts/strategy_tournament.py`）持续验证，最新结果存储在 `data/tournament/` JSON 文件中。

## 架构演进

| Phase | 状态 | 内容 |
|-------|:--:|------|
| 1 分析助手 | ✅ | 数据 + 过滤 + 评分 + Web |
| 2 信号系统 | ✅ | 多策略 + 回测 + 日频 cron + Telegram |
| 2.5 可扩展重构 | ✅ | Strategy Registry + 消除硬编码 |
| 3.0 ML基础设施 | ✅ | Strategy接口 + Factor DSL + PIT特征 + LightGBM |
| 3.5 自动化R&D | ✅ | 基本面因子 + PE/PB + Optuna + 锦标赛 |
| 4.0 AI Agent 驱动 | 🟡 | ML接入生产 ✅ / LLM因子发现 ✅ / 自适应策略 🔜 |

## 关键设计约束

- **策略可插拔**: 新增策略 = config注册 + BaseStrategy子类
- **数据层零锁**: Parquet存储 + DuckDB `:memory:` → cron写不影响Web读
- **PIT零前视**: 所有特征按月切片, `as_of` 参数严格限制数据可用范围
- **因子可组合**: DSL表达式声明式, 可缓存, 可序列化
- **ML可重现**: 模型版本化 (registry.json), 训练参数全记录

## See Also

- [[ai-automation-roadmap]] — AI自动化三阶段路线图 ★
- [[ml-pipeline]] — ML管道完整文档 ★
- [[duckdb-migration]] — 存储架构演进 (SQLite→DuckDB→Parquet)
- [[web-architecture]] — Web SPA + health endpoint
- [[financial-cache]] — 财务三层缓存 + PIT特征存储
- [[strategy-evolution]] — 策略迭代历史 + 回测结果
- [[buffett-rolling-backtest]] — 滚动回测 + 前视偏差修复
- [[cybernetics-regime]] — 月线Regime检测 ★
