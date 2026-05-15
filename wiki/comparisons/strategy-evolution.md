---
title: 策略演进
created: 2026-05-12
updated: 2026-05-15
type: comparison
tags: [buffett, multifactor, cybernetic, ml-lgbm, strategy, backtest]
confidence: high
---

## 策略迭代历史

| 阶段 | 类型 | 状态 | 说明 |
|------|------|:--:|------|
| 初版 | MA5/20金叉 | ❌ 放弃 | 6年仅3-5次信号，无效 |
| 巴菲特精选池 | 基本面过滤 | 演进 | 三重过滤筛选 |
| 巴菲特+控制论 | 多策略 | 当前 | regime自适应 + 四策略并列 |
| ML | LightGBM | 当前 | PIT特征 + 锦标赛验证 |

## 当前: 四策略独立对比 (2020-2026, 100只, 日频引擎)

| 策略 | 收益 | Sharpe | MaxDD | 类型 |
|------|------|--------|-------|------|
| LightGBM ML | +28.31% | 0.17 | -10.1% | ML (26因子+PIT) |
| 多因子月度调仓 | +4.56% | -0.09 | -34.9% | 手调规则 |
| 控制论自适应 | +0.49% | -0.24 | -13.8% | 月频regime |
| 巴菲特价值精选 | n/a | — | — | 财务依赖 |

ML 模型: In-sample IC=0.551, CV IC=0.097 (Optuna优化), 7个LLM发现因子。

## 关键教训

**前视偏差（已修复）:** 曾用当日结果回测历史。修复方案：按年滚动重跑 `buffett_filter()`，PIT零前视特征存储。

**regime 检测日频噪声（已修复）:** 日线MA检测导致regime天天翻转（5974笔交易）。修复：月K线预计算，控制论100只 -5.85%→+10.07%。

**调仓频率（已修复）:** 闭包跟踪 `last_month` 状态，真正每月仅一次调仓。

**更多因子≠更好（已验证）:** LLM因子加到33个后 in-sample IC 0.194→0.551 但 OOS 收益 +36%→+28%。需因子选择（ICIR过滤）。

## 相关

- [[buffett-filter]] — 真实过滤逻辑
- [[buffett-rolling-backtest]] — 回测修复
- [[ml-pipeline]] — ML管道详解
- [[financial-cache]] — 财务缓存+因子
- [[ai-automation-roadmap]] — 自动化路线
