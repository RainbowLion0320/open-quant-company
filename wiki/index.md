# Wiki Index

> Quant Agent 知识库目录。每行 = wikilink + 一句话概括。
> Last updated: 2026-05-15 | Total pages: 14 ( + log + schema )

## Concepts
- [[system-architecture]] — **系统架构总览**：五层设计 (数据+策略+ML/AI+执行+Web)，4策略注册表，26因子体系
- [[ml-pipeline]] — **ML 管道** ★：因子DSL→PIT特征→LightGBM→锦标赛→LLM因子发现，端到端
- [[buffett-filter]] — 三重过滤器：能力圈→护城河→安全边际
- [[buffett-rolling-backtest]] — 滚动回测：按年重新过滤，消除前视偏差
- [[cybernetics-regime]] — 市场状态检测：月线MA排列 (v3.4 fix)，日频→月频
- [[dcf-valuation]] — DCF估值：两阶段模型
- [[multifactor-scoring]] — 四维打分引擎：质量+估值+技术+市场
- [[financial-cache]] — 三层财务缓存 + PIT基本面/估值因子提取

## Entities
- [[tushare-mcp]] — Tushare MCP，258工具，2000积分

## Decisions
- [[ai-automation-roadmap]] — **AI自动化路线图** ★：Phase 3.0/3.5 已完成，Phase 4.0 LLM因子探索中
- [[duckdb-migration]] — SQLite→DuckDB→Parquet 三阶段演进，Phase 3 PIT特征存储
- [[web-architecture]] — Vue 3 + FastAPI + WebSocket，动态渲染4策略

## Comparisons
- [[data-sources]] — AKShare(日线+财务) vs Tushare(三张表+指标) 分工
- [[strategy-evolution]] — 四策略回测对比：ML +28% / 多因子 +5% / 控制论 +0.5% / 巴菲特 n/a
