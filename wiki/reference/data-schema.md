---
title: Data Schema — 数据库完整结构
created: 2026-05-18
updated: 2026-05-18
type: reference
tags: [data, parquet, schema, database]
---

# Data Schema — 数据库完整结构

> 所有 Parquet 表的列定义、类型、示例。与 `wiki/reference/data-dimensions.md`（维度总表）互补——那篇回答「有哪些维度」，这篇回答「每个维度长什么样」。

---

## 1. OHLCV 日线行情 (per-symbol)

**存储**: `data/store/stock/daily/{symbol}.parquet` (单只股票，Sina 源)
**来源**: `scripts/cron_fetch_ohlcv.py` → `data/fetchers/stock_daily.py` → AKShare `stock_zh_a_daily`

| 列名 | 类型 | 说明 |
|------|------|------|
| date | str | 交易日期 YYYY-MM-DD |
| open | float64 | 开盘价 |
| high | float64 | 最高价 |
| low | float64 | 最低价 |
| close | float64 | 收盘价 |
| volume | float64 | 成交量 (手) |
| amount | float64 | 成交额 (元) |
| outstanding_share | float64 | 流通股本 |
| turnover | float64 | 换手率 |

---

## 2. 同花顺财务摘要 (per-symbol)

**存储**: `data/store/stock/financials/{symbol}.parquet`
**来源**: `scripts/cron_fetch_financials.py` → `data/fetchers/financial.py` → AKShare `stock_financial_abstract_ths`

| 列名 | 类型 | 说明 |
|------|------|------|
| 报告期 | str | 报告期 YYYY-MM-DD |
| 净利润 | str | 归属净利润 |
| 净利润同比增长率 | str | 净利润 YoY |
| 扣非净利润 | str | 扣非净利润 |
| 扣非净利润同比增长率 | str | 扣非 YoY |
| 营业总收入 | str | 营业收入 |
| 营业总收入同比增长率 | str | 营收 YoY |
| 基本每股收益 | str | EPS |
| 每股净资产 | str | BVPS |
| 每股资本公积金 | str | |
| 每股未分配利润 | str | |
| 每股经营现金流 | str | |
| 销售净利率 | str | |
| 销售毛利率 | str | |
| 净资产收益率 | str | ROE |
| 净资产收益率-摊薄 | str | ROE (diluted) |
| 营业周期 | str | |
| 存货周转率 | str | |
| 存货周转天数 | str | |
| 应收账款周转天数 | str | |
| + 5 more | str | (variable) |

> 注: 所有值为字符串类型，需自行 cast。

---

## 3. PIT 特征月度切片

**存储**: `data/store/features/{YYYY-MM}.parquet`
**每行**: 一只股票在某月的特征向量  
**来源**: `scripts/build_features.py` → `data/feature_store.py::enrich`

| 列名 | 类型 | 类别 | 说明 |
|------|------|------|------|
| symbol | str | ID | 股票代码 6 位 |
| month | str | ID | 月份 YYYY-MM |
| ret_1d | float64 | 收益 | 1 日收益 |
| ret_5d | float64 | 收益 | 5 日收益 |
| ret_10d | float64 | 收益 | 10 日收益 |
| ret_20d | float64 | 收益 | 20 日收益 |
| ret_60d | float64 | 收益 | 60 日收益 |
| ma5_bias | float64 | 技术 | MA5 偏离度 |
| ma10_bias | float64 | 技术 | MA10 偏离度 |
| ma20_bias | float64 | 技术 | MA20 偏离度 |
| ma60_bias | float64 | 技术 | MA60 偏离度 |
| vol_5d | float64 | 波动 | 5 日波动率 |
| vol_20d | float64 | 波动 | 20 日波动率 |
| vol_60d | float64 | 波动 | 60 日波动率 |
| volume_ratio_5 | float64 | 量价 | 5 日量比 |
| volume_ratio_20 | float64 | 量价 | 20 日量比 |
| amplitude | float64 | 量价 | 振幅 |
| high_low_ratio | float64 | 量价 | 最高/最低比 |
| ma5_20_cross | float64 | 技术 | MA5/MA20 交叉 |
| ma20_60_cross | float64 | 技术 | MA20/MA60 交叉 |
| rsi_14 | float64 | 技术 | RSI(14) |
| vol_adj_mom_5d | float64 | 量价 | 量调动量 |
| volume_conviction | float64 | 量价 | 量能确信度 |
| intraday_close_strength | float64 | 量价 | 日内收盘强度 |
| upside_intraday_range | float64 | 量价 | 日内上行空间 |
| midpoint_bias | float64 | 量价 | 中点偏离度 |
| volume_vol_ratio | float64 | 量价 | 量/波动比 |
| open_gap_ma20 | float64 | 量价 | 开盘与 MA20 偏离 |
| fund_roe | float64 | 基本面 | ROE |
| fund_gross_margin | float64 | 基本面 | 毛利率 |
| fund_net_margin | float64 | 基本面 | 净利率 |
| fund_de_ratio | float64 | 基本面 | 资产负债率 |
| fund_net_profit | float64 | 基本面 | 净利润 |
| fund_roe_5y_avg | float64 | 基本面 | 5 年平均 ROE |
| fund_gm_trend | float64 | 基本面 | 毛利率趋势 |
| mf_net_amount | float64 | 资金 | 主力净流入 |
| mf_inst_net | float64 | 资金 | 机构净流入 |
| mf_smart_ratio | float64 | 资金 | 聪明钱占比 |
| holder_change_pct | float64 | 股东 | 股东户数变化率 |
| holder_concentration | float64 | 股东 | 股东集中度 |
| macro_pmi | float64 | 宏观 | PMI |
| macro_shibor_3m | float64 | 宏观 | Shibor 3M |
| macro_shibor_on | float64 | 宏观 | Shibor O/N |
| macro_cpi | float64 | 宏观 | CPI |
| val_pe | float64 | 估值 | PE |
| val_pe_ttm | float64 | 估值 | PE(TTM) |
| val_pb | float64 | 估值 | PB |
| val_ps | float64 | 估值 | PS |
| val_dv_ratio | float64 | 估值 | 股息率 |
| val_pe_percentile | float64 | 估值 | PE 历史分位 |
| val_total_mv | float64 | 估值 | 总市值 |
| val_circ_mv | float64 | 估值 | 流通市值 |

实际列数以 `scripts/build_features.py` 产出的当月 Parquet 为准。

---

## 4. 宏观数据

### 4.1 CPI (Tushare 源, 月频)

**存储**: `data/store/macro/cpi.parquet`  
**来源**: Tushare `cn_cpi` (国家统计局) → AKShare `macro_china_cpi_yearly`(金十, 已停更, 仅历史回退)

| 列名 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 月份 (YYYY-MM-01) |
| nt_val | float64 | 全国 CPI 当月值 |
| nt_yoy | float64 | 全国 CPI 同比 (%) |
| nt_mom | float64 | 全国 CPI 环比 (%) |
| nt_accu | float64 | 全国 CPI 累计 |
| town_val | float64 | 城市 CPI 当月值 |
| town_yoy | float64 | 城市 CPI 同比 |
| town_mom | float64 | 城市 CPI 环比 |
| town_accu | float64 | 城市 CPI 累计 |
| cnt_val | float64 | 农村 CPI 当月值 |
| cnt_yoy | float64 | 农村 CPI 同比 |
| cnt_mom | float64 | 农村 CPI 环比 |
| cnt_accu | float64 | 农村 CPI 累计 |

> 注: AKShare 金十数据源已于 2025-09 停更。切换至 Tushare，数据范围 1990-01 ~ 至今。

### 4.2 PPI / PMI (Tushare 源, 月频)

**PPI 存储**: `data/store/macro/ppi.parquet`  
**来源**: Tushare `cn_ppi` (国家统计局)  
**主列**: date, ppi_yoy (同比), ppi_mp_yoy (生产资料), ppi_cg_yoy (生活资料) 等  

**PMI 存储**: `data/store/macro/pmi.parquet`  
**来源**: Tushare `cn_pmi` (国家统计局)  
**主列**: date, pmi_mfg (制造业 PMI)

> 注: PPI/PMI 同样从 AKShare 金十切换至 Tushare，数据范围 2005-01 ~ 至今。

### 4.3 GDP / 货币供应量 / LPR / Shibor (AKShare 源)

**存储**: `data/store/macro/money_supply.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 日期 |
| M2_stock | float64 | M2 存量 |
| M2_yoy | float64 | M2 同比 |
| M1_stock | float64 | M1 存量 |
| M1_yoy | float64 | M1 同比 |
| M0_stock | float64 | M0 存量 |
| M0_yoy | float64 | M0 同比 |

### 4.3 LPR

**存储**: `data/store/macro/lpr.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 日期 |
| LPR_1Y | float64 | 1 年期 LPR |
| LPR_5Y | float64 | 5 年期 LPR |
| RATE_1 | float64 | 参考利率 1 |
| RATE_2 | float64 | 参考利率 2 |

### 4.4 Shibor

**存储**: `data/store/macro/shibor.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 日期 |
| O/N-定价 | float64 | 隔夜 |
| O/N-涨跌幅 | float64 | |
| 1W-定价 | float64 | 1 周 |
| 1W-涨跌幅 | float64 | |
| 2W-定价 | float64 | 2 周 |
| 2W-涨跌幅 | float64 | |
| 1M-定价 | float64 | 1 月 |
| 1M-涨跌幅 | float64 | |
| 3M-定价 | float64 | 3 月 |
| 3M-涨跌幅 | float64 | |
| 6M-定价 | float64 | 6 月 |
| 6M-涨跌幅 | float64 | |
| 9M-定价 | float64 | 9 月 |
| 9M-涨跌幅 | float64 | |
| 1Y-定价 | float64 | 1 年 |
| 1Y-涨跌幅 | float64 | |

---

## 5. 国债收益率曲线

**存储**: `data/store/bond/treasury_yields.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| 日期 | str | 日期 |
| 中国国债收益率2年 | float64 | |
| 中国国债收益率5年 | float64 | |
| 中国国债收益率10年 | float64 | |
| 中国国债收益率30年 | float64 | |
| 中国国债收益率10年-2年 | float64 | 利差 |
| 中国GDP年增率 | float64 | |
| 美国国债收益率2年 | float64 | |
| 美国国债收益率5年 | float64 | |
| 美国国债收益率10年 | float64 | |
| 美国国债收益率30年 | float64 | |
| 美国国债收益率10年-2年 | float64 | 利差 |
| 美国GDP年增率 | float64 | |

---

## 6. 股东户数 (per-symbol)

**存储**: `data/store/stock/holders/{symbol}.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| ts_code | str | Tushare 代码 (如 000001.SZ) |
| ann_date | datetime64 | 公告日期 |
| end_date | datetime64 | 截止日期 |
| holder_num | int64 | 股东户数 |

---

## 7. 股东增减持 (per-symbol)

**存储**: `data/store/stock/holdertrade/{symbol}.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| ts_code | str | Tushare 代码 |
| ann_date | datetime64 | 公告日期 |
| holder_name | str | 股东名称 |
| holder_type | str | C(公司)/P(个人)/G(高管) |
| in_de | str | IN(增持)/DE(减持) |
| change_vol | float64 | 变动数量 |
| change_ratio | float64 | 变动比例 |
| after_share | float64 | 变动后持股 |
| after_ratio | float64 | 变动后比例 |
| avg_price | float64 | 均价 |
| total_share | float64 | 总股本 |

---

## 8. 资金流向每日 (per-symbol)

**存储**: `data/store/stock/moneyflow/{symbol}.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| 日期 | datetime64 | |
| 收盘价 | float64 | |
| 涨跌幅 | float64 | |
| 主力净流入-净额 | float64 | 主力资金净额 |
| 主力净流入-净占比 | float64 | |
| 超大单净流入-净额 | float64 | |
| 超大单净流入-净占比 | float64 | |
| 大单净流入-净额 | float64 | |
| 大单净流入-净占比 | float64 | |
| 中单净流入-净额 | float64 | |
| 中单净流入-净占比 | float64 | |
| 小单净流入-净额 | float64 | |
| 小单净流入-净占比 | float64 | |

> 月频版: `data/store/stock/moneyflow/monthly/{date}.parquet` (全历史，来源 Tushare)

---

## 9. 限售股解禁

**存储**: `data/store/stock/share_float/all.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| ts_code | str | Tushare 代码 |
| ann_date | str | 公告日期 |
| float_date | str | 解禁日期 |
| float_share | float64 | 解禁数量 |
| float_ratio | float64 | 解禁比例 |
| holder_name | str | 持有人 |
| share_type | str | 股份类型 |

---

## 10. 股票回购

**存储**: `data/store/stock/repurchase/all.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| ts_code | str | Tushare 代码 |
| ann_date | str | 公告日期 |
| end_date | str | 回购期限 |
| proc | str | 进度 |
| exp_date | str | 到期日 |
| vol | float64 | 回购数量 |
| amount | float64 | 回购金额 |
| high_limit | float64 | 最高价 |
| low_limit | float64 | 最低价 |

---

## 11. 券商月度金股

**存储**: `data/store/stock/broker_recommend/{YYYYMM}.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| month | str | 月度 YYYYMM |
| broker | str | 券商名称 |
| ts_code | str | 推荐股票代码 |
| name | str | 股票名称 |

---

## 12. 涨跌停统计 (limit_list, 限流)

**存储**: `data/store/stock/limit_list/{date}.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| trade_date | str | 交易日期 |
| ts_code | str | |
| industry | str | 行业 |
| name | str | 股票名 |
| close | float64 | 收盘价 |
| pct_chg | float64 | 涨跌幅 |
| amount | float64 | 成交额 |
| limit_amount | float64 | 封单额 |
| float_mv | float64 | 流通市值 |
| total_mv | float64 | 总市值 |
| turnover_ratio | float64 | 换手率 |
| fd_amount | float64 | |
| first_time | str | 首次涨停时间 |
| last_time | str | 最后涨停时间 |
| open_times | int64 | 开板次数 |
| up_stat | str | 连板统计 |
| limit_times | int64 | 连板天数 |
| limit | str | U(涨停)/D(跌停)/Z(炸板) |

---

## 13. 券商研报 (限流)

**存储**: `data/store/stock/research_report/{YYYYMM}.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| trade_date | str | 研报日期 |
| title | str | 标题 |
| report_type | str | 个股/行业研报 |
| author | str | 作者 |
| name | str | 股票名称 |
| ts_code | str | 股票代码 |
| inst_csname | str | 券商名称 |
| ind_name | str | 行业 |
| url | str | 研报链接 |

---

## 14. 策略信号

**存储**: `data/store/signals/{strategy}.parquet` (buffett/multifactor/ml_lgbm/cybernetic)  
**备份**: `data/store/signals_prev/` (上一期快照)

| 列名 | 类型 | 说明 |
|------|------|------|
| strategy | str | 策略名 |
| symbol | str | 股票代码 |
| name | str | 股票名称 |
| industry | str | 申万行业 |
| score | float64/int64 | 评分 (巴菲特 int, 其他 float) |
| signal | str | BUY/HOLD/SELL |
| detail | str | 详情 JSON |
| computed_at | str | 计算时间 |

---

## 15. 巴菲特扫描

**存储**: `data/store/signals/buffett_scan.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| symbol | str | 股票代码 |
| name | str | 名称 |
| industry | str | 申万行业 |
| sector | str | 板块 |
| verdict | str | 评定 (PASS/FAIL) |
| score | int64 | 综合评分 0-100 |
| avg_roe_5y | float64 | 5 年平均 ROE |
| avg_gross_margin_5y | float64 | 5 年平均毛利率 |
| avg_net_margin_5y | float64 | 5 年平均净利率 |
| debt_equity_ratio | float64 | 负债权益比 |
| safety_margin_pct | float64 | 安全边际 % |
| dcf_value | float64 | DCF 估值 |
| current_price | float64 | 当前价格 |
| updated_at | str | 更新时间 |

---

## 16. 模拟交易

### 16.1 交易记录

**存储**: `data/store/paper/trades.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 交易日期 |
| code | str | 股票代码 |
| name | str | 股票名称 |
| side | str | BUY/SELL |
| price | float64 | 成交价 |
| volume | int64 | 股数 (100 的整数倍) |
| amount | float64 | 成交金额 |
| strategy | str | 策略来源 |

### 16.2 净值

**存储**: `data/store/paper/nav.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 日期 |
| total_asset | float64 | 总资产 |
| cash | float64 | 现金 |
| market_value | float64 | 持仓市值 |

### 16.3 状态

**存储**: `data/store/paper/state.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| cash | float64 | 可用资金 |
| frozen_cash | float64 | 冻结资金 |
| peak_equity | float64 | 峰值权益 |
| positions | str | 持仓 JSON |
| order_counter | int64 | 订单计数 |
| updated_at | str | 更新时间 |

---

## 17. DeepSeek Token 用量

**存储**: `data/store/deepseek/daily_usage.parquet`

| 列名 | 类型 | 说明 |
|------|------|------|
| utc_date | str | 日期 UTC |
| model | str | deepseek-v4-pro / deepseek-v4-flash |
| input_cache_hit | int64 | 缓存命中 token |
| input_cache_miss | int64 | 缓存未命中 token |
| output_tokens | int64 | 输出 token |
| requests | int64 | 请求次数 |
| cost_cny | float64 | 费用 ¥ |
| total_tokens | int64 | 总 token |

---

## 18. 系统监控

**存储**: `data/store/system_monitor.db` (SQLite, 365d 保留)

由 `scripts/collect_system_metrics.py` 采集，列包括 CPU 使用率、内存、磁盘、进程数、网络等约 15 列时间序列。

---

## 速查命令

```python
from data.datahub import DataHub
hub = DataHub()

# 读特征切片
df = hub.read_parquet(hub.feature_path("2026-04"))

# 读宏观
df = hub.read_parquet(hub.macro_path("cpi"))

# 读信号
df = hub.read_parquet(hub.signal_path("buffett"))

# 读模拟交易
df = hub.read_parquet(hub.paper_path("trades"))
```
