---
title: Financial Cache (三层财务缓存 + PIT 特征)
created: 2026-05-12
updated: 2026-05-15
type: concept
tags: [cache, parquet, financials, architecture, akshare, PIT, feature-store, fundamental-factors]
---

# Financial Cache & PIT Feature Store

`data/financials.py` 的三层缓存架构为巴菲特过滤器和回测提供快速财务数据。Phase 3.0 后财务数据也被提取为基本面和估值因子，进入 ML PIT 特征存储。

## 三层缓存架构

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

---

## Phase 3.0: 财务 → 基本面 & 估值因子

财务数据被提取为 ML 特征 (通过 Tushare 补全估值数据):

### 基本面因子 (8)

数据源: 同花顺财务摘要 (`stock_financial_abstract_ths`)

| 因子 | 字段 | 使用方式 |
|------|------|---------|
| fund_roe | ROE (TTM) | 最新报告期 |
| fund_gross_margin | 销售毛利率 | 最新报告期 |
| fund_net_margin | 销售净利率 | 最新报告期 |
| fund_de_ratio | 资产负债率 | 最新报告期 |
| fund_net_profit | 净利润 | 年化 |
| fund_roe_5y_avg | ROE | 5年均值 |
| fund_gm_trend | 毛利率 | 同比变化 |
| fund_nm_trend | 净利率 | 同比变化 |

### 估值因子 (6)

数据源: Tushare `daily_basic` (PE/PB/PS/分红/市值)

| 因子 | 字段 | 使用方式 |
|------|------|---------|
| val_pe | pe_ttm | 当日 |
| val_pb | pb | 当日 |
| val_ps | ps_ttm | 当日 |
| val_dv_ratio | dv_ratio | 当日 (股息率) |
| val_pe_percentile | PE | 5年历史分位 |
| val_total_mv | total_mv | 当日总市值 |

### PIT 构建集成

基本面+估值数据在 `FeatureStoreBuilder.build_month()` 中与价量因子合并:

```python
# data/feature_store.py
def _get_fundamentals(symbol, as_of_date):
    """获取 as_of_date 时已知的最新财报"""
    summary = get_financial_summary(symbol)
    # 只用 as_of_date 之前的报告期
    latest = summary[summary["报告期"] <= as_of_date].iloc[-1]
    return {"fund_roe": float(latest["净资产收益率"]), ...}
```

与价量因子同理: PIT 零前视, 绝不使用未来财报。

## 使用方式

```python
from data.financials import get_financial_summary

df = get_financial_summary("600519")           # 自动走缓存
df = get_financial_summary("600519", force_refresh=True)  # 强制重拉
```

## 相关

- [[ml-pipeline]] — 财务因子在 ML 管道中的位置
- [[duckdb-migration]] — PIT 特征 Parquet 存储
- [[buffett-rolling-backtest]] — 回测中按年读取历史财务
- [[buffett-filter]] — 过滤器依赖这些数据
- [[data-sources]] — AKShare vs Tushare 分工
