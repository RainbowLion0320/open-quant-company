---
title: Cybernetics Regime Detection
created: 2026-05-12
updated: 2026-05-26
type: concept
tags: [cybernetics, market-regime, ma-alignment, position-sizing, sector-rotation, rebalance-frequency]
---

# Cybernetics Regime Detection

市场状态检测——作为组合级别 risk-on/risk-off 风险预算开关，用来决定何时提高或降低市场 beta 暴露。灵感来自钱学森控制论：系统持续感知市场状态，通过反馈回路自适应调参。

**参数定义在 `config/settings.yaml` → `cybernetics.adaptive.detection`，生产公式常量定义在 `cybernetics/regime_policy.py`。**

## Regime Classification

| Regime | 条件 | 行为 |
|--------|------|------|
| **Bull** | confirmed score >= 60，且 trend 与 breadth 确认 | 提高权益/市场 beta 暴露 |
| **Bear** | confirmed score <= 40，或趋势与广度同时跌破防守阈值 | 降低权益暴露，转向现金/防御资产 |
| **Sideways** | 介于 bull/bear 之间或确认不足 | 中性配置 |

当前生产 champion 来自 V3 profit trainer：trend/breadth/risk/volume = 30/30/30/10，bull/bear 阈值 = 60/40，`min_dwell=3`。Regime score 不是单指数 MA 排列，而是多指数趋势、全市场宽度、风险/回撤波动和量能确认的组合分。

实时链路通过 `cybernetics/regime_state.py` 做状态稳定确认。Web/API 返回的 `value` 是 confirmed regime，`raw_value` 是单次快照原始分类，`stability` 显示 pending 状态。同一交易日重复刷新不累计 dwell，必须出现连续唯一市场观测后才切换 confirmed regime。

## Feedback Loop

1. **Sense**: 计算多指数趋势、全市场宽度、风险缓冲和量能确认
2. **Decide**: 先得到 raw regime，再经 `min_dwell` 状态机确认 confirmed regime，设置仓位/止损/上限
3. **Act**: 应用板块权重，过滤股票池
4. **Observe**: 跟踪信号质量，在 regime 持续超阈值时调整参数

## Rebalance 节奏

控制论策略的 `should_rebalance()` 实现 (`backtest/strategies/base.py` 子类):
- **月频**: 每月第一个交易日调仓
- **Regime 切换**: 额外触发 (月频 regime → 极少切换)
- **目标**: 月调仓 + regime 切换驱动的双触发

## Integration

控制论协调器包裹选股池——不替代底层过滤，而是叠加 regime 自适应层。

## See Also

- [[strategy-evolution]] — 四策略回测完整历史 (含 regime fix 前后对比)
- [[system-architecture]] — Regime 检测在五层架构中的位置
- [[buffett-filter]] — 底层选股池
