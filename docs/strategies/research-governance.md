# 策略研究治理

- **状态**: 已启用治理模块
- **模块**: `research.strategy_governance`, `signals.factor_research`, `pipeline.portfolio.ConstrainedPortfolioConstructor`

## 策略分层

| 策略 | 层级 | 主要用途 |
|------|------|----------|
| buffett | quality_filter | 财务质量和安全边际过滤，不作为高频 Alpha |
| multifactor | primary_alpha | 当前主 Alpha，负责横截面排序和候选生成 |
| ml_lgbm | auxiliary_alpha | 辅助 Alpha，捕捉非线性关系，需严格 OOS/IC 门槛 |
| cybernetic | risk_overlay | 市场状态、仓位、风险预算和资产配置 |

## 晋级门槛

`evaluate_promotion()` 对 validated / paper / production 三个目标状态检查：

- OOS 月数
- 交易次数
- Sharpe
- 最大回撤
- 年化换手
- IC
- ICIR

ML 当前保持 `paper` 状态。只有样本外稳定性和 IC 证据达标后，才应晋级为 production。

## 因子研究

`signals.factor_research` 提供：

- `rank_ic_by_period()`：逐期横截面 Spearman IC。
- `factor_diagnostics()`：mean IC、ICIR、正 IC 占比、分组收益 spread、单调性。
- `factor_correlation_clusters()`：识别高度相关因子，避免重复暴露。

## 组合构建

`ConstrainedPortfolioConstructor` 在 Top-N 选股基础上增加：

- 单票权重上限
- 行业权重上限
- 总部署仓位上限
- lot size 取整

后续策略优化优先接入这套组合构建，而不是继续扩大 Top-N 等权的参数空间。
