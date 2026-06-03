---
title: 策略演进
created: 2026-05-12
updated: 2026-06-03
type: comparison
tags: [buffett, multifactor, cybernetic, ml-lgbm, strategy, backtest]
confidence: high
---

## 策略迭代

| 阶段 | 类型 | 状态 | 说明 |
|------|------|:--:|------|
| 初版 | MA金叉 | ❌ | 信号太少 |
| 基本面 | 巴菲特过滤 | 当前 | 三重过滤 |
| 多策略 | Buffett + Multifactor + Cybernetic + ML | 当前 | 内置策略按 Strategy Catalog 分层 |
| 候选池 | Trend/Donchian/RPS/行业轮动等 | 当前 | candidate 默认只允许 research scan 和证据沉淀 |

## 当前策略体系

内置策略和候选策略走同一运行契约，但 production / paper / candidate 生命周期隔离。日频引擎按策略自主调仓节奏运行，候选策略必须通过 OOS、成本、regime 分解和 promotion gate 后才能晋级。

最新回测结果见 `data/tournament/` JSON 文件。

## 关键教训

**前视偏差**: 曾用当日结果回测历史。修复: PIT零前视特征存储。

**Regime日频噪声**: 日线 MA 检测导致过度交易。修复: 生产 policy 历史回放 + confirmed regime 状态机，回测使用上一期已可见结果。

**调仓频率**: 闭包跟踪状态，真正月度调仓。

**更多因子≠更好**: LLM因子增加后in-sample IC上升但OOS下降。需ICIR过滤。

## 相关

- [[buffett-filter]]
- [[buffett-rolling-backtest]]
- [[ml-pipeline]]
- [[financial-cache]]
- [[ai-automation-roadmap]]
