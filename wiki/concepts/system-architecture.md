---
title: System Architecture (系统架构总览)
created: 2026-05-12
updated: 2026-05-30
type: concept
tags: [architecture, system-overview, extensibility, strategy-registry, ML, Factor-DSL, PIT, LightGBM, LLM]
---

# System Architecture

A股量化研究与执行系统架构总览。巴菲特价值投资为决策约束层，钱学森控制论为运行机制层——两者正交不冲突。发布版本以 `pyproject.toml` 为唯一权威；策略数量、因子数量、回测指标等动态事实以 `config/settings.yaml`、`signals/expression.py`、`var/artifacts/models/`、`var/artifacts/tournaments/` 和运行输出为准。

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
│  Vue 3 + Pinia + ECharts + Tailwind — 星盘终端           │
│  /pipeline 关键参数计算透明度页                           │
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
│  Feature Store (PIT as-of date views)                    │
│  Model Registry (LightGBM+Optuna)                        │
│  LLM Hypothesis (provider model → DSL Parser)            │
├──────────────────────────────────────────────────────────┤
│  Strategy Layer                                          │
│  BaseStrategy + unified runtime registry                 │
├──────────────────────────────────────────────────────────┤
│  Data Layer                                              │
│  AKShare (OHLCV/财务/宏观) + Tushare (PE/PB/资金/筹码)   │
│  RiskFreeRateProvider (bond treasury curve → analytics)  │
│  Parquet Store (stock/ETF/bond/futures/macro)            │
│  Data Cleaner → Enrich                                   │
│  Data Registry                                           │
└──────────────────────────────────────────────────────────┘
```

## 策略注册表

策略元数据和运行入口来自 `config/settings.yaml -> strategies`，执行调度由 `data/strategy/plugins.py` 统一处理。新增策略需要提供配置项、runner 函数和信号持久化契约：

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
   日频: scripts/cron_fetch_daily.py → dimension_path("ohlcv_daily", symbol=...)
   慢速: scripts/cron_fetch_extra.py --slow-only
   月频: Macro Monthly Refresh (1日) + Financial Monthly Refresh (3日)
   LLM providers: provider balance API + project API response usage ledger
   Risk-free curve: var/store/bond/treasury_yields.parquet → data/rates/risk_free_rates.py

   路径统一由 DataHub.dimension_path() 从 data_registry 的 cache 模式展开:
   var/store/stock/daily/{symbol}.parquet        ← "stock/daily/{symbol}.parquet"
   var/store/stock/moneyflow/daily/{YYYYMMDD}.parquet  ← 占位符自动展开
   所有脚本不再自行拼接深层路径。

2. 写入清单 (DataHub manifest, 自动)
   每次 write_parquet() → 记录到 var/store/_manifest/datasets.parquet:
   producer / row_count / date_range / schema_hash / file_sha256 / size_bytes
   manifest 写入失败不抛异常——可观测性不阻塞主数据流。

3. 数据清洗 (data/quality/cleaner.py)
   OHLCV 完整性 → 异常值检测(保留涨跌停) → 停牌过滤 → 缺失值填充
   → 清洗报告 (丢弃/填充/缩尾统计)

4. 特征构建 (scripts/build_features.py)
   因子 × 股票 × as_of_date → var/store/features/YYYY-MM-DD.parquet (PIT, 零前视)

5. 模型训练 (scripts/tune_model.py)
   LightGBM + Optuna + 滚动窗口CV (48月训练/6月测试)

6. 策略计算 (scripts/compute_signals.py, cron 触发)
   for each strategy in Registry → signals → var/store/signals/{strategy}.parquet

7. 数据库健康检查 (scripts/db_health_check.py, 每周六)
   从 data_registry.health_metadata() 获取 source/label/SLA/repair/partition
   → 按维度迭代扫描 → freshness_status (fresh/stale/missing/error)
   SLA 由 FRESHNESS_SLA_BY_FREQ 规则驱动 (daily=5d, monthly=45d, quarterly=140d)
   repair_policy 由 status 驱动 (available→auto, rate_limited→rate_limited)
   partition_key 由 cache 模式占位符推断 ({YYYYMMDD}→trade_date, {YYYYMM}→month)

8. 信号推送 → Telegram @buffett0320_bot

9. 因子研究 (factor_hypothesis.py)
   LLM → 因子假说 → DSL解析器计算 → IC评估 → OOS验证

10. 信号选择 (signals/selection.py)
    横截面排名取前 N% → apply_ranked_buys()

11. 缓存轮转 (scripts/cleanup_cache.py, 每周六)
    --dir 安全约束: 必须解析到 cache_root 内, 防止误删 store 数据

12. Web 展示
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
| 信号选择 | `signals/selection.py` | ★ 横截面排名→受限 buy list + hold rows |
| 巴菲特过滤 | `signals/buffett.py` | 安全边际+DCF+三重过滤 |
| 多因子打分 | `signals/multifactor.py` | 五维加权 (质量/估值/技术/市场/行业动量) |
| ML 信号 | `signals/ml_signals.py` | 模型预测→评分和信号行 |
| 特征存储 | `data/features/feature_store.py` | PIT特征 + enrich_from_registry |
| 模型层 | `models/__init__.py` | LightGBM + 注册表 |
| 数据清洗 | `data/quality/cleaner.py` | DataCleaner 规则化清洗 |
| 数据注册 | `data/storage/dimensions.py` | ★ 维度+健康元数据: source/label/SLA/repair/partition 单源管理 |
| Tushare工具 | `data/ingestion/tushare_utils.py` | Token 只读系统环境变量 |
| Tushare治理 | `data/ingestion/tushare_governance.py` | 权限审计、覆盖率检查、缺口补数编排 |
| 多资产基类 | `data/market/assets/base.py` | AssetAdapter ABC + AssetRegistry |
| 股票适配器 | `data/market/assets/stock.py` | StockAsset |
| ETF适配器 | `data/market/assets/etf.py` | ETFAsset (宽基/行业/黄金/债券/货币) |
| 债券适配器 | `data/market/assets/bond.py` | BondAsset (国债收益率+可转债) |
| 期货适配器 | `data/market/assets/futures.py` | FuturesAsset (主力合约) |
| 数据获取 | `data/ingestion/fetcher.py` | AKShare 3源 fallback, API缓存→var/cache/api/ |
| 财务数据 | `data/market/financials.py` | 同花顺 → ROE/毛利/D-E, 存储→var/store/stock/financials/ |
| 数据中台 | `data/storage/datahub.py` | ★ 路径合约 + 写入清单: dimension_path()/manifest_for()/write_parquet(producer=) |
| 股票池 | `data/market/symbols.py` | A股 universe 与行业映射，当前数量以源码为准 |
| 资金流获取 | `data/ingestion/fetchers/moneyflow.py` | 资金流向 |
| 筹码获取 | `data/ingestion/fetchers/holders.py` | 股东户数+增减持 |
| 宏观获取 | `data/ingestion/fetchers/macro.py` | PMI/M2/Shibor等7指标, Tushare优先 |
| 数据库 | `data/storage/db.py` + `data/storage/results_db.py` | Parquet存储 + DuckDB视图 |
| 控制论 | `cybernetics/orchestrator.py` | profit-trained Regime 检测 + 状态机确认 + 自适应参数 |
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
| CodeGraph API | `web/api/routes/codegraph.py` + `web/api/services/codegraph.py` + `web/api/services/codegraph_diagnostics.py` | ★ `/api/codegraph/*` — 本地代码图谱数据端点和确定性架构诊断 |
| 活动监视器 | `web/frontend/src/views/ActivityMonitor.vue` | 🖥️ CPU/内存/Token 仪表盘 |
| 代码图谱 | `web/frontend/src/views/CodeGraph.vue` + `web/frontend/src/composables/useCodeGraph.ts` + `useCodeGraphDiagnostics.ts` | ★ Three.js WebGL 3D 图谱, CodeGraph 模块/文件/符号可视化和架构风险叠加 |
| 模拟交易 | `web/frontend/src/views/Portfolio.vue` | ★ PaperBroker 日频模拟, NAV曲线+持仓+交易记录 |
| 回测引擎 | `backtest/run_all_strategies.py` | 日频引擎 + 策略自主调仓 |
| 回测评分 | `backtest/buffett_real_scorer.py` | PIT滚动评分器 |
| 风险分析 | `backtest/analytics.py` | 15项风险指标 |
| 回测流水线 | `backtest/pipeline_runner.py` + `pipeline/` | 生产共享 Alpha/Portfolio/Risk/Execution 阶段 |
| 配置 | `config/settings.yaml` + `web/api/config_schema/` | 全部可调参数；Web Config Center 通过 group/subgroup schema 编辑 dotted section 并写回嵌套 YAML |

## 因子体系

因子分三层来源。具体数量见源码 `signals/expression.py::alpha_factors()` 和 `data/features/feature_store.py::enrich_from_registry()`。

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
|**LLM发现** | **7** | `llm.use_cases.factor_hypothesis` 配置的 provider/model ★ | vol_adj_mom_5d, midpoint_bias 等 |
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

策略绩效通过锦标赛（`scripts/strategy_tournament.py`）持续验证，最新结果存储在 `var/artifacts/tournaments/` JSON 文件中。

## 架构演进

架构路线只记录方向和决策理由；完成状态以 git 提交、运行产物和测试结果为准，避免 wiki 中的状态标签成为过期事实。

## 关键设计约束

- **策略可插拔**: 新增策略 = config注册 + runner契约 + 信号输出契约
- **数据层零锁**: Parquet存储 + DuckDB `:memory:` → cron写不影响Web读
- **PIT零前视**: 所有特征按 as-of 日期视图读取，`as_of` 参数严格限制数据可用范围；月度切片仅作为月末兼容快照
- **因子可组合**: DSL表达式声明式, 可缓存, 可序列化
- **ML可重现**: 模型版本化 (registry.json), 训练参数全记录
- **注册表驱动**: 维度路径通过 `DataHub.dimension_path(key, **placeholders)` 从 `data_registry.cache` 展开, 路径只定义一次; DB Health 的 source/label/SLA/repair/partition 全从 DataDimension 字段派生, 不硬编码
- **写入可观测**: `DataHub.write_parquet(..., producer=)` → `_manifest/datasets.parquet` 记录 producer/row_count/date_range/schema_hash/file_sha256, 写入失败不抛异常不阻塞主路径
- **副作用分离**: `store_path()` 纯路径计算 vs `store_dir()` 创建目录, `_ensure_relative_store_pattern()` 拒绝 `..` 和绝对路径

## Manifest 子系统

`var/store/_manifest/datasets.parquet` 是 DataHub 自动维护的写入清单。每次 `write_parquet()` 成功后追加一条记录（upsert by path），记录：

| 字段 | 来源 | 用途 |
|------|------|------|
| producer | `producer=` 参数 / `ASTROLABE_PRODUCER` 环境变量 | 追溯写入来源 |
| row_count / column_count | DataFrame | 数据量统计 |
| date_column / date_min / date_max | 自动检测 date 列 | 日期范围 |
| schema_hash | 列名+dtype SHA256 | 检测 schema 变更 |
| file_sha256 | 文件内容 SHA256 | 文件完整性校验 |
| size_bytes | `os.stat` | 磁盘占用 |
| updated_at | `datetime.now()` | 最后写入时间 |

DB Health 读取 manifest 后注入 `schema_hash`、`manifest_files` 等字段，Web API 的 `db_health` 端点通过 manifest 提供更精确的数据新鲜度和完整性信息。

## See Also

- [[ai-automation-roadmap]] — AI自动化三阶段路线图 ★
- [[ml-pipeline]] — ML管道完整文档 ★
- [[duckdb-migration]] — 存储架构演进 (SQLite→DuckDB→Parquet)
- [[web-architecture]] — Web SPA + health endpoint
- [[financial-cache]] — 财务三层缓存 + PIT特征存储
- [[strategy-evolution]] — 策略迭代历史 + 回测结果
- [[buffett-rolling-backtest]] — 滚动回测 + 前视偏差修复
- [[cybernetics-regime]] — profit-trained Regime 检测 ★
- [[multifactor-scoring]] — 五维打分引擎（含行业动量）
- [[paper-trading]] — ★ 日频模拟交易系统

## Web API 契约原则

- Pipeline 页面覆盖 Market Regime、Data Quality、Strategy Evidence、Portfolio/Execution 四条关键链路，用统一节点/边/摘要契约解释关键参数和运行链路。
- Web API 的稳定契约以 Pydantic `response_model` 和前端 TypeScript 类型共同约束；新关键端点必须同时补齐后端模型、前端类型和合约测试。
