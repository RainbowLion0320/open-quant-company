---
title: Buffett Filter (Triple-Filter Stock Screen)
created: 2026-05-12
updated: 2026-05-12
type: concept
tags: [buffett, screening, value-investing, moat, margin-of-safety, backtest]
---

# Buffett Filter

三重过滤管道：~1000 只 A 股筛选。巴菲特哲学的中国化落地，含板块感知调整。

**所有可调参数定义在 `config/settings.yaml` → `buffett` 段。** 此页记录架构和概念，不锁死具体数值。

## Filter 1: 能力圈

主观排除。不在白名单（`circle_of_competence.industries`）内的申万行业直接淘汰。
配置中定义允许的行业列表，以及是否跳过此检查。

## Filter 2: 板块感知护城河

定量盈利能力和质量筛选，按板块调参：

| 指标 | 消费/制造 | 金融板块 | 配置路径 |
|------|----------|---------|---------|
| ROE (5年均值) | 标准阈值 | 放宽阈值 | `moat.sectors.*.min_roe` |
| 利润率类型 | 毛利率 | 销售净利率 | `moat.sectors.*.skip_gross_margin` |
| 利润率阈值 | 标准阈值 | 标准阈值 | `moat.sectors.*.min_gross_margin` / `.min_net_margin` |
| D/E 上限 | 保守 | 放宽 (杠杆是银行核心) | `moat.sectors.*.max_debt_equity` |

数据源: `data/financials.py` → 同花顺 `stock_financial_abstract_ths`，[[financial-cache|三层缓存]]。

## Filter 3: 安全边际

[[dcf-valuation|两阶段DCF]] 计算内在价值，安全边际阈值和 DCF 参数均从 config 读取。
配置项: `margin_of_safety.safety_margin_pct`、`dcf_discount_rate`、`growth_rate_terminal`。

## 综合评分

通过三重的股票按加权评分排序。权重从 `scoring` 段读取，当前维度：

| 因子 | 含义 |
|------|------|
| ROE 百分位 | 盈利能力在池中的相对位置 |
| 利润率百分位 | 毛利率/净利率的相对位置 |
| 安全边际 | 折扣大小（权重最重） |

## 回测结果

真实三重过滤（[[buffett-rolling-backtest|按年滚动]]，消除前视偏差）：**+37.61% 跑赢基准 +12.85pp**，每年仅 1-3 只通过，9 笔交易。

## See Also

- [[buffett-rolling-backtest]] — 回测中如何使用此过滤器
- [[dcf-valuation]] — DCF 方法细节
- [[financial-cache]] — 财务数据缓存架构
- [[strategy-evolution]] — 三策略对比
