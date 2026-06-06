# LightGBM ML

- **状态**: paper
- **信号名**: ml_lgbm
- **运行器**: `signals.ml_signals:compute_ml_signals`

## 概述

基于 LightGBM 的机器学习选股策略。使用 PIT（Point-in-Time）特征切片训练，支持分市场状态（牛/熊/震荡）的 regime-aware 模型。每周六自动重训，日频预测。

当前定位为辅助 Alpha，不直接作为 production 主策略。进入 production 前必须通过策略晋级门槛：足够 OOS 月数、交易次数、Sharpe、最大回撤、换手、IC 和 ICIR。

运行时模型加载由 `models/lgbm_runtime.py` 统一处理。生产信号和回测都会优先加载 regime-aware 模型；regime 专属模型文件名为 `lgbm_{regime}.pkl`，元数据为 `lgbm_{regime}_meta.json`。

## 数据依赖

| 维度 | 来源 | 频率 |
|------|------|------|
| ohlcv_daily (qfq via PriceService) | AKShare + adj_factor | daily |
| financial_summary | AKShare | quarterly |
| fina_indicator | Tushare | quarterly |
| adj_factor | Tushare | daily |
| valuation_daily | Tushare | daily |
| moneyflow_daily | AKShare | daily |
| features_all (PIT) | Computed | daily as-of |

## 参数空间

| 参数 | 值 | 说明 |
|------|-----|------|
| use_regime_models | true | 分市场状态模型 |
| feature_frequency | daily | PIT 特征目标粒度 |
| max_feature_age_months | 3 | 特征最大时效 |
| score_scale | 5.0 | Sigmoid 压缩系数 |
| allow_stale_features | false | 过期特征处理 |
| allow_live_factor_fallback | false | 实时因子回退 |

价格口径权威来源为 `data/market/price_service.py`。PIT 特征、信号和回测使用 `PriceUseCase.RESEARCH/SIGNAL/BACKTEST` 的 `qfq` 口径，实时执行和估值路径另走 `raw`。

## 回测路径

回测入口 `backtest/run_all_strategies.py --strategy ml_lgbm` 使用 `MLFeatureStoreAlphaModel`，按调仓日选择不晚于该日的最新 PIT as-of 特征视图一次性批量预测全股票池，再交给统一 Pipeline 执行组合构建、风控和成交模拟。不要退回通用逐股 `StrategyAlphaAdapter`，否则正式全池回测会退化为数千只股票逐个 `predict()`。

日频价量、估值和资金流特征使用 `scripts/build_features.py --frequency daily` 构建到 `var/store/features/YYYY-MM-DD.parquet`。`YYYY-MM.parquet` 月末切片不是正式输入。

特征矩阵进入模型前会统一 `to_numeric(errors="coerce")`，再处理 `inf`/`nan`，避免 Parquet 中对象类型列导致 LightGBM 拒绝预测。

## 结果来源

最新样本内/OOS/锦标赛结果不写死在策略文档中，避免与模型和回测输出漂移。查看：

- `var/artifacts/models/` 下的模型元数据
- `var/store/signals/ml_lgbm.parquet`
- `var/artifacts/tournaments/` 下的锦标赛 JSON
- Web `/strategy-lab` 页面

## 成本敏感性

机器学习策略可能有较高换手率，交易成本敏感性以当前回测输出和交易成本配置为准。需要持续关注预测分数分布、IC 衰减和实际换手。

## 失效场景

- 过拟合：因子数量增加时 LightGBM 容易过拟合历史噪声
- 特征时效性：PIT 特征超过 3 个月后预测能力快速衰减
- 市场结构性变化：注册制改革、T+0 引入等结构性变化破坏历史规律
- 特征数据中断：PIT 特征构建依赖多数据源，任一数据源中断影响预测
- 模型退化：需要持续监控 IC 衰减趋势
