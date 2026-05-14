---
title: Buffett Rolling Backtest (巴菲特滚动回测)
created: 2026-05-12
updated: 2026-05-14
type: concept
tags: [buffett, backtest, lookahead-bias, rolling-window]
---

# Buffett Rolling Backtest (巴菲特滚动回测)

> 消除前视偏差的滚动回测架构

## 问题

旧 `buffett_scorer` 调用 `load_buffett_results()` 读取 DuckDB 中**今天**的筛选结果，对所有历史月份用同一个分数。导致虚假高收益、低交易量。

## 方案演进

### v1: 简化估值评分（已废弃）
Tushare `daily_basic` 拉 PE/PB/股息率 → parquet 缓存 → 每月查当时估值评分。
- 结果: +10.03%, 548 笔, MaxDD -16.8%
- 局限: 只有 PE/PB，没有 ROE/毛利率/D-E/DCF
- 代码: `backtest/buffett_real_scorer.py`（v1, 已被 `backtest/run_all_strategies.py` 日频引擎取代并移除）

### v2: 真实三重过滤（当前）
完整 `buffett_filter()`: 能力圈 → ROE/毛利率/D-E → DCF安全边际。
按年用**当时**可用的年报数据重新跑过滤器。
- **结果: +37.61%, 跑赢基准 +12.85pp, 9 笔交易, MaxDD -14.1%**
- 代码: `backtest/buffett_real_scorer.py`

### v2 数据流

```
get_financial_summary(symbol)
  → 内存缓存? 命中 → 返回
  → parquet 磁盘? 命中 → 加载并返回
  → AKShare API → 写入 parquet → 返回

buffett_real_scorer:
  for year in 2015..2026:
    for sym in pool:
      df = get_financial_summary(sym)
      slice df to only years ≤ (year-1)  ← 关键! 消除前视偏差
      roe, gm, nm, debt = extract from df
      result = buffett_filter(sym, roe, gm, debt, ...)
      if result.verdict == PASS: cache score
    按年缓存 → 同一年各月共用
```

## 三策略对比 (2015-2026, 100只, 月度调仓)

| 策略 | 收益 | Sharpe | MaxDD | 交易 | 特点 |
|------|------|--------|-------|------|------|
| **巴菲特(真实)** | **+37.61%** | 0.05 | -14.1% | 9 | 极致精选，跑赢基准 |
| 基准(上证) | +24.76% | — | — | — | — |
| 多因子 | +1.23% | -0.02 | -51.8% | 1208 | 广撒网，高波动 |
| 控制论 | +0.63% | -0.06 | -34.3% | 842 | 板块轮动 |

## 相关

- [[buffett-filter]] — 完整巴菲特过滤逻辑，所有阈值见 config
- [[financial-cache]] — 财务数据三层缓存
- [[dcf-valuation]] — DCF 方法（参数见 config）
- [[strategy-evolution]] — 策略演进
