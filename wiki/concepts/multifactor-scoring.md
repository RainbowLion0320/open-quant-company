---
title: 多因子打分引擎
created: 2026-05-12
updated: 2026-06-03
type: concept
tags: [multifactor, strategy]
confidence: medium
---

## 五维打分模型

因子和权重定义在 `config/settings.yaml` → `signals.multifactor.weights`。

| 维度 | 概念 | 包含因子 |
|------|------|---------|
| Quality | 基本面质量 | 巴菲特评分 + ROE水平 + ROE趋势 |
| Valuation | 估值折扣 | 安全边际大小 |
| Technical | 技术面 | 动量 + 波动率 |
| Market | 市场环境 | Regime × 市场状态 |
| Industry Momentum | 行业动量 | 申万行业20d/60d动量 → 个股映射 |

权重: quality=0.35, valuation=0.25, technical=0.15, market=0.10, industry_momentum=0.15。
行业动量从 DataHub 维度 `sector_performance_snapshot` 读取最新快照，并通过 `sector_membership` 映射个股→行业。缺少快照或映射时回到中性行业分。

各维度的具体因子和权重在 config 中配置，可按市场状态自适应调整。

## 技术因子接入

- 动量 (1月/3月): 从 `_get_technical_factors()` 实时计算
- 波动率: 20日年化标准差
- 阈值 (buy/sell 分界线): 在 `signals.multifactor.buy_threshold` 配置

## 历史 Bug

- ~~momentum/volatility 硬编码为 0~~ → 已修复，接入实时行情
- ~~buy 阈值过高导致 0 buys~~ → 已改为配置驱动的 `signals.multifactor.buy_threshold` 和 `signal_selection` gates

## 文件

- 引擎: `signals/multifactor.py`
- 因子表达式: `signals/expression.py` + `signals/dsl_parser.py`
- 回测: `backtest/run_all_strategies.py`（多策略锦标赛）

## 相关

- [[buffett-filter]] (评分输入)
- [[cybernetics-regime]] (市场维度输入)
- [[strategy-evolution]] (多策略锦标赛)
