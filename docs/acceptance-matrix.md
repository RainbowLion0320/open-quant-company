# 星盘 / Astrolabe Quant OS — PRD/Spec 验收矩阵

> 日期: 2026-05-30 | 来源: 文档治理基线
> 用途: 追踪 6 个能力域从 PRD/spec → 代码 → 测试 → API/Web → 手工验收的完整链路
> 维护规则: 本文件记录当前可验收能力链路，不作为 sprint 日志；历史计划和任务过程通过 git 追溯。

## 1. 数据管道 (Data Pipeline)

| # | PRD/Spec 条目 | 代码文件 | 测试 | API / Web | 手工验收 | 状态 | 缺口 |
|---|--------------|---------|------|-----------|---------|------|------|
| 1.1 | DataRegistry 声明式维度配置 | `config/settings.yaml` → `data/data_registry.py` | `test_datahub_contracts.py:test_data_registry_contract_is_valid` | `GET /system/health` → `DatabaseHealth.vue` | registry validate 无错误，扫描使用注册表路径 | OK | — |
| 1.2 | DataHub 统一路径 `dimension_path()` + 原子写入 | `data/datahub.py` | `test_datahub_contracts.py:test_datahub_expands_registry_dimension_paths` | — | `python -c "from data.datahub import DataHub; print(DataHub().audit())"` | OK | — |
| 1.3 | Manifest 元数据记录 (schema/row_count/hash) | `data/datahub.py` | `test_datahub_contracts.py:test_datahub_writes_manifest_for_parquet` | `GET /system/health` (DB Health 页面) | 检查 `data/store/_manifest/datasets.parquet` 有记录 | OK | — |
| 1.4 | fcntl 锁 + 去重追加 | `data/datahub.py:append_parquet()` | `test_boundary.py` (DataHub追加去重写入) | — | 并发写入测试 | OK | — |
| 1.5 | AKShare 3 源 fallback (新浪→东财→腾讯) | `data/fetcher.py` | `test_data_fetcher_resilience.py` | — | `python -c "from data.fetcher import get_stock_daily; print(get_stock_daily('000001'))"` | OK | — |
| 1.6 | API 安全阀 (默认不触网) | `data/fetcher.py` | `test_architecture_contracts.py:test_stock_daily_read_path_does_not_implicitly_fetch_api` | — | 设置 `QUANT_ALLOW_API_FALLBACK=0` 验证不触网 | OK | — |
| 1.7 | 请求节流 3s + 指数退避重试 3 次 | `data/fetcher.py` | `test_data_fetcher_resilience.py` | — | 观察 cron 日志无频率限制错误 | OK | — |
| 1.8 | 6 规则数据清洗 | `data/cleaner.py` | `test_data_cleaner_contracts.py` | — | `python -c "from data.cleaner import clean_ohlcv; ..."` | OK | — |
| 1.9 | 财务数据三层缓存 (内存→Parquet→API) | `data/financials.py` | `test_datahub_contracts.py:test_financials_uses_canonical_symbol_path` | — | 第二次查询同一股票财务数据应瞬间返回 | OK | — |
| 1.10 | PIT 特征构建 (月度切片) | `data/feature_store.py` | `test_architecture_contracts.py:test_build_features_import_is_safe` | — | `python scripts/build_features.py` 生成 `data/store/features/YYYY-MM.parquet` | OK | 待增强自动化前视检测 |
| 1.11 | Cron Logger (JSONL + 自动轮转 500 行) | `data/cron_logger.py` | `test_cron_logger_contracts.py` | `GET /system/cron-log` → `Settings.vue` | 检查 `data/store/_cron_log/` 有日志文件 | OK | — |
| 1.12 | DataRegistry.validate() 合约检验 | `data/data_registry.py` | `test_datahub_contracts.py:test_data_registry_contract_is_valid` | `DatabaseHealth.vue` 健康状态列 | 启动时自动运行 validate() | OK | — |
| 1.13 | DB Health 扫描 | `data/results_db.py` | `test_datahub_contracts.py:test_db_health_scans_moneyflow_symbol_and_tushare_daily` | `GET /system/health` → `DatabaseHealth.vue` | Web 页面按 DataRegistry 启用维度展示状态表格 | OK | — |

## 2. 信号系统 (Signal System)

| # | PRD/Spec 条目 | 代码文件 | 测试 | API / Web | 手工验收 | 状态 | 缺口 |
|---|--------------|---------|------|-----------|---------|------|------|
| 2.1 | 巴菲特三重过滤 (能力圈→护城河→安全边际) | `signals/buffett.py` | `test_buffett_financial_sector.py` | `GET /signals/buffett` → `Signals.vue` | `make scan` 生成 `data/store/signals/buffett_scan.parquet` | OK | — |
| 2.2 | 多因子五维加权打分 | `signals/multifactor.py` | `test_boundary.py` (动量计算), `test_sector_pipeline.py:test_multifactor_weights_sum_to_one` | `GET /signals/multifactor` → `Signals.vue` | 固定日期+股票池评分结果可复现，detail 含 industry 分 | OK | — |
| 2.3 | ML LightGBM 信号 | `signals/ml_signals.py` | `test_architecture_contracts.py:test_model_evaluate_datetime_index_icir_does_not_crash` | `GET /signals/ml_lgbm` | `python scripts/tune_model.py` 和 `weekly_retrain.py` | OK | — |
| 2.4 | 控制论自适应 Hybrid Regime 检测 + 参数调整 | `cybernetics/orchestrator.py`, `cybernetics/hmm_engine.py`, `cybernetics/regime.py`, `cybernetics/regime_policy.py`, `cybernetics/regime_scoring.py`, `cybernetics/regime_state.py`, `data/models/regime_hmm/` | `test_market_regime_v2.py`, `test_hmm_engine.py`, `test_regime_scoring.py`, `test_regime_state.py` | `GET /market/regime` → `Market.vue`, `GET /pipeline/market-regime` → `Pipeline.vue` | Hybrid 默认引擎；规则评分输出 score/components，HMM 输出概率/confidence/entropy；不一致低置信 blended vote；实时 confirmed regime 按唯一观测日执行 `min_dwell=3` | OK | — |
| 2.5 | 因子 DSL 表达式引擎 (声明式因子) | `signals/expression.py` | `test_boundary.py` (RSI/MA/MACD/Delta) | — | `python -c "from signals.expression import SMA,Delta,Ret; ..."` | OK | — |
| 2.6 | DSL 公式解析 (LLM→计算) | `signals/dsl_parser.py` | `test_boundary.py` (公式解析) | — | `python scripts/factor_hypothesis.py` | OK | — |
| 2.7 | 横截面排名 → buy/sell/hold 信号 | `signals/selection.py` | `test_boundary.py` (apply_ranked_buys) | — | 验证信号文件符合 schema (symbol, score, signal) | OK | — |
| 2.8 | 策略插件注册表 (动态 import) | `data/strategy_plugins.py` | `test_architecture_contracts.py:test_enabled_strategy_plugins_have_runners` | `GET /strategies` → `Strategies.vue` | 新增策略只需改 yaml 配置 | OK | — |
| 2.9 | Regime 自适应权重调整 | `signals/multifactor.py` | `test_sector_pipeline.py:test_regime_affects_market_score_but_not_industry` | — | bull/bear/sideways 三种 regime 下权重分布不同 | OK | — |
| 2.10 | 行业动量因子集成 | `signals/multifactor.py:_industry_score()` | — | 多因子评分含 industry 维度, 组合敞口 API | 行业动量已纳入五维评分, detail 含 industry 分 | OK | — |
| 2.11 | 策略研究治理和晋级门槛 | `research/strategy_governance.py` | `test_strategy_research_governance.py` | `GET /strategies/governance` → `Strategies.vue` | 四策略分层、paper/production 门槛、ML 默认为 paper | OK | — |
| 2.12 | 因子研究诊断 | `signals/factor_research.py` | `test_strategy_research_governance.py:test_factor_diagnostics_rank_ic_quantile_spread_and_correlation_clusters` | — | 输出 IC/ICIR/分组收益 spread/相关性聚类 | OK | — |
| 2.13 | Market Regime 离线训练与晋级 | `research/regime_training.py`, `scripts/train_market_regime.py` | `test_regime_training.py` | `reports/regime_training/summary.json` | champion/challenger、walk-forward、策略 A/B、默认不自动替换生产公式 | OK | — |
| 2.14 | Market Regime 挣钱导向训练 | `research/regime_training.py`, `scripts/train_market_regime_profit.py`, `cybernetics/regime_policy.py` | `test_regime_profit_training.py` | `reports/regime_profit_training/summary.json` | 可交易资产 risk-on/risk-off、强 baseline、walk-forward OOS、champion 同标准诊断、best validated 选择，`w0611` 已作为规则评分基线并由统一 production policy 常量约束 | OK | — |
| 2.15 | Strategy Catalog 策略元数据权威目录 | `research/strategy_catalog.py`, `data/registry.py` | `test_strategy_catalog.py` | `GET /strategies/catalog` → `Strategies.vue` | 策略目录含类型、层级、生命周期、数据需求和输出契约 | OK | — |
| 2.16 | 策略 runtime mode 生产隔离 | `data/strategy_plugins.py`, `scripts/compute_signals.py`, `web/api/jobs.py` | `test_strategy_runtime_gates.py` | `POST /strategies/run` (`mode=production/research`) | production 默认排除 candidate；Strategy Lab 候选按钮显式 research scan | OK | — |
| 2.17 | 首批候选策略池 | `signals/candidates/*.py`, `config/settings.yaml` | `test_candidate_strategy_contracts.py` | `GET /strategies/catalog` | 8 个候选策略输出统一 StrategySignalRows，默认候选买入上限 ≤20 | OK | 需后续 OOS 实证 |

## 3. 回测引擎 (Backtest Engine)

| # | PRD/Spec 条目 | 代码文件 | 测试 | API / Web | 手工验收 | 状态 | 缺口 |
|---|--------------|---------|------|-----------|---------|------|------|
| 3.1 | N 策略锦标赛对比 | `backtest/run_all_strategies.py` | — | `GET /backtest` → `Backtest.vue` | `make backtest` 输出排名表 | OK | — |
| 3.2 | 15 项风险指标 (Sharpe/Sortino/Calmar...) | `backtest/analytics.py` | `test_boundary.py` (Sharpe/MaxDD/WinRate/Beta/Alpha) | `Backtest.vue` 雷达图 | 手工验证 Sortino 用 RMS 法、Beta 用 cov 矩阵 | OK | — |
| 3.3 | PIT 零前视偏差 | `backtest/run_all_strategies.py` | `test_backtest_pit_contracts.py` | — | 构造未来暴涨样本 → 策略不提前买入 | OK | — |
| 3.4 | Regime 回测用生产 policy 且滞后一月 | `backtest/run_all_strategies.py:build_production_regime_map()` | `test_architecture_contracts.py:test_backtest_regime_replay_uses_production_policy_not_monthly_ma_chain` | — | 历史回放 `CHAMPION_POLICY`，当月只使用上一期可得 regime，禁止旧 MA 链路 | OK | — |
| 3.5 | 巴菲特滚动窗口逐年评分 | `backtest/buffett_real_scorer.py` | — | — | 验证滚动评分器每次策略评分前重置年度缓存，且只使用当期可得财报 | OK | — |
| 3.6 | 回测结果可复现 | `backtest/run_all_strategies.py` / deterministic fixture | `test_backtest_reproducibility.py` | — | 同一数据+种子 → 同一结果 | OK | — |
| 3.7 | 可插拔回测流水线 | `backtest/pipeline.py` | `test_backtest_pipeline_contracts.py` | — | 自定义 Pipeline 组合 Data/Strategy/Selection/Risk/Execution | OK | — |
| 3.8 | 基准使用上证综指 (非个股) | `config/settings.yaml` backtest.benchmark | — | — | 确认 benchmark=sh000001 (非 000001) | OK (已修复) | — |
| 3.9 | 约束组合构建 | `pipeline/portfolio.py:ConstrainedPortfolioConstructor` | `test_strategy_research_governance.py:test_constrained_portfolio_constructor_caps_sector_and_single_name_weight` | — | Top-N 同时受单票/行业/总仓位上限约束 | OK | — |
| 3.10 | 候选策略证据报告契约 | `research/strategy_evaluation.py`, `backtest/run_all_strategies.py` | `test_strategy_backtest_evidence.py`, `test_strategy_evaluation.py` | `data/store/research/strategy_evidence/*.json` | 报告含强基准、metrics、OOS、成本、regime breakdown 和 promotion decision | OK | 待接入更多真实 baseline 结果 |

## 4. 执行层 (Execution Layer)

| # | PRD/Spec 条目 | 代码文件 | 测试 | API / Web | 手工验收 | 状态 | 缺口 |
|---|--------------|---------|------|-----------|---------|------|------|
| 4.1 | PaperBroker 模拟券商 (ABC 接口) | `broker/__init__.py` | `test_boundary.py` (买入/卖出/T+1/资金不足) | `GET /portfolio` → `Portfolio.vue` | 手工下单 → 验证持仓/余额/NAV 更新 | OK | — |
| 4.2 | T+1 交易约束 | `broker/__init__.py` | `test_boundary.py` (T+1限制卖出/隔日解除) | — | 当日买入的股票当日不能卖出 | OK | — |
| 4.3 | 5 规则风控 | `broker/risk.py` | `test_broker_risk_persistence_allocator.py:test_risk_manager_rejects_each_configured_limit`, `test_broker_risk_persistence_allocator.py:test_risk_manager_enforces_daily_order_count` | — | 逐规则验证 (仓位上限/总敞口/日频/熔断/单笔) | OK | — |
| 4.4 | 熔断机制 (回撤 > 阈值自动拒绝买单) | `broker/risk.py` | `test_broker_risk_persistence_allocator.py:test_risk_manager_rejects_each_configured_limit` | — | 模拟回撤超限 → 验证买单全拒绝 | OK | — |
| 4.5 | Parquet 状态持久化 (trades/nav/state) | `broker/persistence.py`, `broker/state.py` | `test_broker_risk_persistence_allocator.py:test_paper_state_persistence_round_trip_uses_public_state_model` | — | 创建 Broker → 下单 → 重启 → 状态恢复一致 | OK | — |
| 4.6 | Cron 调度 (15:30 扫描 + 09:30 执行) | `scripts/compute_signals.py`, `scripts/execute_paper_trades.py` | — | `POST /signals/scan` (手动触发) | GitHub Actions `daily-scan.yml` 正常执行 | OK | — |
| 4.7 | Cron 日志可观测 | `data/cron_logger.py` | — | `GET /system/cron-log` | 每次 cron 执行后日志 JSONL 有记录 | OK | — |
| 4.8 | 多资产交易所 (差异化费率) | `broker/exchange.py` | `test_broker_risk_persistence_allocator.py:test_exchange_costs_are_asset_specific` | — | A股 vs ETF 费率不同 | OK | — |

## 5. Web 平台 (Web Platform)

| # | PRD/Spec 条目 | 代码文件 | 测试 | API / Web | 手工验收 | 状态 | 缺口 |
|---|--------------|---------|------|-----------|---------|------|------|
| 5.1 | Vue 3 SPA + Pinia + ECharts + Tailwind | `web/frontend/` | — | 7 个一级入口 + 二级 tab 工作区 | `npm run build` 通过 | OK | — |
| 5.2 | FastAPI 12 业务路由模块 | `web/api/routes/` (12 文件) | `test_web_system_contracts.py` (strategy jobs 路由) | 全部业务路由模块 | `python -m uvicorn web.api.app:create_app --factory` 启动无报错 | OK | — |
| 5.3 | WebSocket 实时进度推送 | `web/api/ws.py`, `web/api/jobs.py` | `test_websocket_contracts.py` | Strategy run/backtest 进度条 | 触发回测 → 前端进度条实时更新 | OK | — |
| 5.4 | DuckDB :memory: 零锁查询 | `web/api/db.py` / `data/db.py` | `test_boundary.py` (DuckDB CRUD) | 所有数据查询端点 | Web 页面数据加载无延迟 | OK | — |
| 5.5 | API 错误响应统一 + 稳定端点 response_model | 各路由文件 + `web/api/errors.py` + `web/api/models.py` | `test_web_system_contracts.py`, `test_market_route_contracts.py`, `test_pipeline_route_contracts.py` | — | 4xx/5xx 错误结构一致，关键成功响应有 Pydantic schema | OK | — |
| 5.6 | Settings API YAML 读写 + 审计 | `web/api/routes/settings.py` | `test_audit.py`, `test_auth.py` | `/system?tab=settings` → `Settings.vue` | 修改配置 → 确认弹窗 → 保存 → audit ledger 有记录 | OK | — |
| 5.7 | 市场总览 (regime + multi_asset + macro + hot sectors) | `web/api/routes/market.py` + `web/api/routes/sectors.py` | `test_market_route_contracts.py`, `test_web_system_contracts.py` | `Market.vue` | Regime orb + 纯数字 score + 4 个核心小仪表盘 + Confirmed/Raw/Pending/Dwell 状态卡 + 核心指数相对强弱图 + 宏观快照 + Top5 热门行业脉冲；页脚只保留 MODE/REGIME/FRESH 和系统健康状态，策略明细归属策略实验室 | OK | — |
| 5.8 | DB Health 注册表维度监控 | `web/api/routes/system.py` | `test_web_system_contracts.py:test_db_health_scans_new_registry_dimensions` | `/datahub?tab=health` → `DatabaseHealth.vue` | DataRegistry 维度状态表格 + 修复操作 | OK | — |
| 5.9 | Hindsight 记忆查询 | `web/api/routes/hindsight.py` | — | `/system?tab=hindsight` → `HindsightGraph.vue` | LLM 记忆图谱可查询 | OK | — |
| 5.10 | 前端构建无大 chunk 警告 | `web/frontend/vite.config.ts` | — | — | `npm run build` 无 >500KB chunk 警告 | OK | — |
| 5.11 | System monitor (CPU/MEM/DISK) | `web/api/routes/system.py` | `test_web_system_contracts.py` | `/system?tab=monitor` → `ActivityMonitor.vue` | 资源面板 + DeepSeek 用量 + Top 进程 + API Health/Services/Cron Jobs | OK | — |
| 5.12 | Monitor/Settings 职责边界清晰 | `ActivityMonitor.vue` + `Settings.vue` | — | `/system` tabs | Monitor 只读运行观测，不展示 Telegram/Data Sources 等配置摘要；Settings 含策略状态/风控/审计 | OK | — |
| 5.13 | 行业雷达 Web 页面 | `Sectors.vue` + `web/api/routes/sectors.py`, `web/api/services/sectors.py`, `data/sectors.py` | `test_sector_pipeline.py`, `test_api_services.py`, `test_web_system_contracts.py` | `/research?tab=sectors` + `GET /api/sectors/*` | 行业资金方块矩阵主视图 + 行业面积按资金量映射 + 资金/动量/信号热力切换 + 申万行业排名表 + 行业级信号分布；不展示行业内具体股票；组合敞口归属组合执行页 | OK | — |
| 5.14 | Strategy Lab 目录化 UI + evidence artifact 下钻 | `Strategies.vue`, `StrategyLab.vue`, `StrategyEvidence.vue`, `web/frontend/src/api/index.ts` | `test_web_system_contracts.py:test_strategy_lab_exposes_catalog_and_candidate_language`, `test_strategy_evaluation.py` | `/strategy-lab?tab=strategies`, `/strategy-lab?tab=evidence`, `GET /api/strategies/evidence` | 首屏展示策略目录、生命周期筛选、候选策略、生产隔离横幅；证据面板展示 missing/available/blocked/promotion_ready 状态和 artifact 明细 | OK | — |
| 5.15 | CLI Control Plane | `astrolabe_cli/` | `test_cli_*.py` | `astroq health`, `astroq strategy catalog`, `astroq data status`, `astroq strategy evidence`, `astroq pipeline`, `astroq assets overview`, `astroq execution dry-run` | Agent 可通过 JSON 输出判断下一步动作 | OK | — |
| 5.16 | Pipeline 关键参数透明度页面 | `web/api/routes/pipeline.py`, `web/api/services/pipeline.py`, `web/frontend/src/views/Pipeline.vue` | `test_pipeline_route_contracts.py`, `test_documentation_contracts.py` | `/pipeline` + `GET /api/pipeline` + `GET /api/pipeline/{key}` | Market Regime、Data Quality、Strategy Evidence、Portfolio Execution 四条流程图；节点可点击查看输入/输出 | OK | — |

## 6. 多资产架构 (Multi-Asset)

| # | PRD/Spec 条目 | 代码文件 | 测试 | API / Web | 手工验收 | 状态 | 缺口 |
|---|--------------|---------|------|-----------|---------|------|------|
| 6.1 | AssetAdapter ABC 统一接口 | `data/assets/base.py` | `test_asset_contracts.py` (27 tests) | — | `StockAsset` / `ETFAsset` 实现所有抽象方法 | OK | — |
| 6.2 | Stock 资产 (AKShare + Tushare) | `data/assets/stock.py` | — | `GET /stocks` → `Stocks.vue` | 全量 A 股股票池可查询 | OK | — |
| 6.3 | ETF 资产 (AKShare `fund_etf_hist_em`) | `data/assets/etf.py` | `test_asset_contracts.py::TestETFAssetContracts` | — | fetch_daily 返回标准 OHLCV, data_source="real" | OK | — |
| 6.4 | Bond/Futures/Crypto 适配器 | `data/assets/{bond,futures,crypto}.py` | `test_asset_contracts.py` (5 classes) | — | Bond=proxy, Futures=real, Crypto=placeholder | OK | — |
| 6.5 | AssetAllocator regime 动态权重 | `broker/allocator.py` | `test_broker_risk_persistence_allocator.py:test_asset_allocator_normalizes_regime_enum_and_unknown` | — | bull: stock 60%, bear: stock 10%, sideways: 35% | OK | — |
| 6.6 | 资产开关控制 (enabled: true/false) | `config/settings.yaml` assets.*.enabled, `data/assets/overview.py` | `test_multi_asset_tournament.py::TestAssetOverviewContracts` | `GET /api/assets/overview` → `/datahub?tab=assets` | 关闭资产在 CLI/API/Web 中显示 disabled，不进入 allocation | OK | — |
| 6.7 | 多资产回测对比 | `backtest/multi_asset_tournament.py` | `test_multi_asset_tournament.py` | — | stock-only vs ETF-only vs multi 三组对比，proxy fallback 保留 `data_source` | OK | — |
| 6.8 | 差异化费率 (A股/ETF/债券) | `broker/exchange.py` | — | — | A股印花税 0.1% vs ETF 免印花税 | OK | — |
| 6.9 | 行业/板块数据维度 | `data/sectors.py` + `scripts/build_sector_snapshots.py` | — | `GET /api/sectors/*` | 申万行业指数 + 行业映射 + 信号聚合 + 敞口 | OK | — |
| 6.10 | 行业 Web 雷达页面 | `web/frontend/src/views/Sectors.vue` + `data/sectors.py` | `test_sector_pipeline.py`, `test_web_system_contracts.py` | `/research?tab=sectors` | 申万行业资金方块矩阵 + 按资金量映射面积 + 排名表 + 行业级信号分布，不显示行业内个股 | OK | — |

## 汇总

| 能力域 | 总条目 | 功能可验收 | 质量债条目 | 待补自动化测试 |
|--------|-------|------------|------------|----------------|
| 数据管道 | 13 | 13 | 1 | 1 |
| 信号系统 | 17 | 17 | 1 | 0 |
| 回测引擎 | 10 | 10 | 1 | 0 |
| 执行层 | 8 | 8 | 0 | 0 |
| Web 平台 | 16 | 16 | 0 | 0 |
| 多资产架构 | 10 | 10 | 0 | 0 |
| **合计** | **74** | **74** | **3** | **1** |

> **说明：** `功能可验收` 表示该能力有可用代码路径。`质量债条目` 统计"缺口"列非 `—` 的行。当前剩余 3 项质量债：PIT 特征前视检测需继续强化、候选策略需要真实 OOS 实证、候选策略证据报告需接入更多真实 baseline 结果。

**维护说明:**

- 本矩阵只保留当前能力与验收链路，具体完成时间从 git 历史追溯。
- 新能力进入矩阵前必须能映射到代码、测试或手工验收方式。
- 未来重点仍是扩大真实浏览器 smoke/e2e、视觉回归、数据质量门禁和研究实验治理。
