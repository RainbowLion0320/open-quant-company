---
title: Wiki Index
created: 2026-05-13
updated: 2026-05-16
type: meta
tags: [index]
---

# Wiki Index

> Quant Agent 知识库目录。每行 = wikilink + 一句话概括。
> Last updated: 2026-05-15 | Total pages: 14 ( + log + schema )

## Concepts
- [[system-architecture]] — **系统架构总览**：五层设计，4策略注册表，35特征体系，多资产架构，数据注册表
- [[ml-pipeline]] — **ML 管道** ★：因子DSL→PIT特征→LightGBM→锦标赛→LLM因子发现，enrich_from_registry
- [[buffett-filter]] — 三重过滤器：能力圈→护城河→安全边际
- [[buffett-rolling-backtest]] — 滚动回测：按年重新过滤，消除前视偏差
- [[cybernetics-regime]] — 市场状态检测：月线MA排列，日频→月频修复
- [[dcf-valuation]] — DCF估值方法
- [[multifactor-scoring]] — 四维打分引擎（已演进为四策略对比体系）
- [[financial-cache]] — 三层财务缓存 + PIT基本面/估值/资金/筹码/宏观因子提取

## Entities
- [[tushare-mcp]] — Tushare MCP，258工具，2000积分（门槛制，不消耗）

## Decisions
- [[ai-automation-roadmap]] — **AI自动化路线图** ★：Phase 4.2 LLM多轮迭代+OOS+自注入库
- [[duckdb-migration]] — SQLite→DuckDB→Parquet 三阶段演进
- [[web-architecture]] — Vue 3 + FastAPI，Quantum Terminal v4.0 设计系统

## Comparisons
- [[data-sources]] — AKShare(日线+财务+宏观+资金) vs Tushare(三张表+指标+moneyflow+holders)
- [[strategy-evolution]] — 四策略回测对比：ML — 见 `data/tournament/`
