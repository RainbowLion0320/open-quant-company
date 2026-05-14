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
- ✅ 无断链 (所有 [[wikilinks]] 解析正确)
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
