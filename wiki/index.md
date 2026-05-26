---
title: Wiki Index
created: 2026-05-13
updated: 2026-05-23
type: meta
tags: [index]
---

# Wiki Index

> 星盘 / Astrolabe Quant OS — 个人量化研究与执行操作系统知识库。每行 = wikilink + 一句话概括。
> This index lists stable knowledge pages. Current counts, metrics, and phase status live in code/config/data outputs, not in wiki prose.
> Documentation ownership: see `../docs/DOCUMENTATION.md`.

## Concepts
- [[system-architecture]] — **系统架构总览**：多层正交设计，策略运行入口，多资产架构，数据注册表
- [[ml-pipeline]] — **ML 管道** ★：因子DSL→PIT特征→LightGBM→锦标赛→LLM因子发现，enrich_from_registry
- [[buffett-filter]] — 三重过滤器：能力圈→护城河→安全边际
- [[buffett-rolling-backtest]] — 滚动回测：按年重新过滤，消除前视偏差
- [[cybernetics-regime]] — 市场状态检测：profit-trained 权重公式 + confirmed 状态机
- [[dcf-valuation]] — DCF估值方法
- [[multifactor-scoring]] — 五维打分引擎（含行业动量），四策略对比体系
- [[financial-cache]] — 三层财务缓存 + PIT基本面/估值/资金/筹码/宏观因子提取

- [[hindsight-architecture]] — Hindsight 记忆引擎深层架构：配置详解, 端口陷阱, 生命周期, 检索策略
- [[hindsight-graph]] — ★ Hindsight 记忆知识图谱可视化：Canvas 力导向图, 节点悬浮/点击探索
- [[paper-trading]] — ★ 日频模拟交易: 信号→PaperBroker→Parquet持久化→Web展示

## Entities
- [[tushare-mcp]] — Tushare MCP，258工具，2000积分（门槛制，不消耗）

## Decisions
- [[ai-automation-roadmap]] — **AI自动化路线图** ★：LLM多轮迭代、OOS验证、候选池晋级的方法论
- [[duckdb-migration]] — SQLite→DuckDB→Parquet 三阶段演进
- [[datahub]] — DataHub 数据中台：统一路径、原子写入、最新批次、存储审计
- [[web-architecture]] — Vue 3 + FastAPI，星盘终端 v4.0 设计系统

## Reference
- [[data-dimensions]] — ★ 数据维度索引：DataRegistry/DataHub 查询入口, 不复制动态维度数量
- [[data-schema]] — ★ 数据合约索引：DataContract 来源、检查方式、常见 schema 家族

## Comparisons
- [[data-sources]] — AKShare(日线+财务+宏观+资金) vs Tushare(三张表+指标+moneyflow+holders)
- [[strategy-evolution]] — 四策略回测对比：ML — 见 `data/tournament/`
