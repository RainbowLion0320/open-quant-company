# 巴菲特价值精选

- **状态**: production
- **信号名**: buffett
- **运行器**: `scripts.compute_signals:compute_buffett`

## 概述

巴菲特价值投资策略，基于三重过滤：能力圈（行业白名单）→ 护城河（盈利能力+杠杆率）→ 安全边际（DCF估值 vs 现价）。全量扫描 5517 只 A 股，选出满足条件的深度价值标的。

## 数据依赖

| 维度 | 来源 | 频率 |
|------|------|------|
| ohlcv_daily | AKShare | daily |
| financial_summary | AKShare | quarterly |
| fina_indicator | Tushare | quarterly |
| adj_factor | AKShare | daily |

## 参数空间

| 参数 | 值 | 说明 |
|------|-----|------|
| dcf_discount_rate | 8% | DCF 折现率 |
| growth_rate_terminal | 3% | 永续增长率 |
| safety_margin_pct | 30% | 安全边际折扣 |
| min_roe | 15% | 最低 ROE |
| min_roe_years | 5 | 连续盈利年数 |
| min_gross_margin | 30% | 最低毛利率 |
| max_debt_equity | 1.5 | 最高负债权益比 |
| 行业白名单 | 31 行业 | 排除金融/ST/亏损 |

## 样本内结果

- **回测期**: 2020-01-01 → 2026-05-10
- **基准**: 上证综指 +35.48%
- **年化收益**: +0.00%（50 股池不足以触发买入）
- **交易次数**: 77
- **注意**: 巴菲特策略在 50 股小池中几乎无法选出标的，需全量 5517 只运行。

## OOS 结果

全量扫描（2026-05-16, 5517 只）：
- 603288 海天味业 91 分
- 002415 海康威视 88 分
- 600036 招商银行 82 分

## 成本敏感性

低换手率（年均 < 2 次），交易成本影响极小。DCF 估值误差是主要风险。

## 失效场景

- 全面牛市：价值标的跑输成长股
- 会计准则变更：ROE/毛利率失真
- 行业政策剧变：能力圈内行业被颠覆
- 通货膨胀失控：DCF 折现率失效
