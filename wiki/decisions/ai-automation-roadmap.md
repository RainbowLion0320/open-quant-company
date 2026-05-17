---
title: AI 自动化交易框架路线图
created: 2026-05-14
updated: 2026-05-18
type: decision
tags: [AI, ML, RL, architecture, roadmap, strategy, factor-DSL, PIT, LightGBM, RD-Agent, LLM]
---

# AI 自动化交易框架路线图

从手调规则策略演进到 AI/ML 驱动的自动化 R&D 循环。本文只记录方向、约束和晋级门槛；当前进度、指标、样本量和任务状态以 git 提交、运行日志、`data/models/`、`data/tournament/`、`data/factor_scoreboard.py` 为准。

## 目标架构

```
DataHub/DataRegistry
  → PIT Feature Store
  → Model Training / Factor Research
  → Strategy Runtime Registry
  → Tournament / Paper Trading
  → Human or Agent Review
```

核心原则：
- 数据、特征、模型和策略输出必须可追溯到同一个配置版本和数据快照。
- LLM 可以提出因子和改动，但不能绕过 OOS、交易成本、回撤和稳定性验证。
- 研究结果进入生产前必须经过锦标赛、paper trading 和人工/agent review。

## 晋级门槛

### 因子晋级

- DSL 能被解析并在 PIT 数据上稳定计算。
- 不能是横截面常量，宏观变量只能作为条件或交互项。
- 通过 IC、ICIR、OOS 和滚动稳定性检查。
- 记录到因子记分板，后续可被淘汰。

### 模型晋级

- 训练元数据记录特征列表、训练窗口、参数、样本范围和保存时间。
- 使用时间序列滚动验证，避免随机切分造成前视偏差。
- 与当前生产模型做 A/B 或锦标赛对比。
- 明确特征新鲜度要求，过期特征不得静默参与生产信号。

### 策略晋级

- 注册在 `config/settings.yaml -> strategies`。
- 提供 runner 函数并由 `data/strategy_plugins.py` 调度。
- 输出标准信号行：`symbol/name/industry/score/signal/detail`。
- 回测、Web job、日频扫描、paper trading 使用同一策略运行入口。

## 优先级

### P1: 可信研究闭环

- 强化 `scripts/tune_model.py` 的模型元数据和 promotion gate。
- 让 `data/factor_scoreboard.py` 驱动自动淘汰候选因子。
- 对新旧模型输出做并行锦标赛，而不是覆盖式替换。

### P2: 数据广度和质量

- DataHub catalog 从 DataRegistry 派生，并记录 freshness、schema、owner。
- 慢速数据源通过后台任务积累，不阻塞日频扫描和 Web。
- ETF、债券、期货、加密资产必须先有真实数据契约，再接入策略。

### P3: 执行生产化

- 以事件账本表达 `SignalSet -> TargetPortfolio -> Orders -> Fills -> Positions -> NAV`。
- 回测、paper trading、未来实盘复用同一交易所、风控和成本模型。
- Agent 只提交可审查的改动和研究报告，不直接绕过风控执行。

## 瓶颈模型

| 风险 | 影响 | 设计回应 |
|------|------|----------|
| 网络数据源不稳定 | 数据缺口、任务卡住 | 缓存、超时、后台补拉、freshness gate |
| 因子过拟合 | 回测漂亮但实盘失效 | OOS、滚动窗口、记分板、淘汰机制 |
| 策略接口分裂 | 回测和生产不一致 | 统一 runtime registry |
| 执行模型分裂 | NAV 不可对账 | 事件账本 + 统一 broker/exchange |

## See Also

- [[ml-pipeline]] — ML 管道端到端方法
- [[system-architecture]] — 系统架构总览
- [[datahub]] — 数据中台决策
- [[strategy-evolution]] — 策略演进经验
