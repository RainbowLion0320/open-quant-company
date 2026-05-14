---
title: Cybernetics Regime Detection
created: 2026-05-12
updated: 2026-05-12
type: concept
tags: [cybernetics, market-regime, ma-alignment, position-sizing, sector-rotation]
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

具体仓位比例、止损幅度、最大持仓数均从 config 读取，每日自动重算。

## Sector Rotation

当 regime 切换时板块权重自动调整。配置中定义每种 regime 下的偏好行业（申万一级）。概念示例：

| Regime | 典型偏好 |
|--------|---------|
| Bull | 进攻型：证券、电子、计算机 |
| Bear | 防御型：银行、公用事业、食品饮料 |
| Sideways | 中性：银行、煤炭、建筑装饰 |

实际行业列表在 `cybernetic.sector_rotation` 中配置，可随时调整。

## Feedback Loop

1. **Sense**: 计算上证每日 MA 排列
2. **Decide**: 判定 regime，设置仓位/止损/上限
3. **Act**: 应用板块权重，过滤股票池
4. **Observe**: 跟踪信号质量，在 regime 持续超阈值时调整参数

## Integration

控制论协调器包裹 [[buffett-filter]] 池——不替代三重过滤，而是叠加 regime 自适应层。见 [[strategy-evolution]]。

## See Also

- [[buffett-filter]] — 底层选股池
- [[strategy-evolution]] — v3: 巴菲特 + 控制论
