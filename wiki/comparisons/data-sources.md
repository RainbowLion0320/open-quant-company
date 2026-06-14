---
title: 数据源能力治理
created: 2026-05-12
updated: 2026-06-14
type: comparison
tags: [akshare, tushare, data, capability, registry]
---

## 问题边界

项目里有三件事不能混在一起：

| 层级 | 权威入口 | 含义 |
|------|----------|------|
| 外部能力 | `data.ingestion.source_capabilities` | 外部 source 理论上或当前环境可提供哪些接口、资产、频率和权限状态 |
| 项目接入 | `config/settings.yaml` → `data_registry` | Astrolabe 正式使用、健康检查、可修复的数据维度 |
| 本地覆盖 | DataHub store/cache/manifest | 当前机器实际下载了多少数据，是否新鲜完整 |

过去只写“AKShare vs Tushare”会漏掉两个问题：一是 AKShare 本身包装了腾讯、东方财富、新浪、同花顺等 backend；二是外部源能提供的接口远多于项目当前接入的维度。现在用 Source Capability Registry 单独治理外部能力，再和 `data_registry` 做 diff。能力状态按 `discovered`、`sample_probed`、`contracted`、`project_integrated` 分层，不能把“发现到接口”当成“生产已接入”。

## 当前 source 集合

| Source | 定位 | v1 治理方式 |
|--------|------|-------------|
| `akshare` | 免费 Python 聚合包，覆盖行情、宏观、基金、债券、期货等大量接口 | 本地安装包 introspection，记录版本、callable、module、signature、docstring 摘要；并从 callable 后缀映射腾讯、东方财富、新浪、同花顺 backend |
| `tushare` | Token-gated Pro API，财务、估值、资金流、行业和宏观深度更强 | 使用当前 `TUSHARE_TOKEN` probe 权限；缺 token 时标记 `missing_secret` |
| `tencent_finance` | 行情 backend / 直接候选源 | AKShare `_tx` callable 映射 + 静态 endpoint catalog；`qt.gtimg.cn` 和 `web.ifzq.gtimg.cn/appstock/app/fqkline/get` 仅在 sample 模式做小样本验证 |
| `eastmoney` | 行情、盘口、基金等 backend / 直接候选源 | AKShare `_em` callable 映射 + 静态候选目录；默认不直接访问东方财富网络接口 |
| `sina_finance` | 行情、指数、期货等 backend / 直接候选源 | AKShare `_sina` callable 映射 + 静态候选目录；默认不直接访问新浪网络接口 |
| `tonghuashun` | 财务摘要、资金流等 backend / 直接候选源 | AKShare `_ths` callable 映射 + 静态候选目录；默认不直接访问同花顺网络接口 |
| `exchange_official` | 交易所公告/规则/日历候选源 | 只做 candidate source，不默认补数 |
| `cninfo` | 公告和披露候选源 | 只做 candidate source，不默认补数 |
| `computed` | 项目内部派生数据 | 从正式维度和内部产物映射 |

## CLI

```bash
astroq data sources --json
astroq data sources audit --source all --discovery-depth catalog --json
astroq data sources audit --source all --discovery-depth sample --json
astroq data sources audit --source akshare --json
astroq data sources audit --source tushare --offline --json
astroq data sources audit --source tushare --json
astroq data sources diff-registry --json
```

审计产物写入：

```text
var/artifacts/data-sources/latest.json
```

Web 的 DataHub → Sources 页签只读这个产物。页面加载不扫描 AKShare 包、不访问 Tushare、不触发任何外部网络请求。

候选源当前没有被提升为生产主数据源。它们的候选接口只用于能力治理和未来字段契约评估；若要正式接入，必须先完成字段漂移、限流、授权边界和复权口径审查，再同步 `data_registry`。

## AKShare 与 Tushare 的实际分工

| 维度 | AKShare / backend | Tushare |
|------|-------------------|---------|
| 日线 OHLCV | 主要来源，支持多 backend fallback | 可作为 raw daily 能力和对账来源 |
| 流通股本/估值 | 部分接口可得，稳定性随 backend 变化 | `daily_basic` 更适合生产治理 |
| 同花顺财务摘要 | 适合快速研究缓存 | `fina_indicator` 和三张表更完整 |
| 完整三张表 | 非主路径 | `income` / `balancesheet` / `cashflow` |
| PE/PB/市值/换手 | 视 backend 可用性 | `daily_basic` |
| 资金流 | AKShare backend 可覆盖部分维度 | `moneyflow` / `moneyflow_mkt_dc` |
| 申万行业行情 | 非主路径 | `sw_daily` |
| 宏观利率 | AKShare 可作为免费来源 | Tushare 作为 token-gated 补充 |

## Diff 解释

- **Unmapped capability**：外部源存在能力，但项目没有接入到 `data_registry`。这不是 bug，本质是待评估机会。
- **Registry source missing**：项目数据维度声明了来源，但 capability registry 没有对应能力记录。这通常是真问题，需要补 capability mapping 或修正维度来源。
- **Frequency mismatch**：外部接口频率和项目维度频率不一致，需要人工确认口径。

任何新增外部数据源、fetcher 或 provider adapter，都必须同步 Source Capability Registry，并跑：

```bash
astroq data sources audit --source all --discovery-depth catalog --json
astroq data sources diff-registry --json
```

## 相关

- [[data-dimensions]]
- [[datahub]]
- [[tushare-mcp]]
- [[financial-cache]]
