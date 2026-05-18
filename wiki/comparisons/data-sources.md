---
title: 数据源对比
created: 2026-05-12
updated: 2026-05-12
type: comparison
tags: [akshare, tushare, data, cache]
---

## AKShare vs Tushare MCP

| 维度 | AKShare | Tushare MCP |
|------|---------|-------------|
| 费用 | 免费 | 2000积分 |
| 限流 | 无（需3s节流防反爬） | 约200次/分钟 |
| 日线OHLCV | ✅ 3源fallback | ✅ daily |
| 流通股本 | ✅ Sina日线自带 | ✅ daily_basic |
| 同花顺财务摘要 | ✅ ROE/毛利/D-E/增长 | ❌ 但fina_indicator更好 |
| 完整三张表 | ❌ | ✅ income/balance/cash |
| PE/PB/市值/换手 | ❌ | ✅ daily_basic |
| 融资融券 | ❌ | ✅ margin |
| 北向资金 | ❌ | ✅ hk_hold |
| 申万行业行情 | ❌ | ✅ sw_daily |

## 分工

```
AKShare（免费不限流）      Tushare MCP（2000积分）
├── 日线OHLCV              ├── 三张表
├── 实时快照               ├── 财务指标
├── 同花顺财务摘要          ├── PE/PB/市值
├── 指数成分股              ├── 融资融券+北向+申万
└──                        └── 宏观
```

## 财务数据缓存

同花顺财务摘要（`data/financials.py`）默认只读本地 Parquet，API 补数由 cron/repair 触发：

```
data/store/stock/financials/{symbol}.parquet ← scripts/cron_fetch_financials.py / repair_table.py
```

100只股票首次拉取约150秒，之后毫秒级。详见 [[financial-cache]]。

## 相关

- [[tushare-mcp]]
- [[buffett-filter]]
- [[financial-cache]]
