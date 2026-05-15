---
title: 多因子打分引擎
created: 2026-05-12
updated: 2026-05-12
type: concept
tags: [multifactor, strategy]
confidence: medium
---

## 四维打分模型

因子和权重定义在 `config/settings.yaml` → `signals.multifactor.weights`。

| 维度 | 概念 | 包含因子 |
|------|------|---------|
| Quality | 基本面质量 | 巴菲特评分 + ROE水平 + ROE趋势 |
| Valuation | 估值折扣 | 安全边际大小 |
| Technical | 技术面 | 动量 + 波动率 |
| Market | 市场环境 | Regime × 行业轮动 |

各维度的具体因子和权重在 config 中配置，可按市场状态自适应调整。

## 技术因子接入

- 动量 (1月/3月): 从 `_get_technical_factors()` 实时计算
- 波动率: 20日年化标准差
- 阈值 (buy/sell 分界线): 在 `signals.multifactor.buy_threshold` 配置

## 历史 Bug

- ~~momentum/volatility 硬编码为 0~~ → 已修复，接入实时行情
- ~~buy 阈值过高导致 0 buys~~ → 已从 60 下调
- 当前: 185 buys (1000 stocks, regime=bull)

## 文件

- 引擎: `signals/multifactor.py`
- 因子表达式: `signals/factors.py`（借鉴 qlib DSL）
- 回测: `backtest/run_all_strategies.py`（四策略对比）

## 相关

- [[buffett-filter]] (评分输入)
- [[cybernetics-regime]] (市场维度输入)
- [[strategy-evolution]] (四策略对比)
