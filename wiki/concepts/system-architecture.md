---
title: System Architecture (系统架构总览)
created: 2026-05-12
updated: 2026-05-21
type: concept
tags: [architecture, system-overview, extensibility, strategy-registry, ML, Factor-DSL, PIT, LightGBM, LLM]
---

# System Architecture

A股量化交易系统架构总览。巴菲特价值投资为决策约束层，钱学森控制论为运行机制层——两者正交不冲突。当前版本、策略数量、因子数量、回测指标等动态事实以 `config/settings.yaml`、`signals/expression.py`、`data/models/`、`data/tournament/` 和运行输出为准。

## 设计哲学：三层正交架构

三层正交不是三个策略的分工——它穿透所有组件，定义系统在任何时刻的运作方式。

```
认知层 (系统如何感知与进化)   约束层 (系统边界与安全)     执行层 (系统如何运行)
━━━━━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━━
Data Registry → 数据维度自感知 RiskManager → 规则预检      Cron/Workflow → 日频扫描
Factor DSL → 声明式计算       Data Cleaner → 数据质量关卡  Tournament → 策略对比
Feature Pipeline → PIT存储    PIT零前视 → 严格20交易日    Workflow → qrun YAML
Model Registry → 版本化/复现  Rate Limit → API稳定保障    Telegram → 信号推送
IC/OOS → 因子有效性评估       Safety Margin → 先验后行    WebSocket → 实时进度
LLM Research → 自动化R&D      Circuit Breaker → -15%熔断  Self-healing → 重试/降级
```

**每一层都穿透所有策略，而非某一层对应某一策略：**

- **认知层**运行在：`scripts/compute_signals.py` 调 ML 模型时 → `scripts/build_features.py` 构建特征时 → factor_hypothesis 评估新因子时 → tournament 比较策略时。它不专属于 ML——巴菲特策略也通过 PIT 特征存储获取财务数据。
- **约束层**运行在：`PaperBroker.submit_order()` 提交前 → `scripts/build_features.py` 构建特征前清洗 → `scripts/tune_model.py` 滚动窗口 CV 防过拟合 → cron 遵守 API rate limit。它不专属于巴菲特——ML 策略同样受 5 规则风控。
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
├──────────────────────────────────────────────────────────┤
│  FastAPI Backend                                         │
│  routes + WebSocket + async jobs + DuckDB :memory: views │
├──────────────────────────────────────────────────────────┤
│  Risk Control Layer                                      │
│  broker/risk.py — 5 pluggable rules                      │
│  max_single_position / max_total_exposure / circuit_breaker│
├──────────────────────────────────────────────────────────┤
│  Execution Layer (scripts/compute_signals.py + workflow/cron)    │
│  Strategy plugins + notification hooks                   │
├──────────────────────────────────────────────────────────┤
│  Multi-Asset Layer                                       │
│  AssetAdapter ABC + AssetRegistry (5 types)              │
│  MultiAssetExchange (stock/ETF/bond/futures)              │
│  AssetAllocator (regime → weights → cross-asset orders)  │
├──────────────────────────────────────────────────────────┤
│  Workflow Layer                                          │
│  run_workflow.py + config/workflows/*.yaml                │
├──────────────────────────────────────────────────────────┤
│  ML / AI Layer                                           │
│  Feature Store (PIT monthly slices)                      │
│  Model Registry (LightGBM+Optuna)                        │
│  LLM Hypothesis (DeepSeek v4-pro → DSL Parser)           │
├──────────────────────────────────────────────────────────┤
│  Strategy Layer                                          │
│  BaseStrategy + unified runtime registry                 │
├──────────────────────────────────────────────────────────┤
│  Data Layer                                              │
│  AKShare (OHLCV/财务/宏观) + Tushare (PE/PB/资金/筹码)   │
│  Parquet Store (stock/ETF/bond/futures/macro)            │
│  Data Cleaner → Enrich                                   │
│  Data Registry                                           │
└──────────────────────────────────────────────────────────┘
```

## 策略注册表

策略元数据和运行入口来自 `config/settings.yaml -> strategies`，执行调度由 `data/strategy_plugins.py` 统一处理。新增策略需要提供配置项、runner 函数和信号持久化契约：

```yaml
strategies:
  example:
    label: Example Strategy
    config_key: signals.example
    runner: package.module:compute_example
    signal_name: example
    enabled: true
```

策略接口 (`backtest/strategies/base.py`):
- `score(symbol, prices, idx, regime) → float` — 0-100 分
- `should_rebalance(date, regime, last_regime) → bool`
- `get_positions(scores, holdings, capital) → dict`

## 数据流

```
1. 数据采集 (按频率分组的 cron 体系)
   日频: scripts/cron_fetch_daily.py → OHLCV + Shibor + 估值 + 复权 + 资金流 + 基金 + 期货
   慢速: scripts/cron_fetch_extra.py --slow-only → limit_list(1/hr) + top_list(日积月累)
   月频: Macro Monthly Refresh (1日) + Financial Monthly Refresh (3日) → 宏观+基本面全量
   DeepSeek: scripts/ingest_deepseek_cdp.py → Chrome CDP → /api/v0/usage/cost → 日度用量

   存储路径:
   data/store/stock/daily/{symbol}.parquet          ← OHLCV 日线
   data/store/stock/financials/{symbol}.parquet     ← 财务摘要 (原 data/cache/financials/)
   data/store/stock/valuation/{symbol}.parquet      ← PE/PB 估值 (原 data/cache/valuation/)
   data/store/stock/holders/、moneyflow/、...       ← Tushare 扩展维度
   data/store/fund/、futures/、macro/               ← 基金/期货/宏观
   data/cache/api/*.parquet                          ← AKShare API 响应 MD5 缓存 (可再生)
   data/store/deepseek/daily_usage.parquet           ← DeepSeek 日度 Token 用量

2. 数据清洗 (data/cleaner.py)
   OHLCV 完整性 → 异常值检测(保留涨跌停) → 停牌过滤 → 缺失值填充
   → 清洗报告 (丢弃/填充/缩尾统计)

3. 特征构建 (scripts/build_features.py)
   因子 × 股票 × 月数 → data/store/features/YYYY-MM.parquet (PIT, 零前视, 严格20交易日前向收益)

4. 模型训练 (scripts/tune_model.py)
   LightGBM + Optuna + 滚动窗口CV (48月训练/6月测试)
   → data/models/lgbm_best.pkl

5. 策略计算 (scripts/compute_signals.py, 由 workflow/cron 触发)
   for each strategy in Registry:
     scorer → signals → data/store/signals/{strategy}.parquet

6. 信号推送 → Telegram @buffett0320_bot

7. 因子研究 (factor_hypothesis.py)
   LLM (deepseek-v4-pro) → 因子假说 → DSL解析器计算 → IC评估 → 多轮迭代 + OOS验证
   通过因子自动注册到 alpha_factors()

8. 信号选择 (signals/selection.py)
   全池子打分 → 横截面排名取前 N% → apply_ranked_buys() 标记 buy。
   替代旧简单阈值 (score>=45→buy)，避免阈值过宽导致按代码顺序买入。

9. 缓存轮转 (scripts/cleanup_cache.py, 每周六)
   清理 data/cache/api/ 中 >90 天未访问的 MD5 缓存文件 (API 响应可再生)

10. Web 展示
   FastAPI ← DuckDB(:memory:) + read_parquet() views → Vue 3 SPA
```

## 关键模块

| 模块 | 文件 | 角色 |
|------|------|------|
| 策略接口 | `backtest/strategies/base.py` | BaseStrategy + StrategyRegistry |
| 多资产交易所 | `broker/exchange.py` | MultiAssetExchange (stock/ETF/bond/futures) |
| 资产分配 | `broker/allocator.py` | AssetAllocator (regime→权重→跨资产下单) |
| 风险控制 | `broker/risk.py` | RiskManager 5规则预检 |
| 因子 DSL | `signals/expression.py` | 因子声明式表达式 |
| DSL 解析器 | `signals/dsl_parser.py` | LLM公式→计算 |
| 信号选择 | `signals/selection.py` | ★ 横截面排名→交易信号 (Codex) |
| 巴菲特过滤 | `signals/buffett.py` | 安全边际+DCF+三重过滤 |
| 多因子打分 | `signals/multifactor.py` | 四维加权 (质量/估值/技术/市场) |
| ML 信号 | `signals/ml_signals.py` | 模型预测→买卖信号 |
| 特征存储 | `data/feature_store.py` | PIT特征 + enrich_from_registry |
| 模型层 | `models/__init__.py` | LightGBM + 注册表 |
| 数据清洗 | `data/cleaner.py` | DataCleaner 规则化清洗 |
| 数据注册 | `data/data_registry.py` | 数据维度统一管理 |
| Tushare工具 | `data/tushare_utils.py` | Token统一(环境变量优先→config兜底) |
| 多资产基类 | `data/assets/base.py` | AssetAdapter ABC + AssetRegistry |
| 股票适配器 | `data/assets/stock.py` | StockAsset |
| ETF适配器 | `data/assets/etf.py` | ETFAsset (宽基/行业/黄金/债券/货币) |
| 债券适配器 | `data/assets/bond.py` | BondAsset (国债收益率+可转债) |
| 期货适配器 | `data/assets/futures.py` | FuturesAsset (主力合约) |
| 数据获取 | `data/fetcher.py` | AKShare 3源 fallback, API缓存→data/cache/api/ |
| 财务数据 | `data/financials.py` | 同花顺 → ROE/毛利/D-E, 存储→data/store/stock/financials/ |
| 数据中台 | `data/datahub.py` | ★ 统一路径 + manifest: dimension_path()/manifest_for()/signal_path() |
| 股票池 | `data/symbols.py` | A股 universe 与行业映射，当前数量以源码为准 |
| 资金流获取 | `data/fetchers/moneyflow.py` | 资金流向 |
| 筹码获取 | `data/fetchers/holders.py` | 股东户数+增减持 |
| 宏观获取 | `data/fetchers/macro.py` | PMI/M2/Shibor等7指标, Tushare优先 |
| 数据库 | `data/db.py` + `data/results_db.py` | Parquet存储 + DuckDB视图 |
| 控制论 | `cybernetics/orchestrator.py` | 月线Regime检测 + 自适应参数 |
| 工作流 | `scripts/run_workflow.py` | qrun-style pipeline |
| 锦标赛 | `scripts/strategy_tournament.py` | 多策略自动对比 |
| 模拟执行 | `scripts/execute_paper_trades.py` | ★ 日频: 信号→下单→NAV→持久化 |
| 状态持久化 | `broker/persistence.py` | ★ PaperBroker Parquet 序列化 |
| 多资产锦标赛 | `scripts/multi_asset_tournament.py` | 二资产分配验证 |
| 因子发现 | `scripts/factor_hypothesis.py` | LLM因子假说→DSL→IC/OOS |
| 日频扫描 | `scripts/compute_signals.py` | workflow/cron 调度策略运行 |
| 慢数据填充 | `scripts/cron_fetch_slow.py` | 限流数据日常积累 |
| 特征构建 | `scripts/build_features.py` | 批量PIT特征构建，CLI 控制样本和区间 |
| 模型训练 | `scripts/tune_model.py` | Optuna + LightGBM |
| PE/PB补增 | `scripts/enrich_pe_pb.py` | 给特征文件批量补估值列 |
| 财务预缓存 | `scripts/precache_financials.py` | 磁盘缓存全量财务数据 |
| 缺月补建 | `scripts/rebuild_missing_months.py` | 精准补建受损特征文件 |
| Token缓存 | `scripts/update_token_cache.py` | Hermes state.db + Hindsight → JSON |
| 系统指标采集 | `scripts/collect_system_metrics.py` | 每分钟写 SQLite 时序数据 |
| Hindsight采集 | `scripts/collect_hindsight_tokens.py` | 从 /metrics (port 9177) 拉取 LLM token |
| 系统监视API | `web/api/routes/system.py` | /monitor + /history 端点 |
| 图谱API | `web/api/routes/hindsight.py` | ★ `/api/hindsight/graph` — 知识图谱数据端点 |
| 活动监视器 | `web/frontend/src/views/ActivityMonitor.vue` | 🖥️ CPU/内存/Token 仪表盘 |
| 记忆图谱 | `web/frontend/src/views/HindsightGraph.vue` | ★ Canvas力导向图, Hindsight知识图谱可视化 |
| 模拟交易 | `web/frontend/src/views/Portfolio.vue` | ★ PaperBroker 日频模拟, NAV曲线+持仓+交易记录 |
| 回测引擎 | `backtest/run_all_strategies.py` | 日频引擎 + 策略自主调仓 |
| 回测评分 | `backtest/buffett_real_scorer.py` | PIT滚动评分器 |
| 风险分析 | `backtest/analytics.py` | 15项风险指标 |
| 回测流水线 | `backtest/pipeline.py` | 可插拔回测 |
| 配置 | `config/settings.yaml` | 全部可调参数 |

## 因子体系

因子分三层来源。具体数量见源码 `signals/expression.py::alpha_factors()` 和 `data/feature_store.py::enrich_from_registry()`。

### 价量因子 (Factor DSL)

| 类别 | 数量 | 来源 | 示例 |
|------|:--:|------|------|
|收益率 | 5 | Qlib Alpha158 | ret_1d, ret_5d, ret_20d, ret_60d |
|均线偏离 | 4 | Qlib Alpha158 | ma5_bias, ma20_bias, ma60_bias |
|波动率 | 3 | Qlib Alpha158 | vol_5d, vol_20d, vol_60d |
|成交量 | 2 | Qlib Alpha158 | volume_ratio_5, volume_ratio_20 |
|价格范围 | 2 | Qlib Alpha158 | amplitude, high_low_ratio |
|趋势 | 2 | Qlib Alpha158 | ma5_20_cross, ma20_60_cross |
|动量 | 1 | Qlib Alpha158 | rsi_14 |
|**LLM发现** | **7** | **deepseek-v4-pro** ★ | vol_adj_mom_5d, midpoint_bias 等 |
|**动量增强** | **4** | **Codex 4.4** ★ | mom_3m_skip_1m, mom_6m_skip_1m, trend_strength, ma120_deviation |

### 外部富化因子 (9, enrich_from_registry)

| 维度 | 数量 | 来源 | 因子 |
|------|:--:|------|------|
| 资金流向 | 3 | Tushare moneyflow | mf_net_amount, mf_inst_net, mf_smart_ratio |
| 筹码集中 | 2 | Tushare holders | holder_change_pct, holder_concentration |
| 宏观经济 | 4+ | Data Registry macro (Tushare优先, AKShare兜底/补充) | macro_pmi, macro_shibor_3m, macro_shibor_on, macro_cpi, macro_gdp_yoy |

### 基本面+估值 (14, scripts/build_features.py)

| 维度 | 数量 | 来源 | 因子 |
|------|:--:|------|------|
| 基本面 | 8 | 同花顺财务 | fund_roe, fund_gross_margin, fund_de_ratio 等 |
| 估值 | 由配置/代码决定 | Tushare daily_basic | val_pe, val_pb, val_ps, val_pe_percentile 等 |

## 策略验证

策略绩效通过锦标赛（`scripts/strategy_tournament.py`）持续验证，最新结果存储在 `data/tournament/` JSON 文件中。

## 架构演进

架构路线只记录方向和决策理由；完成状态以 git 提交、运行产物和测试结果为准，避免 wiki 中的状态标签成为过期事实。

## 关键设计约束

- **策略可插拔**: 新增策略 = config注册 + runner契约 + 信号输出契约
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
- [[multifactor-scoring]] — 四维打分引擎
- [[paper-trading]] — ★ 日频模拟交易系统
