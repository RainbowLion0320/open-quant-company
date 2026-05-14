---
title: Financial Cache (三层财务缓存)
created: 2026-05-12
updated: 2026-05-12
type: concept
tags: [cache, parquet, financials, architecture, akshare]
---

# Financial Cache

`data/financials.py` 的三层缓存架构，为 [[buffett-filter|巴菲特过滤器]] 和 [[buffett-rolling-backtest|回测]] 提供快速财务数据访问。

## 架构

```
get_financial_summary(symbol)
  │
  ├─ 1. 内存缓存 (dict)
  │   key: f"financial_summary_{symbol}"
  │   命中 → 直接返回 ✅ (ns级)
  │
  ├─ 2. 磁盘缓存 (parquet)
  │   path: data/cache/financials/{symbol}.parquet
  │   命中 → pd.read_parquet → 填入内存 → 返回 ✅ (ms级)
  │
  └─ 3. AKShare API
      ak.stock_financial_abstract_ths(symbol)
      成功 → 写入 parquet → 填入内存 → 返回 (3-5s)
      失败 → 回退 get_financial_indicator()
```

## 数据内容

同花顺财务摘要 DataFrame，列包括：
- 报告期, 净利润, 营业总收入
- 净资产收益率 (ROE), 销售毛利率, 销售净利率
- 资产负债率, 产权比率
- 净利润同比增长率

## 性能

| 层级 | 延迟 | 适用场景 |
|------|------|---------|
| 内存 | ns | 同进程重复查询 |
| parquet | ms | 跨进程/重启后 |
| API | 3-5s | 首次拉取 |

100 只股票首次预热 ≈ 150 秒，二次运行（磁盘缓存命中）≈ 0.5 秒。

## 使用方式

```python
from data.financials import get_financial_summary

df = get_financial_summary("600519")           # 自动走缓存
df = get_financial_summary("600519", force_refresh=True)  # 强制重拉
```

## 相关

- [[buffett-rolling-backtest]] — 回测中按年读取历史财务
- [[buffett-filter]] — 过滤器依赖这些数据
- [[data-sources]] — AKShare vs Tushare 分工
