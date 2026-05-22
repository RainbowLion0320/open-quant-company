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

## 样本内结果

- **回测期**: 2020-01-01 → 2026-05-10
- **基准**: 上证综指 +35.48%
- **年化收益**: +70.28%
- **Sharpe**: 0.59
- **MaxDD**: -13.2%
- **胜率**: 50.3%
- **交易次数**: 77
- **排名**: 锦标赛第二

## OOS 结果

模型每周重训，天然具有 OOS 验证。最近一周重训后的 OOS 表现待记录。

## 成本敏感性

机器学习策略换手率约 40-70%/月，交易成本对净收益影响约为 -3~-5%/年。MaxDD 最低（-13.2%），回撤控制最优。

## 失效场景

- 过拟合：因子数量增加时 LightGBM 容易过拟合历史噪声
- 特征时效性：PIT 特征超过 3 个月后预测能力快速衰减
- 市场结构性变化：注册制改革、T+0 引入等结构性变化破坏历史规律
- 特征数据中断：PIT 特征构建依赖多数据源，任一数据源中断影响预测
- 模型退化：需要持续监控 IC 衰减趋势
