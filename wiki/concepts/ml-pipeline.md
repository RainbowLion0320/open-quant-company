---
title: ML 管道 (端到端机器学习)
created: 2026-05-15
updated: 2026-05-18
type: concept
tags: [ML, LightGBM, PIT, Factor-DSL, Optuna, Tournament, LLM, Factor-Discovery]
---

# ML Pipeline

端到端机器学习管道：因子定义 → PIT 特征构建 → 模型训练 → 生产部署 → 因子发现。本文描述稳定方法和接口，不记录当前 IC、因子数量、样本量或 cron id；这些动态事实以源码、模型元数据和运行产物为准。

## 管道总览

```
signals/expression.py
  → scripts/build_features.py
  → scripts/tune_model.py
  → scripts/strategy_tournament.py
  → signals/ml_signals.py
  → data/store/signals/ml_lgbm.parquet
```

## 1. 因子 DSL

因子由 `signals/expression.py::alpha_factors()` 定义。新增因子应满足：

- 可用已有 DSL 算子表达，或明确新增算子的语义。
- 不依赖未来数据。
- 对空值、停牌、缺列和极端值有明确处理。
- 在进入模型前通过 `data/cleaner.py` 和 PIT 特征构建流程。

示例：

```python
mom_1m = Ref("close", -1) / Ref("close", -21) - 1
vol_20d = Std(Ret("close"), 20)
ma_golden = Gt(MA("close", 5), MA("close", 20))
```

实际因子清单以 `alpha_factors()` 和特征文件列为准。

## 2. PIT 特征存储

特征按月切片到 `data/store/features/YYYY-MM.parquet`。构建入口是 `scripts/build_features.py`，必须通过 CLI 或显式函数调用启动，不能在 import 时执行重任务。

关键约束：

- 每个特征只使用 `as_of` 之前可获得的数据。
- 前向标签使用固定交易日跨度，不能用自然日窗口漂移。
- 构建区间、样本数、是否覆盖已有切片由 CLI 参数控制。
- 生产推理需要检查特征新鲜度，过期特征不能静默使用。

## 3. 模型训练

模型层在 `models/__init__.py`，训练入口在 `scripts/tune_model.py`。

训练要求：

- `prepare_xy()` 丢弃缺失目标，不把未知未来收益填 0。
- 使用时间序列滚动验证。
- 保存模型文件和元数据，包括特征名、样本数、参数、训练时间和评估摘要。
- promotion 前需要和当前生产模型做对比。

## 4. 策略锦标赛

`scripts/strategy_tournament.py` 用于比较策略表现，输出写入 `data/tournament/`。锦标赛结果是动态产物，不复制到 wiki。

锦标赛应验证：

- 收益、回撤、Sharpe、胜率和交易次数。
- 换手率、成本、容量和持仓集中度。
- 与 paper trading 执行模型的一致性。

## 5. 生产部署

`signals/ml_signals.py` 负责生产信号：

1. 加载模型和元数据。
2. 选择最新且不过期的 PIT 特征文件。
3. 按模型特征名构建输入矩阵。
4. 生成标准信号行。
5. 由 `data/strategy_plugins.py` 统一持久化。

如果特征文件过期或覆盖不足，系统应显式告警或跳过，而不是用缺失值默默补 0。

## 6. LLM 因子发现

`scripts/factor_hypothesis.py` 负责 LLM 因子假说：

```
LLM hypothesis
  → DSL formula
  → PIT/OOS evaluation
  → factor_scoreboard
  → optional auto-register
```

LLM 因子必须防止两类常见错误：

- 横截面常量：宏观变量直接作为主信号。
- 历史过拟合：in-sample 提升但 OOS 或锦标赛退化。

## 技术债务

- 模型晋级需要更正式的 artifact manifest。
- 因子记分板需要驱动自动淘汰，而不是只做记录。
- 回测和 paper trading 需要统一执行账本，避免研究收益和模拟 NAV 不可对账。

## See Also

- [[ai-automation-roadmap]] — AI 自动化路线图
- [[system-architecture]] — 系统架构总览
- [[duckdb-migration]] — PIT 特征 Parquet 存储
- [[financial-cache]] — 基本面/估值因子来源
