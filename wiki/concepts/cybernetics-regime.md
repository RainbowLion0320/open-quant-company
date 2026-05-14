---
title: Cybernetics Regime Detection
created: 2026-05-12
updated: 2026-05-15
type: concept
tags: [cybernetics, market-regime, ma-alignment, position-sizing, sector-rotation, rebalance-frequency]
---

# Cybernetics Regime Detection

市场状态检测——通过上证指数均线排列（MA5/MA20/MA60）判定牛熊，自适应调节仓位和止损。灵感来自钱学森控制论：系统持续感知市场状态，通过反馈回路自适应调参。

**参数定义在 `config/settings.yaml` → `cybernetic` 段。**

## Regime Classification

| Regime | 条件 | 行为 |
|--------|------|------|
| **Bull** | close > MA5 > MA20 > MA60 | 高仓位、宽止损、多持仓 |
| **Bear** | close < MA5 < MA20 < MA60 | 低仓位、紧止损、少持仓 |
| **Sideways** | 其他排列 | 中性配置 |

具体仓位比例、止损幅度、最大持仓数均从 config 读取。

## Monthly Regime Fix (v3.4, 2026-05-14)

**问题**: 回测引擎以日频遍历时, 每日重新判定 regime 导致 regime 在 bull/bear/sideways 间高频翻转。实际交易中 regime 判断应基于月级别趋势, 不应每日改变。后果: 控制论策略过度交易 (5974笔/100只 vs buffett 9笔), 回测收益 -5.85%。

**修复**: Regime 检测从日线 MA 排列改为月线 K 线预计算:

```python
# 旧 (日频, 导致 regime 翻转)
def detect_regime(date):
    prices = prices_df.loc[:date]
    ma5 = prices["close"].rolling(5).mean().iloc[-1]
    # → bull on day 15, bear on day 17, bull on day 18...

# 新 (月频, regime 稳定)
regime_cache = {}  # 在回测开始时预计算
for month in all_months:
    monthly_close = prices_df["close"].resample("M").last()
    regime_cache[month] = classify(monthly_close)

# 回测中仅查表
def detect_regime(date):
    return regime_cache[date.strftime("%Y-%m")]
```

**Impact on Rebalance**: 控制论策略的 `should_rebalance` 逻辑:
- 每月调仓 (monthly, 月初第一天)
- Regime 切换时额外触发调仓
- 月频 regime → 切换事件大幅减少 → 交易量暴跌

**结果** (100只，2020-2026):

| 版本 | 收益 | 交易笔数 | 问题 |
|------|------|:--:|------|
| Daily regime (旧) | -5.85% | 5974 | regime 翻转导致过度交易 |
| Monthly regime (新) | **+10.07%** | 42 | ✓ |

1000只全量: 控制论 +0.25% (268笔), 大幅改善。

## Feedback Loop

1. **Sense**: 计算上证月线 MA 排列 (预计算, 月频稳定)
2. **Decide**: 判定 regime，设置仓位/止损/上限
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
