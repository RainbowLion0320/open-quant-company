---
title: AI 自动化交易框架路线图
created: 2026-05-14
updated: 2026-05-14
type: decision
tags: [AI, ML, RL, architecture, roadmap, strategy, factor-DSL, PIT, LightGBM, RD-Agent]
---

# AI 自动化交易框架路线图

从手调规则策略 → AI/ML 驱动的自动化 R&D 循环。借鉴 Microsoft Qlib 架构设计和 RD-Agent 自动化理念，在我们现有 Parquet 存储 + DuckDB 查询引擎基础上逐步演进。

## 背景

当前三策略（巴菲特 23.89% / 控制论 0.25% / 多因子 -5.15%）全部基于手写规则。多因子追涨杀跌暴露了手调规则的极限——没有系统性的因子发现、模型优化和自适应能力。

**目标**：搭建一个能自动发现因子、训练模型、优化策略、自适应市场的框架。不依赖 Qlib 生态，在其设计哲学上自建。

参考论文：RD-Agent-Quant (NeurIPS 2025) — 联合因子-模型优化，2x 收益，70% 更少因子，$10/cycle。

---

## Phase 3.0 — ML 基础设施 (地基)

### 3.0-1: Strategy 接口形式化

借鉴 Qlib `BaseStrategy`，定义标准策略接口：

```
class BaseStrategy:
    def score(self, symbol, features, date, regime) -> float
    def should_rebalance(self, date, regime, last_regime) -> bool  
    def get_positions(self, scores, holdings, capital) -> dict
```

现有三个策略改造为 BaseStrategy 子类，统一注册、测试、对比。

### 3.0-2: Exchange 成本模型

借鉴 Qlib `Exchange` 抽象，分离交易成本：

```
class AShareExchange:
    stamp_tax = 0.0005
    commission = 0.00025
    transfer_fee = 0.00001
    t_plus = 1
    def calc_buy_cost(self, price, shares) -> float
    def calc_sell_cost(self, price, shares) -> float
```

当前成本硬编码在 `run_all_strategies.py`，抽离后回测引擎更干净。

### 3.0-3: 因子 DSL 表达式引擎

借鉴 Qlib `ExpressionOps`，声明式因子表达：

```python
# 现在（命令式）
mom_1m = close[-1] / close[-21] - 1

# 目标（声明式）
mom_1m = Ref("close", -1) / Ref("close", -21) - 1
vol_20d = Std(Ret("close"), 20)
ma_cross = Gt(MA("close", 5), MA("close", 20))
```

好处：因子可组合、可缓存、可自动前视防护、可序列化。参考 Alpha158 的 158 个因子作为初始特征池。

### 3.0-4: Point-in-Time 特征存储

借鉴 Qlib PIT DB，每个数据点带时间戳标记何时可知：

```
data/store/features/
├── 2020-01.parquet   # 2020年1月已知的所有特征
├── 2020-02.parquet
└── ...
```

回测时按月切片，绝不使用未来数据。彻底杜绝前视偏差。

### 3.0-5: LightGBM 基线 + 时间序列 CV

- LightGBM 作为第一个 ML 模型（业界标准，比 GRU/LSTM 更稳健）
- 时间序列交叉验证（滚动窗口 train/valid/test）
- 目标：预测下月收益率排名（learning-to-rank）
- 评估指标：IC Rank, ICIR

---

## Phase 3.5 — 自动化 R&D 循环

### 3.5-1: Model Registry

```python
# 模型版本化
registry/
├── lgbm_v1_20260514.pkl    # 训练日期+版本
├── lgbm_v2_20260521.pkl
└── meta.json               # 元数据 (IC, Sharpe, 训练参数)
```

### 3.5-2: 超参数自动搜索

Optuna 驱动，搜索空间：num_leaves, learning_rate, feature_fraction, bagging_fraction。目标：最大化验证集 IC。

### 3.5-3: 策略锦标赛

每周自动对比：
- 巴菲特策略（不变基线）
- 多因子（当前手调）
- LightGBM vLatest（ML）
- 所有历史模型版本

胜者自动标记为"当前推荐"，cron 可切换到最优模型。

### 3.5-4: 周度 Cron

每周自动：re-train → evaluate vs baselines → 生成报告 → push Telegram。

---

## Phase 4.0 — AI Agent 驱动 (长期愿景)

### 4.0-1: LLM 因子假设生成

- 输入：最新研报、财经新闻、学术论文
- LLM：提出因子假设 ("earnings surprise + low volatility → alpha")
- 自动翻译为因子 DSL 表达式
- 验证：time-series CV → IC 评估

### 4.0-2: 因子-模型联合优化

借鉴 RD-Agent 核心逻辑：
- Research phase：LLM 提出 K 个候选因子
- Development phase：LightGBM 训练 + 评估
- Feedback：IC 排序 → 保留 top-K → 下一轮迭代
- 终止条件：连续 N 轮无提升

### 4.0-3: 自适应策略切换

- 每月评估所有策略的近期表现
- Regime 变化时自动切换最优策略
- "策略组合"替代"单一策略"

---

## 与现有系统的关系

```
手调策略（保留）               AI 策略（新增）
├─ buffett (年调仓)            ├─ lgbm_v1 (日预测, 月调仓)
├─ multifactor (月调仓)        ├─ lgbm_v2 (迭代优化)
└─ cybernetic (月+regime)      └─ ensemble (模型组合)
        │                              │
        └──────────┬───────────────────┘
                   ▼
         Strategy Registry (统一注册)
                   │
         run_all_strategies.py (统一回测)
                   │
         Web UI (统一对比展示)
```

AI 策略与手调策略平等竞争，均在注册表中管理，统一回测对比。

---

## 借鉴 Qlib 的设计模式

| Qlib 模式 | 我们的实现 | Phase |
|-----------|-----------|-------|
| BaseStrategy | `backtest/strategies/base.py` | 3.0-1 |
| Exchange | `broker/exchange.py` | 3.0-2 |
| ExpressionOps | `signals/expression.py` | 3.0-3 |
| PIT Database | `data/store/features/` | 3.0-4 |
| DataHandler | 保留现有 Parquet + DuckDB | ✅ 已有 |
| Backtest Analyzer | `backtest/analytics.py` | ✅ 已有 |
| Model Registry | `models/registry.py` | 3.5-1 |
| Workflow (qrun) | Makefile + compute_signals.py | ✅ 已有 |

## See Also

- [[strategy-evolution]] — 三策略回测结果
- [[duckdb-migration]] — Parquet 存储架构
- [[system-architecture]] — 系统五层架构
- [[financial-cache]] — 财务数据缓存
