---
title: 策略演进
created: 2026-05-12
updated: 2026-05-15
type: comparison
tags: [buffett, multifactor, cybernetic, ml-lgbm, strategy, backtest]
confidence: high
---

## 策略迭代

| 阶段 | 类型 | 状态 | 说明 |
|------|------|:--:|------|
| 初版 | MA金叉 | ❌ | 信号太少 |
| 基本面 | 巴菲特过滤 | 当前 | 三重过滤 |
| 多策略 | 巴菲特+控制论+多因子 | 当前 | 四策略并列 |
| ML | LightGBM | 当前 | PIT特征+锦标赛 |

## 当前策略体系

四策略独立对比，日频引擎，策略自主决定调仓节奏。

最新回测结果见 `data/tournament/` JSON 文件。

## 关键教训

**前视偏差**: 曾用当日结果回测历史。修复: PIT零前视特征存储。

**Regime日频噪声**: 日线MA检测导致过度交易。修复: 月K线预计算。

**调仓频率**: 闭包跟踪状态，真正月度调仓。

**更多因子≠更好**: LLM因子增加后in-sample IC上升但OOS下降。需ICIR过滤。

## 相关

- [[buffett-filter]]
- [[buffett-rolling-backtest]]
- [[ml-pipeline]]
- [[financial-cache]]
- [[ai-automation-roadmap]]
