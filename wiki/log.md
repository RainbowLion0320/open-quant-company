# Wiki Log

> 操作日志。追加模式。

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
- **SCHEMA.md**: 修复 `[[wikilinks]]` → backtick 引用；更新 tag taxonomy (ml 类、新策略)
- **log.md**: 修复 `[[wikilinks]]` → backtick 引用；追加本条目

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
