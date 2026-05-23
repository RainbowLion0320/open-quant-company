# 控制论自适应

- **状态**: production
- **信号名**: cybernetic
- **运行器**: `scripts.compute_signals:compute_cybernetic`

## 概述

钱学森控制论驱动的自适应策略。三级决策层次：市场环境（指数趋势+情绪+资金）→ 板块轮动（行业强度+板块资金+政策面）→ 个股筛选（基本面+技术面+估值）。根据市场状态（牛/熊/震荡）动态调整持仓数量、单仓比例和止损线。

## 数据依赖

| 维度 | 来源 | 频率 |
|------|------|------|
| ohlcv_daily | AKShare | daily |
| moneyflow_daily | AKShare | daily |
| adj_factor | AKShare | daily |

## 参数空间

| 参数 | 牛 | 熊 | 震荡 |
|------|-----|-----|------|
| max_positions | 8 | 2 | 5 |
| position_size | 30% | 5% | 15% |
| stop_loss | -8% | -3% | -5% |
| confidence_threshold | 0.6 | 0.85 | 0.75 |
| 反馈审查周期 | 30 天 | | |
| 最大连续亏损 | 3 次 | | |
| 最低胜率 | 35% | | |

## 结果来源

最新样本内/OOS/锦标赛结果不写死在策略文档中，避免与回测输出漂移。查看：

- `data/store/signals/cybernetic.parquet`
- `data/tournament/` 下的锦标赛 JSON
- Web `/strategy-lab` 页面

## 成本敏感性

牛市中换手率通常高于熊市和震荡市。具体费用影响以当前回测输出和交易成本配置为准。

## 失效场景

- 市场状态误判：日线噪声导致频繁切换牛/熊/震荡
- 反馈循环：连续止损触发自我怀疑机制，过度降低仓位
- 板块轮动失效：行业分类过于粗糙（申万一级 31 行业）
- 控制论模型在极端行情下可能过度适应历史模式
