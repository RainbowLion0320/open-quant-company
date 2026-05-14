# Wiki Index

> Quant Agent 知识库目录。每行 = wikilink + 一句话概括。
> Last updated: 2026-05-12 | Total pages: 12 ( + log + schema )

## Concepts
- [[system-architecture]] — **系统架构总览**：分层设计、数据流、策略注册表（可插拔N策略）、模块地图
- [[buffett-filter]] — 三重过滤器：能力圈→护城河→安全边际，回测 +37.61% 跑赢基准
- [[buffett-rolling-backtest]] — 滚动回测：按年重新过滤，消除前视偏差
- [[cybernetics-regime]] — 市场状态检测：MA排列判定牛熊，自适应仓位
- [[dcf-valuation]] — DCF估值：两阶段模型，参数见 config
- [[multifactor-scoring]] — 四维打分引擎：质量+估值+技术+市场
- [[financial-cache]] — 三层财务缓存：内存→parquet→AKShare API

## Entities
- [[tushare-mcp]] — Tushare MCP，258工具，2000积分，Streamable HTTP

## Decisions
- [[duckdb-migration]] — SQLite→DuckDB迁移，读写分离（Web只读+扫描读写）
- [[web-architecture]] — Vue 3 + FastAPI + WebSocket，8 页面交互式仪表盘

## Comparisons
- [[data-sources]] — AKShare(日线+财务) vs Tushare(三张表+指标) 分工
- [[strategy-evolution]] — 三策略对比：巴菲特 +37.61% / 多因子 +1.23% / 控制论 +0.63%
