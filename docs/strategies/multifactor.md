# 多因子月度调仓

- **状态**: production
- **信号名**: multifactor
- **运行器**: `scripts.compute_signals:compute_multifactor`

## 概述

五维加权打分系统：质量（Buffett 分数 + ROE + ROE 趋势）+ 估值（安全边际分层）+ 技术（skip-1m 动量 + 趋势确认 + 波动率）+ 市场（regime 下的板块适配）+ 行业动量（申万行业 20D/60D 动量）。月度调仓，Top 10 等权。

## 数据依赖

| 维度 | 来源 | 频率 |
|------|------|------|
| ohlcv_daily (qfq via PriceService) | AKShare + adj_factor | daily |
| financial_summary | AKShare | quarterly |
| fina_indicator | Tushare | quarterly |
| adj_factor | Tushare | daily |
| valuation_daily | Tushare | daily |
| sector_membership_snapshot | computed | daily |
| sector_performance_snapshot | computed | daily |

## 参数空间

| 参数 | 值 | 说明 |
|------|-----|------|
| buy_threshold | 52 | 最低买入分 |
| quality_weight | 0.35 | 质量权重 |
| valuation_weight | 0.25 | 估值权重 |
| technical_weight | 0.15 | 技术权重 |
| market_weight | 0.10 | 市场权重 |
| industry_momentum_weight | 0.15 | 行业动量权重 |
| top_n | 10 | 持仓数量 |
| rebalance_interval | ~20 交易日 | 月度调仓 |
| score_base | 50 | 基准分 |

参数权威来源为 `config/settings.yaml` → `signals.multifactor`，上表只记录当前默认值。

价格口径权威来源为 `data/price_service.py`。研究、信号和回测使用 `PriceUseCase.SIGNAL/BACKTEST` 的 `qfq` 口径，执行和估值路径另走 `raw`。

## 结果来源

最新样本内/OOS/锦标赛结果不写死在策略文档中，避免和回测输出漂移。查看：

- `data/tournament/` 下的锦标赛 JSON
- `data/store/signals/multifactor.parquet`
- Web `/strategy-lab` 页面

## 成本敏感性

月度换手约 30-50%，手续费+滑点约 0.05%/交易。对总收益影响约 -2~-3%/年。对净收益影响有限。

## 失效场景

- 因子拥挤：多因子策略同质化导致 alpha 衰减
- 市场状态突变：月度调仓跟不上快速切换
- ROE 季度滞后：季报空窗期质量因子失真
- 估值陷阱：低 PE/PB 可能反映基本面恶化
- 行业动量漂移：行业快照缺失或行业成员映射滞后时，行业维回退到中性分，可能降低轮动敏感度
