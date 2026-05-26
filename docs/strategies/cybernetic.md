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

## Regime 研究训练

Market Regime 公式采用 champion/challenger 研究机制。当前生产 champion 是 V3 验证后的 `w0611`：trend/breadth/risk/volume = 30/30/30/10，bull/bear 阈值 = 60/40。`scripts/train_market_regime.py` 会离线搜索 challenger，并用历史回放、未来标签、walk-forward、组件消融和策略 A/B 判断是否值得人工审查。

运行报告存放在 `reports/regime_training/`。优先查看：

- `summary.json`：决策入口，包含 `keep_champion` / `recommend_challenger_for_review` / `insufficient_data`。
- `champion_vs_challenger.md`：当前公式与最优候选的解释性摘要。
- `candidate_search.csv`：候选规则排名。
- `walk_forward_results.csv`：滚动样本外窗口结果。
- `strategy_ab_test.csv`：固定仓位、当前公式、基线和最优候选的策略贡献。
- `recommended_config.yaml`：仅为人工审查建议，默认不会自动写回生产配置。

## Regime 挣钱导向训练

`scripts/train_market_regime_profit.py` 用更严格的目标训练 Market Regime：把它当作全局 risk-on/risk-off 风险预算信号，而不是选股策略评分器。训练器只使用本地可交易资产代理验证收益、回撤、Sharpe、Calmar、CAGR 和换手，不依赖当前个股策略的信号或 paper PnL。

运行报告存放在 `reports/regime_profit_training/`。优先查看：

- `summary.json`：决策入口，包含 `keep_champion` / `recommend_challenger_for_review` / `insufficient_data`，以及 champion/challenger 的核心收益指标。
- `profit_champion_vs_challenger.md`：收益导向的人类可读摘要。
- `baseline_comparison.csv`：buy-and-hold、固定仓位、均线择时、trend-only、trend+breadth、当前 champion、best challenger 的强基线对比。
- `walk_forward_profit_results.csv`：滚动样本外验证窗口，推荐结论必须由这里支撑。
- `candidate_profit_search.csv`：候选公式全样本排序，只能作为辅助，不作为最终晋级依据。
- `candidate_gate_diagnostics.csv`：每个公式的通过状态、失败 gate、低参与度等 warning，champion 也在同一张表里。
- `candidate_validation_summary.csv`：每个公式跨验证窗口相对 champion 的 OOS 汇总。
- `regime_distribution.csv`：检查候选是否坍缩为永久 risk-on 或永久 risk-off。
- `recommended_profit_config.yaml`：仅为人工审查建议，不会自动写回生产配置；生产替换需要同步修改生产评分、配置阈值和训练 champion。

V3 报告区分 `best_unconstrained_id` 和 `best_validated_id`。前者是原始收益指标最强公式，后者是通过 gate 后的当前最优候选；只有后者能进入人工替换审查。

## 成本敏感性

牛市中换手率通常高于熊市和震荡市。具体费用影响以当前回测输出和交易成本配置为准。

## 失效场景

- 市场状态误判：日线噪声导致频繁切换牛/熊/震荡
- 反馈循环：连续止损触发自我怀疑机制，过度降低仓位
- 板块轮动失效：行业分类过于粗糙（申万一级 31 行业）
- 控制论模型在极端行情下可能过度适应历史模式
