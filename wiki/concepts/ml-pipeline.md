---
title: ML 管道 (端到端机器学习)
created: 2026-05-15
updated: 2026-05-15
type: concept
tags: [ML, LightGBM, PIT, Factor-DSL, Optuna, Tournament, LLM, Factor-Discovery]
---

# ML Pipeline

端到端机器学习管道：因子定义 → PIT特征构建 → 模型训练 → 生产部署 → 因子发现。

## 管道总览

```
┌──────────────────────────────────────────────────────┐
│ 1. 因子定义              signals/expression.py       │
│    26因子 (19 价量 + 7 LLM) DSL 声明式               │
│    alpha_factors() → dict[name, Factor]              │
├──────────────────────────────────────────────────────┤
│ 2. 特征构建             data/feature_store.py        │
│    PIT 月切片 → data/store/features/YYYY-MM.parquet  │
│    200股票 × 100月 × 26因子 = 520,000 数据点          │
├──────────────────────────────────────────────────────┤
│ 3. 模型训练             scripts/tune_model.py        │
│    LightGBM + Optuna + 滚动CV (48/6/12)              │
│    → data/models/data/models/lgbm_best.pkl                       │
├──────────────────────────────────────────────────────┤
│ 4. 模型评估             scripts/strategy_tournament.py│
│    4策略对比回测 → data/tournament/                   │
│    ML vs 巴菲特/多因子/控制论                          │
├──────────────────────────────────────────────────────┤
│ 5. 生产部署             signals/ml_signals.py        │
│    compute_signals.py → ml_lgbm 策略 → Parquet信号    │
│    cron 15:30 CST 每日扫描                            │
├──────────────────────────────────────────────────────┤
│ 6. 因子发现             scripts/factor_hypothesis.py │
│    LLM (deepseek-v4-pro) → DSL解析器 → IC评估         │
│    7/8 采纳 → alpha_factors()                        │
└──────────────────────────────────────────────────────┘
```

## 1. 因子 DSL

### 表达式引擎

命令式 → 声明式, 借鉴 Qlib ExpressionOps:

```python
# 之前 (手写循环)
mom_1m = close[-1] / close[-21] - 1

# 现在 (声明式)
mom_1m = Ref("close", -1) / Ref("close", -21) - 1
vol_20d = Std(Ret("close"), 20)
ma_golden = Gt(MA("close", 5), MA("close", 20))
```

支持操作符: `Ref`, `MA`, `Std`, `Delta`, `Ret`, `Gt`, `Lt`, `PctChange`, `RollingOp`, `BinOp`

### 当前 26 因子

| # | 名称 | 类别 | 公式 | 来源 |
|---|------|------|------|------|
| 1 | ret_1d | 收益 | `Ret("close", 1)` | Alpha158 |
| 2 | ret_5d | 收益 | `Ret("close", 5)` | Alpha158 |
| 3 | ret_20d | 收益 | `Ret("close", 20)` | Alpha158 |
| 4 | ret_60d | 收益 | `Ret("close", 60)` | Alpha158 |
| 5 | ma5_bias | 均线 | `close / MA(close,5) - 1` | Alpha158 |
| 6 | ma20_bias | 均线 | `close / MA(close,20) - 1` | Alpha158 |
| 7 | ma60_bias | 均线 | `close / MA(close,60) - 1` | Alpha158 |
| 8 | vol_5d | 波动 | `Std(Ret("close"), 5)` | Alpha158 |
| 9 | vol_20d | 波动 | `Std(Ret("close"), 20)` | Alpha158 |
| 10 | vol_60d | 波动 | `Std(Ret("close"), 60)` | Alpha158 |
| 11 | volume_ratio_5 | 量比 | `volume / MA(volume,5)` | Alpha158 |
| 12 | volume_ratio_20 | 量比 | `volume / MA(volume,20)` | Alpha158 |
| 13 | amplitude | 振幅 | `(high-low) / pre_close` | 自研 |
| 14 | high_low_ratio | 高低比 | `high / low` | 自研 |
| 15 | ma5_20_cross | 趋势 | `Gt(MA(close,5), MA(close,20)) as int` | Alpha158 |
| 16 | ma20_60_cross | 趋势 | `Gt(MA(close,20), MA(close,60)) as int` | Alpha158 |
| 17 | rsi_14 | 动量 | 14日 RSI | Alpha158 |
| 18 | fund_roe | 基本面 | ROE (TTM) | 同花顺 |
| 19 | fund_gross_margin | 基本面 | 毛利率 | 同花顺 |
| 20 | fund_de_ratio | 基本面 | 负债率 | 同花顺 |
| 21 | fund_roe_5y_avg | 基本面 | ROE 5年均值 | 自研 |
| 22 | fund_gm_trend | 基本面 | 毛利率趋势 | 自研 |
| 23 | val_pe | 估值 | PE (TTM) | Tushare |
| 24 | val_pb | 估值 | PB | Tushare |
| 25 | val_ps | 估值 | PS (TTM) | Tushare |
| 26 | val_pe_percentile | 估值 | PE 5年分位 | 自研 |
| 27 | vol_adj_mom_5d | **LLM** | `Delta(close,5) / Std(close,20)` | V4 Pro ★ |
| 28 | midpoint_bias | **LLM** | `(high+low)/2 / MA(close,20) - 1` | V4 Pro ★ |
| 29 | intraday_close_strength | **LLM** | `(close-low) / (high-low)` | V4 Pro ★ |
| 30 | volume_vol_ratio | **LLM** | `volume_ratio_20 / vol_20d` | V4 Pro ★ |
| 31 | volume_conviction | **LLM** | `volume / Std(volume,20)` | V4 Pro ★ |
| 32 | open_gap_ma20 | **LLM** | `(open-Ref(close,1)) / MA(close,20)` | V4 Pro ★ |
| 33 | upside_intraday_range | **LLM** | `(high-close) / Std(close,20)` | V4 Pro ★ |

注: 起始的 26=19 价量+7 LLM, 加上 8 基本面和 6 估值后实际共 33。本表列出完整 26 + 8 基本面 + 6 估值 = 40 特征。

## 2. PIT 特征存储

### 设计原则

- **Point-in-Time**: 每个 Parquet 文件只包含该月已知的数据
- **零前视**: `as_of` 限制严格, 回测时绝不使用未来信息
- **按月切片**: `data/store/features/YYYY-MM.parquet`

### 构建流程

```python
from data.feature_store import FeatureStoreBuilder
from signals.expression import alpha_factors

builder = FeatureStoreBuilder(alpha_factors())
# 单月构建
df = builder.build_month("2024-01", symbols=symbol_pool)

# 批量构建
builder.build_all("2015-01", "2026-05", symbols=symbol_pool)
# 产出: data/store/features/{2015-01..2026-05}.parquet
```

### 时间序列拆分

```python
from data.feature_store import TimeSeriesSplitter

splitter = TimeSeriesSplitter(
    train_len=48,  # 48个月训练
    test_len=6,    # 6个月测试
    step=12,       # 每12个月滚动
)
for train_months, test_months in splitter.split(all_months):
    train_X, train_y = load_month_range(train_months)
    model.fit(train_X, train_y)
    score = evaluate(test_months)
```

## 3. 模型训练

### 架构

`models/__init__.py` → `LightGBMRegressor` (首选) / `sklearn.ensemble.GradientBoostingRegressor` (macOS fallback)

```python
from models import LightGBMRegressor

model = LightGBMRegressor()
model.fit(X_train, y_train)
model.save("lgbm_best")
# → data/models/data/models/lgbm_best.pkl + registry.json
```

### 模型注册表

```json
// data/models/registry.json
{
  "lgbm_best": {
    "version": "v3",
    "ic_in_sample": 0.551,
    "n_features": 33,
    "training_date": "2026-05-15",
    "hyperparams": {"n_estimators": 200, "max_depth": 6, ...}
  }
}
```

### Optuna 超参数搜索

`scripts/tune_model.py`:
- 搜索空间: n_estimators [100,500], max_depth [3,10], learning_rate [0.01,0.2]
- 目标函数: 最大化滚动CV的 IC 均值
- 48月训练 / 6月测试 / 12月步长
- 最佳模型自动保存

**结果**: CV IC = 0.097 (vs Alpha158 基线 0.042, +2.3x)

## 4. 策略锦标赛

`scripts/strategy_tournament.py`:
- 输入: 策略注册表 → 4策略完整回测
- 输出: `data/tournament/tournament_{timestamp}.json` (排名 + 指标)
- 回测: 日频引擎, 每个策略自主决定调仓节奏

**最新结果** (2026-05-15):

| Rank | 策略 | 收益 | Sharpe | MaxDD | 交易 |
|:--:|------|------|--------|-------|:--:|
| 1 | LightGBM ML | +28.31% | 0.17 | -10.1% | 24 |
| 2 | 多因子 | +4.56% | -0.09 | -34.9% | 48 |
| 3 | 控制论 | +0.49% | -0.24 | -13.8% | 24 |

## 5. 生产部署

### ML 信号生成

`signals/ml_signals.py` → `compute_ml_signals(limit=100)`:
1. 加载 `data/models/lgbm_best.pkl`
2. 构建最新月特征
3. 预测评分 → 前 `limit` 只 → `buy` 信号
4. 存入 `data/store/signals/ml_lgbm.parquet`（cron 日频生成，非预置文件）

### Cron 集成

`scripts/compute_signals.py` 已注册 `ml_lgbm` 策略:
```python
STRATEGY_MAP = {
    "buffett": compute_buffett,
    "multifactor": compute_multifactor,
    "cybernetic": compute_cybernetic,
    "ml_lgbm": compute_ml,   # ★ Phase 4.0
}
```

Cron `job_id=934b4ecdca9f` — 每交易日 15:30 CST → 4策略并行扫描 → Telegram 推送。

## 6. LLM 因子发现

`scripts/factor_hypothesis.py` — AI 驱动的因子 R&D:

```
step 1: LLM 生成因子假说 (deepseek-v4-pro)
  → "波动率调整的短期动量 = 5日价格变化 / 20日波动率"

step 2: DSL 解析器翻译
  → compute_formula("Delta(close,5)/Std(close,20)", df)

step 3: IC 评估
  → 因子值 vs forward 20d return → Spearman IC

step 4: 判定
  → |IC| > 0.01 → 采纳 → alpha_factors()
  → |IC| ≤ 0.01 → 丢弃
```

**首轮结果** (2026-05-15):
- 输入: 8 个LLM提出的因子
- 通过: 7 个 (87.5%)
- Top IC: midpoint_bias (0.216), vol_adj_mom_5d (0.215)
- 已全部加入 `alpha_factors()` → 因子数量 19→26 (LLM贡献7个), PIT全特征40个(含基本面和估值)

### 发现的问题

因子从 19→26→33 后, in-sample IC 0.194→0.551 但锦标赛收益 36%→28%——**过拟合**。LLM 因子找到了历史数据的模式, 但 OOS 不成立。下一步需引入因子选择 (ICIR 过滤, 样本外验证)。

## 技术债务 & 下一步

- [ ] **因子选择**: ICIR 过滤替代简单 |IC| > 0.01 阈值
- [ ] **多轮迭代**: factor_hypothesis.py → 自动重复 → 收敛停止
- [ ] **周度再训练**: ML 模型 cron (尚未注册, 待观察 OOS 稳定性)
- [ ] **Regime 感知 ML**: 按市场状态分模型训练 (bull/bear/sideways)
- [ ] **特征重要性反馈**: 训练后自动报告 → 提示下一次 LLM 因子假说方向

## See Also

- [[ai-automation-roadmap]] — 三阶段路线图
- [[system-architecture]] — 含 ML 层的五层架构
- [[duckdb-migration]] — PIT 特征 Parquet 存储
- [[strategy-evolution]] — 策略回测历史
- [[financial-cache]] — 基本面/估值因子来源
