---
title: Wiki Log
created: 2026-05-13
updated: 2026-05-18
type: meta
tags: [log]
---

# Wiki Log

> 操作日志。追加模式。

## [2026-05-18] refactor | 架构治理修正 — wiki 去动态事实
- system-architecture.md: 移除版本/策略数量/因子数量/phase状态等易过期事实，改为引用代码和运行产物。
- ml-pipeline.md: 改写为稳定方法论文档，不再复制当前 IC、因子数量、cron id。
- ai-automation-roadmap.md: 改写为晋级门槛和优先级文档，不再保存当前进度表。
- web-architecture.md: 修正系统信息路由，移除已不存在的 `/settings` 页面描述。

## [2026-05-17] audit | 项目地毯式审视 — 身份统一+config清理
- 项目标题: "Quant Agent — 个人A股量化交易系统 — 日频 · 自托管 · AI增强"
- settings.yaml: version 0.1.0→5.1.0, phase删除, 股票数1000→5204
- settings.yaml: 删除死配置 buffett_cyber + ma_cross + backtest pipeline 旧段
- README: 新标题+概述更新
- wiki: index描述更新, web-architecture日期修正, system-architecture版本描述更新

## [2026-05-17] digest | Codex hardening (ccb56ef) — wiki + 记忆同步
- signals/selection.py: 新增横截面排名信号选择模块 (apply_ranked_buys)
- signals/multifactor.py: 动量增强 (skip-1m/趋势确认/bounded保护/score_components)
- backtest/run_all_strategies.py: 3→4策略回测 (ml_lgbm scorer + max_positions动态)
- 控制论增强: 板块扩展 (电力设备/军工/交运/医药/石油石化) + 趋势确认 + 波动惩罚
- 调仓优化: 月度复评安全网 (防信号冻住) + 漂移阈值0.75
- scripts/compute_signals.py: 信号选择集成 + 组件分detail
- config/settings.yaml: signal_selection 段 + ml配置
- 前视偏差修复: mom_1m close[-22] 等
- wiki/system-architecture.md: 信号选择模块 + 动量增强因子 + 数据流步骤更新
- 新增 cron: paper-trading-daily (fcf64b5abf36, 交易日09:30)

## [2026-05-17] create | Paper Trading 模拟交易系统
- 创建 concepts/paper-trading.md — 日频执行, Parquet持久化, Web展示, 风控集成
- 更新 concepts/system-architecture.md — 模拟执行+状态持久化+模拟交易加入关键模块表
- 更新 decisions/web-architecture.md — 模拟交易页描述更新为完整功能
- 更新 index.md — 16页, 新增 paper-trading 条目
- 模块文件: broker/persistence.py + scripts/execute_paper_trades.py + web/api/routes/portfolio.py + Portfolio.vue

## [2026-05-17] create | Hindsight 知识图谱模块
- 创建 concepts/hindsight-graph.md — Canvas 力导向图, 4链接类型, 交互设计
- 更新 decisions/web-architecture.md — 10→11页, 记忆图谱专节
- 更新 concepts/system-architecture.md — 图谱API + 记忆图谱加入关键模块表
- 更新 index.md — 15页, 新增 hindsight-graph 条目
- 模块文件: web/api/routes/hindsight.py + web/frontend/src/views/HindsightGraph.vue

## [2026-05-16] codex | 指挥中心升级 + wiki同步
- Codex: Market API 扩展 (multi_asset/macro/alerts) + Market.vue 重写为 Command Center
- 前端: Regime 动画球体, 多资产跟踪器, 策略矩阵, 智能预警
- web-architecture.md: 更新为10页结构 + 指挥中心/活动监视器详情
- 锦标赛: 5204全量结果 (多因子+65.97% 🥇, ML -38.63% ❌)
- log.md/wiki同步

## [2026-05-16] plan | 下阶段计划 (Phase 5.1+)
- 更新 ai-automation-roadmap.md: 当前进度 + P1/P2/P3 计划 + 瓶颈
- P1 模型成熟度: regime ML推理/因子淘汰/A-B对比/LLM因子rerun
- P2 数据广度: ETF真实行情/Crypto CCXT/北向积累/因子跨资产
- P3 生产化: 实盘Broker/Telegram推送稳定性/WebSocket/回测加速
- 核心引擎 90% 就绪, 锦标赛全量跑中

## [2026-05-16] expand | 全A股扩满 (1000→5517只)
- CIRCLE_STOCKS: 1000 → 5517 (AKShare stock_info_a_code_name() 全量)
- universe_raw.json 更新 (5517条, 从沪深300+中证500成分股改为全量)
- CLAUDE.md / wiki/system-architecture.md 同步更新
- 特征重建后台运行中 (5517×100月, ~7-8h)
- 下一步: 重训模型 + 全量锦标赛

## [2026-05-14] create | AI 自动化路线图 + Phase 3.0 基础设施
- 新建 wiki/decisions/ai-automation-roadmap.md: 三阶段路线图
- Phase 3.0-1: Strategy 接口形式化 (backtest/strategies/base.py)
- Phase 3.0-2: Exchange 成本模型 (broker/exchange.py)
- Phase 3.0-3: 因子 DSL 表达式引擎 (signals/expression.py)
- Phase 3.0-4: Point-in-Time 特征存储 (data/feature_store.py)
- Phase 3.0-5: LightGBM 基线模型 + 注册表 (models/__init__.py)
- 更新 CLAUDE.md, index.md

## [2026-05-14] lint | 1 issue found + fixed
- ✅ 无孤立页面 (12页全部交叉引用)
- ✅ 无断链 (所有 wikilinks 解析正确)
- ❌→✅ buffett-rolling-backtest.md: 补 frontmatter (title/created/updated/type/tags)
- ⚠️ system-architecture.md: 229行略超200 (可后续拆分)
- ✅ 12页全部在 index.md 索引
- ✅ 无过期内容

## [2026-05-14] update | Parquet 存储迁移 + wiki 同步
- 数据架构: DuckDB 单文件 → Parquet 存储 + DuckDB :memory: 查询引擎
- 新建 data/store/signals/, data/store/scan_meta.parquet
- 更新 system-architecture.md: 数据层/查询层描述
- 重写 duckdb-migration.md: Phase 1→Phase 2 架构演进
- 更新 strategy-evolution.md: 100/1000只回测结果 + regime fix + 调仓频率 fix
- 项目清理: 删 .DS_Store, quant_results.db, backtest_monthly_result.pkl
- 更新 .gitignore: pkl/duckdb/db files

## [2026-05-14] update | Wiki 架构对齐 LLM Wiki 三层标准
- 新建 queries/、raw/assets/ 子目录
- 更新 SCHEMA.md: 增加 Architecture: Three Layers 章节、raw frontmatter 约定、queries 类型
- Domain: A股量化交易系统 — 巴菲特 + 控制论
- Created: SCHEMA.md, index.md, log.md
- Created concepts/: buffett-filter, cybernetics-regime, dcf-valuation
- Created entities/: tushare-mcp
- Created decisions/: duckdb-migration, web-architecture
- Created comparisons/: data-sources, strategy-evolution
- Total: 9 pages, fully cross-referenced

## [2026-05-12] update | multifactor-scoring fix + backtest run
- Fixed multifactor 0→185 buys: momentum/volatility now from live price data
- Buy threshold lowered 60→45
- Backtest run: 100 stocks × 2020-2026, 563 trades, Sharpe -0.41

## [2026-05-12] fix | Buffett backtest look-ahead bias — v1 (PE/PB)
- Problem: `buffett_scorer` used today's filter results → fake +258%, 1 trade
- Fix: `backtest/buffett_rolling.py` — Tushare daily_basic PE/PB per stock → parquet
- Result: +10.03%, 548 trades, MaxDD -16.8%
- Pitfall: `if not hasattr(fn, "_attr")` bug discovered

## [2026-05-12] fix | Buffett backtest — v2 (真实三重过滤)
- **Why not real filter?** User asked. Answer: financial data fetch was slow (AKShare per stock).
- Fix: Added parquet disk cache to `data/financials.py` (3-tier: memory→parquet→API)
- New module: `backtest/buffett_real_scorer.py` — uses complete `buffett_filter()` per year
- **Result: +37.61%, BEATS benchmark (+24.76%) by +12.85pp!**
- 9 trades, 1-3 stocks/year, MaxDD -14.1% (lowest), Sharpe 0.05
- Financial cache: 100 stocks × ~1.5s = ~150s first run, instant thereafter
- Web (port 8501) serving updated comparison

## [2026-05-12] sync | Wiki 全面同步代码结构
- index.md: 从 8 页更新到 12 页（+system-architecture +buffett-rolling-backtest +financial-cache），修正所有链接和描述
- strategy-evolution.md: 多因子 0→185 buys，前视偏差已修复，加入三策略回测对比表
- buffett-filter.md: 加入回测结果，所有阈值改为"见 config/settings.yaml"
- web-architecture.md: 6页→8页（+Backtest+StockDetail），加入 DuckDB 读写分离说明
- data-sources.md: 加入三层财务缓存说明 + 链接到 financial-cache
- duckdb-migration.md: 加入读写分离架构（Web只读 / 扫描读写）
- 新建 concepts/financial-cache.md: 三层缓存架构文档

## [2026-05-12] refactor | Wiki 去参数化
- 原则: wiki 记架构/概念/关系，不锁死迭代中的参数值
- dcf-valuation.md: 删除折现率8%/永续增长3%/年限5等硬编码，替换为 config 路径表
- buffett-filter.md: 删除 ROE≥15%/毛利率≥30%/D-E≤1.5/评分权重30-20-50，替换为 config 路径 + 板块感知概念
- buffett-rolling-backtest.md: 删除已废弃的 v1 PE/PB 评分阈值表
- cybernetics-regime.md: 删除仓位30%5%15%/止损-8%-3%-5%/持仓8-2-5，替换为"见 config"
- multifactor-scoring.md: 删除权重40%-30%-15%-15%，替换为 config 路径
- 保留: 策略对比结果表（标注日期范围的回测记录）+ sector rotation 概念示例

## [2026-05-12] design | 可扩展架构设计
- system-architecture.md 重大更新: 加入 Strategy Registry 设计
- 诊断 9 个文件硬编码策略名称 → 提出统一注册表方案
- 新增: 策略接口合约 (scorer + compute + config_key)
- 新增: 当前 vs 目标对照表 + N策略动态渲染设计
- 新增 Phase 2.5 "可扩展重构" + CLAUDE.md 文件树更新

## [2026-05-12] refactor | Phase 2.5 可扩展重构 — 完成
- 改造 12 个文件：新增 registry.py + 修改 11 个文件消除硬编码策略名
- config/settings.yaml: 新增 strategies 注册表
- data/registry.py: 新建统一加载模块 (load/get_enabled/get_label/list_names)
- data/results_db.py: _strategy_label() → registry 查找
- backtest/run_all_strategies.py: 硬编码策略列表 → 遍历 registry
- scripts/compute_signals.py: if-elif 链 + choices → registry 遍历 + 动态 argparse
- web/api/jobs.py: if-elif 链 → registry 映射派发
- web/api/routes/strategies.py: valid set → registry 动态计算 + /api/strategies 返回 registry
- web/api/routes/stocks.py: 硬编码策略名 → 遍历 registry
- web/api/routes/market.py: 返回 registry 元数据
- frontend stores/index.ts: 新增 registry store 字段
- frontend Backtest.vue: 3 个硬编码 tab → v-for 动态渲染 (颜色/标签从 registry)
- frontend Market.vue: 卡片绑定 registry enabled 状态 (禁用策略自动隐藏)
- Web (8501) 重建 + 全链路验证通过

## [2026-05-13] lint | Wiki 交叉审计 + UI 设计同步
- 修复 3 个 broken wikilink: comparing-data-sources→data-sources, cybernetic-regime→cybernetics-regime (×2)
- system-architecture.md: 更新 registry 颜色 example 匹配实际 cyan 主题
- system-architecture.md: 删除 "tab" 术语，更新为同屏叠加曲线描述
- duckdb-migration.md: 纠正错误声明——macOS 不支持真正并发读写，加入 INSERT OR REPLACE pitfall
- web-architecture.md: 新增设计系统段 (Linear-inspired tokens + Inter typography)，更新回测页描述
- 未同步: UI 微调 (pct bug fix, slider CSS, 侧栏具体像素值, emoji 选择) — 属 transient，不具架构意义

## [2026-05-15] update | Phase 3.0–4.0 架构文档全面更新

Phase 3.0 (ML基础设施) + Phase 3.5 (自动化R&D) + Phase 4.0 (AI Agent) 已完成或部分完成，wiki 与代码严重脱节。逐页审计，推动 wiki 与代码同步。

### 变更清单

- **system-architecture.md**: 重写。
  - 更新系统分层图：新增 "ML / AI Layer" (Feature Store + Model Registry + LLM Hypothesis)
  - 数据层更新: DuckDB→Parquet store，DuckDB → :memory: views
  - 新增策略: ml_lgbm 注册，AShareExchange 成本模型
  - 新增模块14个 (models/, signals/dsl_parser.py, data/feature_store.py, backtest/strategies/*)
  - 因子体系表 (26→33因子，含7个LLM发现)
  - 锦标赛结果表 (4策略)
  - 路线图状态更新 (3.0 ✅, 3.5 ✅, 4.0 🟡)

- **ai-automation-roadmap.md**: 重写。
  - Phase 3.0: 全部完成，每个子任务标注 ✅ + 产出文件 + 验证结果
  - Phase 3.5: 全部完成，追加 Optuna IC=0.097、锦标赛 ML+28.31%
  - Phase 4.0-1: ✅ (LLM 7/8 因子通过)
  - Phase 4.0-2: 🟡 (单轮已通，多轮迭代待实现)
  - Phase 4.0-3: 🔜

- **duckdb-migration.md**: 追加 Phase 3 (特征存储扩展)。
  - data/store/features/ 目录结构
  - 特征表 schema (33列)
  - 读写分离模式更新
  - 链接新增 ml-pipeline

- **ml-pipeline.md**: ★ 新建。端到端 ML 管道文档。
  - 6步管道总览图
  - 因子 DSL 完整列表 (33因子，含公式和来源)
  - PIT 特征存储 (Point-in-Time 设计、TimeSeriesSplitter)
  - LightGBM 训练 (模型注册表 registry.json、Optuna)
  - 策略锦标赛 (最新结果表)
  - 生产部署 (ml_signals.py + cron 集成)
  - LLM 因子发现 (DSL解析器→IC评估→采纳)
  - 技术债务 + 下一步

- **cybernetics-regime.md**: 追加 Monthly Regime Fix (v3.4)。
  - 问题描述: 日频 regime 翻转 → 过度交易 → -5.85%
  - 修复方案: 月线K预计算 → regime 稳定 → 交易暴跌
  - Before/After: -5.85% → +10.07% (100只)

- **financial-cache.md**: 追加 Phase 3.0 财务→因子扩展。
  - 基本面因子 (8)、估值因子 (6)
  - PIT 构建集成 (as_of 限制)
  - 链接 ml-pipeline

- **index.md**: 更新为14页。新增 ml-pipeline，策略数3→4，回测结果更新。
- **SCHEMA.md**: 修复 wikilinks 语法示例 → backtick 引用；更新 tag taxonomy (ml 类、新策略)
- **log.md**: 修复 wikilinks 语法示例 → backtick 引用；追加本条目

### 页面统计
- 修改: 6页 (system-architecture, ai-automation-roadmap, duckdb-migration, cybernetics-regime, financial-cache, index)
- 新建: 1页 (ml-pipeline)
- 修复: 2个 broken wikilinks (SCHEMA.md, log.md)
- 总页数: 13 → 14

### 交叉引用验证
- 2个 meta-reference wikilinks 已修复 (不是真正的断链，是关于 wikilinks 自身的文档引用)
- 所有页面至少2个出站 wikilinks ✓
- 所有页面有 frontmatter ✓

## [2026-05-15] redesign | Quantum Terminal Web UI v4.0

完整前端重构。从 Linear-inspired 暗色主题跨越到「量子终端」科幻风格。

### 设计系统
- 底色: `#020617` 深空蓝黑 (原 `#08090a`)
- 主色: `#00d4ff` 电光青 + `#7c3aed` 量子紫 (原 `#06b6d4` 纯青)
- 面板: 玻璃拟态 (`backdrop-filter: blur(12px)`, 半透边框)
- 氛围: Canvas 粒子场 (60粒子 + 连线辉光) + 扫描线叠加
- 字体: Inter (UI) + JetBrains Mono (数据/代码)

### 架构改进
- **API 层**: 新建 `src/api/index.ts` — 统一 fetch 客户端，14 个 endpoints 全部类型化，无 raw fetch 散布
- **ECharts**: 新建 `src/charts/useECharts.ts` — composable wrapper + QUANTUM_THEME 默认，4个页面复用
- **粒子场**: 新建 `src/charts/particles.ts` — useParticles() composable, 60粒子+连线
- **GlassCard**: 新建 `src/components/GlassCard.vue` — 可复用玻璃拟态卡片
- **设计系统**: 新建 `src/assets/quantum.css` — 完整 token 体系，统一全站
- **老样式**: 删除 `src/assets/main.css`

### Shell (App.vue)
- 浮动玻璃侧栏 (72px) — 图标 + hover tooltip + active 辉光条
- 底部状态栏 — 实时时钟 + Regime 轮询 (60s)
- 页面过渡动画 (fade + slide)
- 扫描线 overlay

### 视图重写 (8 pages)
| 页面 | 变更 |
|------|------|
| Market.vue | 玻璃卡片 + regime 进度条 + 量子紫宽度卡 + ECharts composable |
| Backtest.vue | 策略行 left-stats + right-chart + 渐变面积填充 + glow hover |
| Strategies.vue | 策略 dot 指示器 + 渐显动画 + data-table |
| Stocks.vue | 搜索玻璃栏 + 巴菲特评分色 + 信号表 |
| StockDetail.vue | DCF 估值条 + K线 composable + 信号表 |
| Portfolio.vue | 4格概览 + data-table + 下单表单 |
| Signals.vue | 变更箭头 ↑ + 信号色 |
| Settings.vue | Toggle 开关 + 系统信息表 |

### 构建验证
- Vite build: 610 modules, 0 errors, 1.44s
- 部署: `rm -f dist/ && npm run build` 替换，Web restart 可见新 UI

## [2026-05-15] expand | 数据维度全面扩展 + 多资产架构 + 注册表体系

### 重大发现: Tushare积分不消耗
积分是权限门槛, 不按调用次数扣费。2000分可免费访问所有门槛≤2000的API。
所有数据源切换为免费途径: AKShare (永久免费) + Tushare (2000分门槛内免费)。

### 多资产架构底座
- `data/assets/base.py`: AssetAdapter ABC + AssetRegistry (统一接口)
- `data/assets/stock.py`: StockAsset (包装 AKShare + Tushare 双源)
- `data/db.py`: get_store_dir(asset_type=) + 多资产视图注册
- `config/settings.yaml`: 新增 assets: [stock, macro] + 预留 fund/futures/crypto

### 数据维度扩展 (15 维度, ~800K 行, 全部免费)
- Tushare 月频资金流向: 136月 × 4000股 = 540K行
- Tushare 股东户数: 1000/1000股全历史
- Tushare 股东增减持: 703/1000股有记录
- Tushare 券商金股: 17月, 限售解禁6000条, 股票回购2000条
- AKShare 日频资金流向: 1000股 × 120天
- AKShare 宏观7指标: M2/PMI/CPI/PPI/GDP/Shibor/LPR 全历史

### 数据维度注册表
- `data/data_registry.py`: DataRegistry (28维度, 4状态)
- `config/settings.yaml` → data_registry: 每个维度的 source/asset/status/enabled/cache
- feature flags: available | rate_limited | paid | planned
- 付费维度预留: cyq_chips/stk_factor_pro/stk_mins/moneyflow_daily_full (5000分)
- 多资产预留: fund/futures/crypto (planned)

### Cron 限流数据
- `scripts/cron_fetch_slow.py`: 涨跌停 + 研报后台拉取
- Cron job_id=664a3603be57: 每交易日 16:00 CST 执行
- `scripts/fetch_moneyflow_full.py`: 资金流向全历史下载器
- `scripts/cache_all_data.py`: 批量预缓存脚本

### 文档同步
- CLAUDE.md: 更新文件树 (data/assets/, data/fetchers/, data/data_registry.py, store/stock/, store/macro/)
- config/settings.yaml: 新增 data_registry (28维度) + assets 段
- 暂未同步 wiki (待 Phase D 完成后统一更新)

## [2026-05-15] philosophy | 设计哲学升级 — 两层→三层正交架构

原始哲学: 巴菲特决策约束层 + 控制论运行机制层。经过 Phase 3.0-4.2 演进后不再准确。

新增第三层: **数据驱动认知层** (Cognitive — 怎么学)。

### 变更理由
系统实际运行中出现了两层的哲学无法覆盖的新维度:
- LLM 因子发现、锦标赛验证、特征重训 — 不是"决策"也不是"执行"，是"认知进化"
- 反馈回路从 1 条扩展到 4 条 (市场/策略/模型/数据)
- 数据注册表让系统具备"维度的自我感知"
- registry 驱动架构让系统可以自我扩展

### 新三层
```
数据驱动认知层 (怎么学)      价值约束决策层 (做什么)      控制论执行层 (怎么做)
LLM因子发现 → 因子进化        能力圈 → 资产白名单           多层递阶 → 任务分层
锦标赛 → 策略优胜劣汰         安全边际 → 风险底线           四回路反馈 → 持续改进
特征重训 → 模型进化           护城河 → 质量筛选             自适应 → 参数动态调整
数据注册表 → 维度自感知        不亏钱 → OOS验证+ICIR        前馈预防 → PIT零前视
```

### 文件变更
- SOUL.md: 完整重写。新增认知层定义，四回路反馈，三层正交关系图
- wiki system-architecture.md: 设计哲学段更新为三层
- wiki log.md: 追加本条

## [2026-05-15] layer | 新增风险控制层 + 统一工作流层

对标 vnpy RiskManager 和 Qlib qrun。

### 风险控制层 (broker/risk.py)
- RiskRule 基类 + 5 个可插拔规则: MaxSinglePosition, MaxTotalExposure, MaxOrdersPerDay, MaxDrawdownCircuitBreaker, MaxSingleOrderAmount
- RiskManager: 从 config/settings.yaml → risk_control 段加载, 预检通过才能下单
- 所有规则有 enabled 开关, 各阈值在 config 中配置
- settings.yaml: 新增 risk_control 段 (5规则)

### 统一工作流层 (scripts/run_workflow.py)
- 对标 Qlib qrun: YAML 定义 pipeline, 单命令执行
- config/workflows/research_pipeline.yaml: build_features → tune_model → strategy_tournament
- config/workflows/factor_discovery.yaml: LLM因子发现 → 重建特征 → 重训 → 验证
- run_workflow.py: 读 YAML, 顺序执行 steps, 超时+重试+on_fail 策略
- `python scripts/run_workflow.py --list` 列出所有可用工作流

### 架构图更新
- 新增 Risk Control Layer + Workflow Layer
- 层数: 6 → 8 (Web / API / Risk / Execution / Workflow / ML / Strategy / Data)

## [2026-05-15] layer | 新增数据清洗层 + 数据流重排

### 问题
数据流缺少清洗环节——原始数据直接喂特征构建。OHLCV 的负价、异常涨跌、停牌数据、缺失值都会污染训练集。

### 数据清洗层 (data/cleaner.py)
- CleanRule 基类 + 6 个可插拔规则: OHLCVIntegrity, OutlierDetection, SuspendedDetection, MissingValue, FinancialValidation, Winsorize
- DataCleaner: 从 config/settings.yaml → data_cleaning 段加载规则
- 两种模式: clean_ohlcv(df) 清洗 OHLCV, clean_features(df) 清洗特征
- 每步返回 CleanReport (丢弃/填充/缩尾统计)

### 6 条清洗规则
1. OHLCVIntegrity: 价格合理性 (high>=low, close in [low,high], close>0)
2. OutlierDetection: Z-score 检测 + 成交量暴增检测 (sigma=5)
3. SuspendedDetection: 价格连续不变≥60天 → 停牌标记
4. MissingValue: 前向填充 (最多5天), 仍有NA则丢弃
5. FinancialValidation: ROE/PE/D-E 合理性裁剪
6. Winsorize: 1%/99% 缩尾

### 集成
- build_features.py: 特征构建后 → clean_features → enrich
- feature_store.py: OHLCV 拉取后可调 clean_ohlcv
- settings.yaml: 新增 data_cleaning 段 (6规则 + enabled开关)

### 数据流重排
采集(1) → 清洗(2) → 特征构建(3) → 模型训练(4) → 策略计算(5) → 信号(6) → 因子研究(7) → Web(8)

## [2026-05-15] cleanup | Wiki 去数据化 — 存架构，不存数值

### 原则
Wiki 记录系统如何工作（HOW），不记录当前数值是什么（WHAT）。
更新数值时不该改 wiki。数值的权威来源：代码/配置/数据文件。

### 移除的易变内容
- system-architecture.md: 锦标赛结果表 + IC/因子数断言 → 改为引用 `data/tournament/`
- strategy-evolution.md: 回测数字表 → 简化为策略迭代历史 + 引用
- ai-automation-roadmap.md: Optuna IC/锦标赛数字/Phase状态 → 引用对应文件
- ml-pipeline.md: 锦标赛结果表 → 引用 `data/tournament/`
- index.md: ML+28% → 引用 `data/tournament/`

### 保留的内容（不受此规则约束）
- buffett-filter.md: +37.61% 是历史锚点结论，不是会重复更新的状态
- cybernetics-regime.md: Before/After 对比是方法论验证的一部分
- log.md: 历史日志，天然包含数值

### SCHEMA.md 更新
新增「内容准则」段，定义应该写什么/不应该写什么，以及每种数值的权威来源。

## 2026-05-17: Hindsight 记忆系统重构

### 根因诊断
Hindsight 自 05-11 起 auto-retain 停止工作。诊断出三个叠加问题：
1. **双记忆冲突** — `memory.memory_enabled: true` 让 Hermes 内置 MEMORY 和 Hindsight 同时运行，互相抢占
2. **批处理丢失** — `flush_min_turns: 6` 导致不足 6 轮的会话完全不触发 retain
3. **容量瓶颈** — `memory_char_limit: 2200` 太小

### 修复
- `~/.hermes/config.yaml`: `memory_enabled` → false, `flush_min_turns` → 1, `memory_char_limit` → 8000
- 清空 Hindsight 14 条噪音自指节点（pg0 实例重建）
- 批量注入 12 条核心项目知识（架构/策略/数据/Web/因子/交易/池子/用户偏好/配置等）

### 端口幽灵问题
发现两个 Hindsight daemon 实例：
- 8888 (start_hindsight_daemon.py 显式启动) — 14 节点空壳，Web API 之前连的它
- 9177 (Hermes 插件 auto-start) — 404 节点真实数据

修复：`web/api/routes/hindsight.py` 的 HINDSIGHT 常量从 8888 → 9177

### 知识沉淀
- 新建 `wiki/concepts/hindsight-architecture.md` — 完整架构文档（基础设施/配置/端口陷阱/生命周期/检索策略）
- 更新 `wiki/concepts/hindsight-graph.md` — 修正端口 + 添加 bug 记录 + 跨链接
- 更新 `wiki/concepts/system-architecture.md` — 记忆体系更新

### 当前状态
404 节点, 8000+ 链接。retain 每轮自动触发。Web 图谱 API 正确返回 100 节点（默认分页），但前端 Canvas 渲染为空白（待修 bug）。

## 2026-05-17: Codex 数据管理中台重构 (DataHub)

### 决策背景
项目不需要重型数据库。核心混乱不在存储格式，而在路径和读写入口分散——每个模块自己拼 `data/store/...`，硬编码绝对路径，难以扩展和审计。方案：保持 Parquet + DuckDB 不动，上面加一个轻量 DataHub 统一层。

### DataHub (`data/datahub.py`, 300 行)
- **目录统一**: `store_root`, `cache_root`, `signals`, `features`, `macro`, `paper`, `system_monitor`, token cache
- **路径消除硬编码**: `signal_path(strategy)` / `feature_path(month)` / `macro_path(name)` / `paper_path(name)`
- **原子写入**: Parquet/JSON 先写 `.tmp-{uuid}-{name}` 临时文件，再 `os.replace` 覆盖，消除半写入风险
- **追加+去重**: `append_parquet(df, dedupe_subset=[cols])` 统一追加语义
- **最新批次**: `latest_batch(path, ts_col="computed_at")` 统一取策略最新信号
- **轻量审计**: `audit()` 返回所有已知数据集的存在性/文件数/大小
- **目录注册表**: `catalog()` 返回 8 个逻辑 DatasetSpec (signals/features/paper/macro/system_monitor/token)
- **单例工厂**: `get_datahub()` / `reset_datahub()` 全局访问

### 接入覆盖 (38 个文件)
- `data/db.py`: DuckDB 视图注册改用 `HUB.signals_dir()` / `HUB.scan_meta_path()` / `HUB.cache_dir()`
- `data/results_db.py`: 策略结果/巴菲特扫描/scan meta 改为原子写入
- `data/feature_store.py`: PIT 月切片 + registry enrichment 改用 `HUB.feature_path()` + `write_parquet`
- `broker/persistence.py`: paper trading 目录改用 `HUB.paper_dir()`，消除 `Path(__file__).parent.parent / "data" / "store" / "paper"` 的相对路径拼装
- `scripts/execute_paper_trades.py`: 信号读取改用 `HUB.latest_batch()` 替代手动 `df["computed_at"].max()` 筛选
- `web/api/routes/system.py` + `scripts/collect_*.py`: 系统监控库/token cache 不再写死绝对路径
- 多个 fetcher/offline 脚本移除 `/Users/fushao/quant-agent/...` 硬编码
- `tests/test_boundary.py`: 新增 3 项 DataHub 边界测试 (latest_batch/appent去重/audit)

### 迁移原则
不移动历史数据，不改变现有 Parquet 文件名，不破坏旧路径。DataHub 作为统一入口覆盖新写和关键路径，旧模块渐进式迁移。

### 知识沉淀
- 新建 `wiki/decisions/datahub.md` — 决策背景 + 实现 + 接入范围 + 扩展规则
- 更新 `wiki/log.md` — 完整审计

## 2026-05-17: 知识图谱 3D 重构 (Canvas 2D → Three.js WebGL)

### 决策背景
用户想在 Web 端看知识图谱的 3D 星空效果。Canvas 2D 力导向图在 59 节点 + 1365 边时画面持续抖动（永不收敛），且 2D 平面线交叉不可避免。Three.js WebGL 用 GPU 渲染，性能比 Canvas 2D 高一个数量级。

### Canvas 2D 收敛修复 (commit f790306)
- **收敛判定**: 所有节点速度 < 0.15 px/frame 持续 60 帧 → 停动画
- **参数调优**: damping 0.85, repulsion 300, centering 0.005, springLen 80, springK 0.005
- **恢复动画**: 拖拽/重载时重置 converged 状态

### Three.js 3D 实现 (commit 9c3bac9)
- **渲染**: SphereGeometry 复用 + BufferGeometry 单次 draw call
- **力模拟**: 3D 空间 (x/y/z)，同参数，同收敛逻辑
- **节点大小按度**: scale 1.8~6.3，degree 越高越大
- **点击高亮**: 关联边 → 白色 solid 0.9，非关联 → 暗淡 0.05
- **OrbitControls**: 旋转/缩放/平移，autoRotate 0.15
- **星空背景**: 600 粒子 additive blending
- **安装**: three@latest (~135KB gzipped)

### 逐边高亮修复 (commit 8245615)
**Bug**: 边按类型分 4 组共用 material，点节点 → 整组全白。
**Fix**: 所有边合并到单个 BufferGeometry，用 vertexColors 逐边控制颜色。点节点时只改关联边的顶点颜色 → 白，其余 → `#111122`。

### World 节点类型 (commit 525257b)
Hindsight 事实提取的三层模型：
- **Observation** (青色 #00d4ff): 「刚发生的」→ 对话原始碎片
- **Experience** (紫色 #7c3aed): 「学到的」→ 精炼知识
- **World** (金色 #e8a840): 「本来如此的」→ 通用客观知识

三种节点在色轮上近似等边三角 (195°/270°/40°)，视觉差异最大。

### 稳定性改进
- **Keep-alive cron**: job_id=f462d01e3475，每 5 分钟检查 9177 端口，挂了自动重启
- **端口统一**: start_hindsight_daemon.py 端口从 8888 → 9177
- **Web API 指向**: hindsight.py 连接 9177（之前指向 8888 空壳）

### 知识沉淀
- 更新 `wiki/concepts/hindsight-architecture.md` — world 类型 + 当前统计
- 更新 `wiki/concepts/hindsight-graph.md` — 3D 架构细节
- 更新 `wiki/log.md` — 完整审计（本条）
- 更新 `wiki/index.md` — 链接决策页

## 2026-05-17: DeepSeek Token 消耗监控接入

### 背景
通过 Chrome DevTools MCP (Google 官方) 连接到用户本机 Chrome，在 DeepSeek 平台用量页面点击「导出」按钮下载 CSV，实现无需 API key 即可获取 token 数据。

### 技术栈
- **Chrome DevTools MCP**: Google 官方 MCP server (v0.26.0)，通过 CDP WebSocket 直接控制用户本机 Chrome
- **配置**: Hermes `mcp_servers.chrome` — stdio transport via `npx chrome-devtools-mcp@latest --autoConnect`
- **Chrome 启动**: `--remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug-profile`

### 数据摄入 (scripts/ingest_deepseek_usage.py)
- 输入: DeepSeek 平台导出的 `usage_data_YYYY_M.zip`（含 amount-*.csv + cost-*.csv）
- 处理: pivot token 类型 → 列 + merge cost → 统一 daily summary
- 输出: `data/store/deepseek/daily_usage.parquet` (22 rows, per-day per-model)
- 列: utc_date | model | input_cache_miss | input_cache_hit | output_tokens | requests | cost_cny | total_tokens

### DataHub 集成
- `datahub.py`: 新增 `deepseek_usage_path()` 路径方法 + catalog entry
- 目录: `data/store/deepseek/daily_usage.parquet`

### Web 监控面板 (Activity Monitor)
- 后端 API: `GET /api/system/deepseek-usage` (raw parquet → JSON, last 14 days)
- 前端: Canvas 柱状图，过去 7 天每天两组柱 (v4-pro 青色 + v4-flash 紫色)
- Y 轴单位: 百万 tokens，X 轴: MM-DD 日期

### 5 月统计 (1-17 日)
| 模型 | 实际计费 Token | 调用次数 |
|------|---------------|---------|
| v4-pro | 46.7M | 7,193 |
| v4-flash | 57.5M | 8,522 |
| **合计** | **104.2M** | **15,715** |

缓存命中 token 不收费 (v4-pro: 1.6B, v4-flash: 23M)。总费用约 ¥275。

### Cron 任务
- `job_id=781d17fea37f`: 每日 23:30 自动摄入最新 CSV

## 2026-05-17: DeepSeek 图表多轮迭代

### 三级叠加柱状图 (fde8a41)
将简单总 token 柱改为三级叠加：底部 input_cache_miss(深色)、中部 output_tokens(实色)、顶部 input_cache_hit(半透明)。直观展示计费 vs 免费的占比。

### 拆分为独立图表 (7a17943)
两个模型放同一图时 Y 轴比例失衡（v4-pro cache_hit 200M+ 碾压 v4-flash 4M）。改为两个独立画布，各自独立 Y 轴缩放。

### 30 天视图 + 费用图 (f8dca87)
- 范围从 7 天扩展到 30 天
- 三行垂直布局：v4-pro 叠加柱 / v4-flash 叠加柱 / 费用 ¥ 柱状+折线
- X 轴日历生成（非数据驱动），缺失日期填 0
- 柱宽从满槽逐步收窄到 20% 槽宽 (ec17743→ef43259→ac7d5ae)
- 30 天合计值以 tag-badge 形式显示在表头 (9e01d61→eadf2b1)

### 图表周边清理
- 删除旧的「今日 Token 用量」卡片 (d2d1e92)
- 删除旧的「Token $」历史趋势折线图 (c7b3099)

## 2026-05-17: 系统页面重构 + 留存优化

### 活动监视器 + 系统设置合并 (7fc6430)
两个页面都是"系统信息"，合并为一个页面：
- ActivityMonitor.vue 追加三块 Settings 内容：Telegram 通知开关、数据源状态 (AKShare/Tushare/Hindsight/Parquet)、系统信息网格
- 侧栏从 10 项减为 9 项，「活动监视」→「系统信息」
- 路由移除 /settings，Settings.vue 不再加载 (618→618 模块)

### 系统监控留存期 (0479e20)
`collect_system_metrics.py` 自带内联清理逻辑 (`_cleanup()`)，每次采集时自动删除超期数据。留存期从 30 天改为 365 天 (~515K 行 ≈ 72 MB，SQLite 完全可控)。

## 2026-05-17: Codex UI polish — 11个文件系统性优化 (commit 18ebb0d)

### 背景
我之前按 Market.vue 风格重构了系统信息页，但 Codex 在此基础上做了大幅 polish。这是对我工作的 code review + 提升，暴露出我多个设计习惯问题。

### Codex 改动范围
11 文件, 972 insertions: ActivityMonitor.vue(573行), quantum.css(67行), Settings.vue(188行), Market.vue(60行), HindsightGraph.vue(114行), Backtest/Portfolio/StockDetail/Strategies/Stocks/Signals

### 关键教训（与我的做法对比）

**1. 语义化 class 而非 inline style 堆砌**
我写: `<div class="hero-value" :style="{ color: cpuColor }">`
Codex: `.metric-main strong` + `.telemetry-card` + `.meter-track i`
→ 命名 CSS class 可复用、可维护、可全局主题切换

**2. null 安全 + computed 格式化函数**
我写: `data?.cpu.percent ?? 0` → 无数据时显示"0%"（误导）
Codex: `fmtPercent(monitor?.cpu?.percent)` → 无数据返回"—%"
添加了 `fmtGb()`, `fmtPercent()`, `pctWidth()`, `loadText`, `batteryText` computed

**3. Canvas 防御性 fallback 尺寸**
我写: `canvas.offsetWidth` → 初始化时可能为 0
Codex: `canvas.offsetWidth || 320` → 始终有合法值

**4. 语义化 HTML 标签**
我用匿名 `<div>` 套 `<div>`
Codex: `<article>` 指标卡, `<aside>` 侧栏, `<section>` 页面分区

**5. CSS 上提到共享样式表**
我把 `padding:18px; display:flex;flex-direction:column;gap:12px` 写在各页面 scoped style 里
Codex: 提取为 `quantum.css` 的 `.view-page`, `.card-pad`, `.section-heading`, `.metric-card`

**6. min-height 替代固定 height**
我写: `style="height:120px"` → 内容溢出被截断
Codex: `.chart-block { min-height: 142px }` → 允许自然增长

**7. clamp() 响应式字号**
我写: `font-size: 36px`
Codex: `font-size: clamp(26px, 3vw, 38px)` → 跨视口自然缩放

**8. minmax() 防 grid 列塌缩**
我写: `grid-template-columns: 2fr 1fr` → 小屏幕可能塌为 0
Codex: `minmax(0, 1.65fr) minmax(330px, 0.8fr)` → 始终有最小宽度

**9. 命名 CSS 状态 class 而非 inline rgba 色值**
我写: `style="background:rgba(6,182,212,0.12);color:rgba(6,182,212,0.9)"`
Codex: `.tag-badge.cyan` `.tag-badge.violet` `.tag-badge.amber`

**10. 全线添加空状态占位**
我完全没有空状态处理
Codex: Market 指数K线/告警/资产/策略矩阵/宏观指标均有 `v-if/v-else` 占位符，进程表有 "暂无进程采样"

**11. `<strong>` / `<em>` 语义标签替代样式 span**
我写: `<span :style="{ color: 'var(--text-primary)' }">`
Codex: `<strong>` + `<em>` + CSS 赋色

### 知识沉淀
- 更新 `wiki/log.md` — 本条目
- 提炼为可复用的前端开发规范（见下文）

### 前端开发规范（从本次对比中提取）
- 禁止在模板中使用裸 `rgba()` 或 hex 色值 inline style → 使用命名 CSS class
- 所有 `?? 0` 默认值改为格式化函数的 `"—"` 安全返回
- Canvas 尺寸读取必须带 `|| 320` style fallback
- 所有数据列表必须有 `v-if` 空状态分支
- 页面容器用 `.view-page` class (quantum.css 全局共享)
- grid 用 `minmax()` 防塌缩，字号用 `clamp()` 做响应式
- 语义标签: `<article>` → 独立卡片, `<aside>` → 侧栏, `<section>` → 页面分区

## 2026-05-18: Codex 架构加固 — 插件注册表 + 合约测试 + 软约束硬化 (commit 2033584)

### 核心交付 (28 files, 986 insertions)

**1. 策略插件注册表 (data/strategy_plugins.py, 135行)**
- `DEFAULT_RUNNERS` 字典：每个策略名 → `module:function` 映射
- `StrategyPlugin` 冻结 dataclass：name/label/runner/signal_name，不可变合约
- `load_runner()`：运行时 `importlib.import_module` + `getattr` 动态加载
- `compute()` → `save()` 统一生命周期
- `run_registered_strategies()`：CLI 和 Web 统一的调度入口，带 progress_callback

**2. settings.yaml 显式化**
- 每个策略新增 `runner` 和 `signal_name` 字段
- Paper trading 新增硬约束：lot_size=100, order_value_pct=0.05, max_order_value=50000, max_orders_per_strategy=5, sell_all_on_sell_signal=true
- ML 新增：max_feature_age_months=3, allow_stale_features=false, allow_live_factor_fallback=false

**3. 架构合约测试 (tests/test_architecture_contracts.py, 73行)**
- `test_enabled_strategy_plugins_have_runners()`：所有启用策略的 runner 必须可调用
- `test_datahub_catalog_includes_data_registry_dimensions()`：catalog 必须覆盖数据维度
- `test_build_features_import_is_safe()`：模块导入安全
- `test_paper_broker_never_sells_more_than_position_when_t0()`：卖不超过持仓
- `test_prepare_xy_drops_missing_targets()`：缺失目标自动丢弃
- `test_model_evaluate_datetime_index_icir_does_not_crash()`：ICIR 计算不崩溃

### 底层文件内化
- **SOUL.md**: 新增「插件注册」(认知层)、「软约束硬化」「架构合约测试」(执行层) 三条哲学
- **CLAUDE.md**: 文件树新增 strategy_plugins.py + tests 描述更新
