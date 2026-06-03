---
title: Buffett Rolling Backtest (巴菲特滚动回测)
created: 2026-05-12
updated: 2026-06-03
type: concept
tags: [buffett, backtest, lookahead-bias, rolling-window, financial-cache]
---

# Buffett Rolling Backtest (巴菲特滚动回测)

消除前视偏差的滚动回测架构。核心思想：回测任何历史月份时，只能用该时间点之前已知的数据。

## 问题

旧 scorer 读取**今天**的筛选结果评估**历史**所有月份 → 虚假 +258%（1笔交易）。

## 方案

完整 `buffett_filter()`：能力圈 → ROE/毛利率/D-E → DCF 安全边际。按年用**当时**可用的年报数据重新跑过滤。

## 数据流

```
get_financial_summary(symbol)
  → 内存缓存? 命中 → 返回
  → parquet 磁盘? 命中 → 加载并返回
  → AKShare API → 写入 parquet → 返回

buffett_real_scorer:
  for year in 2015..2026:
    for sym in pool:
      df = get_financial_summary(sym)
      slice df to only years ≤ (year-1)  ← 消除前视偏差
      roe, gm, nm, debt = extract from df
      result = buffett_filter(sym, roe, gm, debt, ...)
      if result.verdict == PASS: cache score
    按年缓存 → 同一年各月共用
```

## 回测结果

滚动评分结果通过 `backtest/run_all_strategies.py` 和 `research/strategy_evaluation.py` 进入 strategy evidence artifacts。动态收益和排名不写入 wiki，详见 `data/store/research/strategy_evidence/` 与 [[strategy-evolution]]。

## 相关

- [[buffett-filter]] — 过滤逻辑，阈值见 config/settings.yaml
- [[financial-cache]] — 财务三层缓存 + PIT 因子提取
- [[dcf-valuation]] — DCF 方法
- [[strategy-evolution]] — 策略演进
- [[ml-pipeline]] — ML 管道中的 PIT 特征存储
