---
title: AI 自动化交易框架路线图
created: 2026-05-14
updated: 2026-05-15
type: decision
tags: [AI, ML, RL, architecture, roadmap, strategy, factor-DSL, PIT, LightGBM, RD-Agent, LLM]
---

# AI 自动化交易框架路线图

从手调规则策略 → AI/ML 驱动的自动化 R&D 循环。借鉴 Microsoft Qlib 架构设计和 RD-Agent 自动化理念，在我们现有 Parquet 存储 + DuckDB 查询引擎基础上逐步演进。

## 背景

当前四策略体系：手调规则 (巴菲特 / 控制论 / 多因子) + ML (LightGBM)。目标是搭建能自动发现因子、训练模型、优化策略、自适应市场的框架。

## 已完成 (截至 2026-05-15)

### Phase 3.0 — ML 基础设施 ✅

| 任务 | 状态 | 产出 |
|------|:--:|------|
| 3.0-1 Strategy 接口 | ✅ | `backtest/strategies/base.py` — BaseStrategy + StrategyRegistry |
| 3.0-2 Exchange 成本 | ✅ | `broker/exchange.py` — AShareExchange (印花税0.05%/佣金0.025%/过户费0.001%) |
| 3.0-3 因子 DSL | ✅ | `signals/expression.py` — 26因子声明式 (Ref/MA/Std/Delta/Ret/Gt/Lt/BinOp等19个Alpha因子) |
| 3.0-4 PIT 特征存储 | ✅ | `data/store/features/YYYY-MM.parquet` — 月切片零前视, `data/feature_store.py` 构建器 |
| 3.0-5 LightGBM | ✅ | `models/__init__.py` — LightGBMRegressor + sklearn GBR fallback (macOS libomp兼容) |

**验证**: 50股×6月 → 300行, IC=-0.12 (小样本预期内)

### Phase 3.5 — 自动化 R&D ✅

| 任务 | 状态 | 产出 |
|------|:--:|------|
| 3.5-1 Model Registry | ✅ | `models/__init__.py` — BaseModel + save/load/list_versions + `data/models/registry.json` |
| 3.5-2 Optuna 超参搜索 | ✅ | `scripts/tune_model.py` — 48月训练/6月测试/12月步长滚动CV |
| 3.5-3 策略锦标赛 | ✅ | `scripts/strategy_tournament.py` — 4策略自动对比 (回测+评分+导出JSON) |
| 3.5-4 ML 生产集成 | ✅ | `signals/ml_signals.py` + cron `scripts/compute_signals.py` 集成 ml_lgbm 策略 |

**结果**:
- Optuna 结果: 见 `data/models/lgbm_best_meta.json`。
- In-sample IC = 0.551
- 锦标赛 (100股 2020-2026): ML +28.31% / 多因子 +4.56% / 控制论 +0.49% / 巴菲特 n/a

### Phase 4.0 — AI Agent 驱动 (部分完成)

| 任务 | 状态 | 产出 |
|------|:--:|------|
| 4.0-1 LLM 因子生成 | ✅ | `scripts/factor_hypothesis.py` — deepseek-v4-pro 生成 → DSL解析器 → IC评估 |
| 4.0-2 因子-模型联合优化 | 🟡 | 单轮已验证，自动迭代循环尚未实现 |
| 4.0-3 自适应策略切换 | 🔜 | 待实现 |

LLM 因子研究结果: 见 `scripts/factor_hypothesis.py` 最新运行的输出。
- 8个候选因子 → 7个通过IC测试 (IC > 0.01)
- Top因子: `midpoint_bias` IC=0.216, `vol_adj_mom_5d` IC=0.215, `intraday_close_strength` IC=0.206
- $0.00/cycle (用自己的API key)
- 7个因子已加入 `alpha_factors()` → 26因子体系

**局限性**: ML +28.31% 低于纯LightGBM +36.22% (因子数13→26, 过拟合)。In-sample IC 0.194→0.551 但 OOS 下降, 验证了RD-Agent论文的发现：更多因子≠更好, 需要因子选择。

---

## 待实现

### Phase 4.0-2: 因子-模型联合优化循环

借鉴 RD-Agent 核心逻辑:
```
for round in range(max_rounds):
    1. Research: LLM 提出 K 个候选因子
    2. Development: LightGBM 训练 + 评估
    3. Feedback: IC 排序 → 保留 top-K
    4. 终止条件: 连续 N 轮无提升
```

当前单轮已通, 需添加:
- 多轮迭代 (阈值判断自动停止)
- 因子重要性 → 提示下一轮LLM ("exploited short-term volatility too much → suggest fundamental factors")
- 结果持久化 (因子历史表)

### Phase 4.0-3: 自适应策略切换

- 每月评估各策略近3-6月相对表现
- Regime变化时权重调整 (not equal-weight, dynamic)
- "策略组合"替代"单一策略"

---

## 与现有系统的关系

```
手调策略（保留）               AI 策略（已集成）
├─ buffett (年调仓)            ├─ ml_lgbm (日预测, 月调仓)
├─ multifactor (月调仓)        │   26因子 LightGBM
└─ cybernetic (月+regime)      │   锦标赛最优
        │                              │
        └──────────┬───────────────────┘
                   ▼
         Strategy Registry (4策略平等竞争)
                   │
         run_all_strategies.py (统一回测)
                   │
         Web UI (4策略曲线叠加, 点击高亮)
```

---

## Qlib 模式映射 (以我们实现为准)

| Qlib 模式 | 我们的实现 | 状态 |
|-----------|-----------|:--:|
| BaseStrategy | `backtest/strategies/base.py` | ✅ |
| Exchange | `broker/exchange.py` | ✅ |
| ExpressionOps | `signals/expression.py` (26因子) | ✅ |
| PIT Database | `data/store/features/YYYY-MM.parquet` | ✅ |
| DataHandler | Parquet + DuckDB `:memory:` | ✅ |
| Backtest Analyzer | `backtest/analytics.py` (15项指标) | ✅ |
| Model Registry | `models/__init__.py` + `data/models/registry.json` | ✅ |
| Workflow (qrun) | Makefile + scripts/compute_signals.py (cron) | ✅ |
| RD-Agent | `scripts/factor_hypothesis.py` | 🟡 单轮 |

## See Also

- [[ml-pipeline]] — ML管道端到端文档
- [[system-architecture]] — 系统五层架构 (含ML层)
- [[strategy-evolution]] — 四策略回测结果
- [[duckdb-migration]] — Parquet 存储架构
