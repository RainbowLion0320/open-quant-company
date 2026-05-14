---
title: Tushare MCP 数据服务
created: 2026-05-12
updated: 2026-05-12
type: entity
tags: [tushare, data, architecture]
---

Tushare MCP Server v0.0.1，Streamable HTTP 协议，258个工具覆盖沪深/港股/美股/期货/宏观等大类。

## 接入方式

- URL: `https://api.tushare.pro/mcp/?token=<token>`
- MCP配置: `~/.hermes/config.yaml` → `mcp_servers.tushare`
- Token: `config/settings.yaml` → `data.tushare.token`
- 积分: 2000（免费档仅daily, stock_basic限制1次/小时）

## 核心可用接口（量化项目用）

| API | 字段 | 用途 |
|-----|------|------|
| `fina_indicator` | ROE/毛利率/净利率/D-E/FCFF等50+ | 替代同花顺摘要 |
| `daily_basic` | PE/PB/PS/市值/换手 | AKShare没有 |
| `income/balancesheet/cashflow` | 完整三张表 | 同花顺只给摘要 |
| `sw_daily` | 申万行业指数日行情 | 板块轮动基础 |
| `margin` | 融资融券 | 情绪指标 |
| `hk_hold` | 北向资金持股 | 外资动向 |
| `stk_holdernumber` | 股东人数 | 筹码集中度 |
| `research_report` | 券商研报 | 基本面参考 |

## 限流 & 已知问题

- fina_indicator: 单次100条，需循环提取
- daily_basic: 单次6000条
- 2000分约200次/分钟

## 参考

- 完整文档: `docs/tushare-mcp-guide.md`
- 数据源分工: [[data-sources]]
