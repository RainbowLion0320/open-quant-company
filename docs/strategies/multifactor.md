# 多因子月度调仓

- **状态**: production
- **信号名**: multifactor
- **运行器**: `scripts.compute_signals:compute_multifactor`

## 概述

四维加权打分系统：质量 40%（Buffett 分数 + ROE + ROE 趋势）+ 估值 30%（安全边际分层）+ 技术 15%（动量 + 波动率）+ 市场 15%（板块 × 市场状态）。月度调仓，Top 10 等权。

## 数据依赖

| 维度 | 来源 | 频率 |
|------|------|------|
| ohlcv_daily | AKShare | daily |
| financial_summary | AKShare | quarterly |
| fina_indicator | Tushare | quarterly |
| adj_factor | AKShare | daily |
| valuation_daily | Tushare | daily |

## 参数空间

| 参数 | 值 | 说明 |
|------|-----|------|
| buy_threshold | 52 | 最低买入分 |
| quality_weight | 0.4 | 质量权重 |
| valuation_weight | 0.3 | 估值权重 |
| technical_weight | 0.15 | 技术权重 |
| market_weight | 0.15 | 市场权重 |
| top_n | 10 | 持仓数量 |
| rebalance_interval | ~20 交易日 | 月度调仓 |
| score_base | 50 | 基准分 |

## 样本内结果

- **回测期**: 2020-01-01 → 2026-05-10
- **基准**: 上证综指 +35.48%
- **年化收益**: +91.98%
- **Sharpe**: 0.71
- **MaxDD**: -23.8%
- **胜率**: 50.8%
- **交易次数**: 77
- **排名**: 锦标赛第一

## OOS 结果

待补充：最新月份样本外表现。

## 成本敏感性

月度换手约 30-50%，手续费+滑点约 0.05%/交易。对总收益影响约 -2~-3%/年。对净收益影响有限。

## 失效场景

- 因子拥挤：多因子策略同质化导致 alpha 衰减
- 市场状态突变：月度调仓跟不上快速切换
- ROE 季度滞后：季报空窗期质量因子失真
- 估值陷阱：低 PE/PB 可能反映基本面恶化
