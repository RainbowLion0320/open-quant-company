# LightGBM ML

- **状态**: production
- **信号名**: ml_lgbm
- **运行器**: `signals.ml_signals:compute_ml_signals`

## 概述

基于 LightGBM 的机器学习选股策略。使用 PIT（Point-in-Time）特征切片训练，支持分市场状态（牛/熊/震荡）的 regime-aware 模型。每周六自动重训，日频预测。

## 数据依赖

| 维度 | 来源 | 频率 |
|------|------|------|
| ohlcv_daily | AKShare | daily |
| financial_summary | AKShare | quarterly |
| fina_indicator | Tushare | quarterly |
| adj_factor | AKShare | daily |
| valuation_daily | Tushare | daily |
| moneyflow_daily | AKShare | daily |
| features_all (PIT) | Computed | monthly |

## 参数空间

| 参数 | 值 | 说明 |
|------|-----|------|
| use_regime_models | true | 分市场状态模型 |
| max_feature_age_months | 3 | 特征最大时效 |
| score_scale | 5.0 | Sigmoid 压缩系数 |
| allow_stale_features | false | 过期特征处理 |
| allow_live_factor_fallback | false | 实时因子回退 |

## 结果来源

最新样本内/OOS/锦标赛结果不写死在策略文档中，避免与模型和回测输出漂移。查看：

- `data/models/` 下的模型元数据
- `data/store/signals/ml_lgbm.parquet`
- `data/tournament/` 下的锦标赛 JSON
- Web `/strategies` 与 `/backtest` 页面

## 成本敏感性

机器学习策略可能有较高换手率，交易成本敏感性以当前回测输出和交易成本配置为准。需要持续关注预测分数分布、IC 衰减和实际换手。

## 失效场景

- 过拟合：因子数量增加时 LightGBM 容易过拟合历史噪声
- 特征时效性：PIT 特征超过 3 个月后预测能力快速衰减
- 市场结构性变化：注册制改革、T+0 引入等结构性变化破坏历史规律
- 特征数据中断：PIT 特征构建依赖多数据源，任一数据源中断影响预测
- 模型退化：需要持续监控 IC 衰减趋势
