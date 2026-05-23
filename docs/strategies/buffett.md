# 巴菲特价值精选

- **状态**: production
- **信号名**: buffett
- **运行器**: `scripts.compute_signals:compute_buffett`

## 概述

巴菲特价值投资策略，基于三重过滤：能力圈（行业白名单）→ 护城河（盈利能力+杠杆率）→ 安全边际（DCF估值 vs 现价）。面向全量 A 股股票池扫描，选出满足条件的深度价值标的。

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

## 结果来源

最新扫描、回测、OOS 和锦标赛结果不写死在策略文档中。查看：

- `data/store/signals/buffett*.parquet`
- `data/tournament/` 下的锦标赛 JSON
- Web `/strategy-lab` 页面

小样本股票池可能无法触发巴菲特筛选，正式扫描应使用当前配置中的全量股票池。

## 成本敏感性

低换手率（年均 < 2 次），交易成本影响极小。DCF 估值误差是主要风险。

## 失效场景

- 全面牛市：价值标的跑输成长股
- 会计准则变更：ROE/毛利率失真
- 行业政策剧变：能力圈内行业被颠覆
- 通货膨胀失控：DCF 折现率失效
