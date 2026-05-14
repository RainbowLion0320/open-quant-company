# Tushare MCP 数据模块指南

> 更新时间: 2026-05-11 | 积分: 2000 | MCP Server: tushare v0.0.1

## 接入方式

Tushare MCP Server 通过 Streamable HTTP 协议运行:
- MCP URL: `https://api.tushare.pro/mcp/?token=<token>`（配置在 `~/.hermes/config.yaml` → `mcp_servers.tushare`）
- Token: `config/settings.yaml` → `data.tushare.token`
- 共 258 个 MCP 工具，覆盖 15 个数据大类

## 数据等级与用途

### 一级：核心（量化必需，替换当前AKShare/同花顺方案）

| MCP工具 | 提供内容 | 替代方案 | 接入优先级 |
|---------|----------|----------|:--:|
| `daily_basic` | PE/PB/PS/市值/换手率/流通股本 | 当前Baidu估值 + Sina股本 | P0 |
| `fina_indicator` | ROE/ROA/毛利率/净利率/FCFF/FCFE/eps/每股净资产等50+字段 | 当前同花顺摘要（字段少、解析脆弱） | P0 |
| `income` | 完整利润表（100+字段） | 当前无 | P0 |
| `balancesheet` | 完整资产负债表（200+字段） | 当前无 | P0 |
| `cashflow` | 完整现金流量表（80+字段） | 当前同花顺现金流(72字段) | P0 |
| `stock_basic` | 全A股列表+行业+上市日期+是否ST | 当前AKShare stock_info_a_code_name | P1 |
| `index_classify` | 申万2014/2021版行业分类（三级） | 当前scripts/pull_industry.py | P1 |
| `sw_daily` | 申万行业指数日行情 | 当前无（只用个股） | P1 |

### 二级：策略增强（2000积分解锁，AKShare没有）

| MCP工具 | 提供内容 | 量化用途 |
|---------|----------|----------|
| `weekly` / `monthly` | A股周线/月线 | 低频验证（2000分） |
| `margin` | 融资融券每日汇总（2010起） | 控制论情绪指标 |
| `margin_detail` | 个股融资融券明细 | 个股杠杆热度 |
| `hk_hold` | 北向资金持股明细 | 外资持仓变化 |
| `stk_holdernumber` | 股东人数（不定期） | 筹码集中度 |
| `moneyflow` | 个股资金流向（大单/小单） | 主力动向 |
| `pledge_stat` / `pledge_detail` | 股权质押 | 风险排查 |
| `repurchase` | 股票回购 | 管理层信心信号 |
| `stk_holdertrade` | 股东增减持 | 内部人交易 |
| `top10_holders` / `top10_floatholders` | 前十大股东/流通股东 | 机构持仓分析 |
| `report_rc` | 券商盈利预测 | DCF增长假设参考 |
| `forecast` / `express` | 业绩预告/快报 | 财报前瞻 |
| `dividend` | 分红送股 | 股息率因子 |
| `fina_mainbz` | 主营业务构成 | 护城河深度分析 |

### 三级：宏观环境（控制论regime detection）

| MCP工具 | 提供内容 |
|---------|----------|
| `cn_gdp` | GDP |
| `cn_cpi` | CPI |
| `cn_m` | 货币供应量（M0/M1/M2） |
| `cn_ppi` | PPI |
| `sf_month` | 社会融资规模 |
| `cn_pmi` | PMI |
| `shibor` / `shibor_lpr` | Shibor利率/LPR |
| `cn_schedule` | 经济数据发布日程 |
| `moneyflow_hsgt` | 沪深港通资金流向 |

### 四级：研究与信息

| MCP工具 | 提供内容 |
|---------|----------|
| `research_report` | 券商研报（个股/行业，2017起） |
| `news` | 新闻快讯（6年+历史） |
| `major_news` | 长篇通讯（8年+） |
| `npr` | 国家政策库 |
| `irm_qa_sh` / `irm_qa_sz` | 上证/深证e互动董秘问答 |

### 五级：暂时不需要（打板/超短/高频/跨市场）

| 分类 | 说明 |
|------|------|
| 打板专题 (30个) | 龙虎榜/涨跌停/同花顺东财概念/游资——超短风格 |
| 分钟/Tick/实时 | 低频量化不需要 |
| 期货/期权/债券 | A股以外的品种 |
| 港股/美股 | 扩展阶段再考虑 |
| 小佩因子 (stock_vx/stock_mx) | 黑箱因子，不符合控制论透明原则 |

## 权限等级

| 积分 | 关键解锁 |
|------|----------|
| 120 | daily, stock_basic, trade_cal, new_share, namechange |
| **2000** | weekly, monthly, daily_basic, margin, moneyflow, top_list, hk_hold, stk_holdernumber, 股东增减持, 股权质押, 回购, 大宗交易, fina系列 |
| 3000 | share_float (限售解禁) |
| 5000+ | 分钟数据, 高频 |

当前2000积分基本覆盖所有低频量化需求，只有一个share_float（限售解禁）需3000分。

## AKShare ↔ Tushare 分工

```
AKShare（免费不限流）         Tushare MCP（2000分）
├── 日线OHLCV (3源fallback)  ├── 完整三张表 (income/balance/cash)
├── 实时快照 (spot_em)       ├── 财务指标 (fina_indicator)
├── 指数成分股                ├── PE/PB/市值/换手 (daily_basic)
└──                           ├── 申万行业分类+行情
                              ├── 融资融券
                              ├── 北向资金
                              ├── 股东人数
                              ├── 宏观数据
                              └── 研报+新闻
```

原则：**日线行情走AKShare（免费），财务/指标/情绪/行业走Tushare。**

## 已知限制

### 免费档 vs 2000积分的区别

| 接口 | 免费(120) | 2000积分 |
|------|-----------|----------|
| stock_basic | 1次/小时 | 无明显限制 |
| trade_cal | 无权限 | ✅ |
| daily_basic | 无权限 | ✅ |
| fina_indicator | 无权限 | ✅（每次100条，循环提取） |
| income/balance/cash | 无权限 | ✅ |
| margin/moneyflow | 无权限 | ✅ |
| hk_hold | 无权限 | ✅ |

### 通用限制

- `fina_indicator`: 单次最多100条，需按日期循环
- `daily`: 单次8000行
- `daily_basic`: 单次6000条
- `moneyflow_hsgt`: 单次300条
- MCP调用频率: 未知（需实际使用观察）

## MCP工具完整列表

258个工具，详见 `hermes mcp tools` 或直接查看:
- 沪深股票: 基础14 + 行情20 + 财务10 + 参考9 + 市场参考8 + 两融7 + 资金流向8 + 特色14 + 打板30 = 120
- 指数专题: 15+
- 宏观: 19 (国内14 + 国际5)
- 大模型语料: 6
- 其他: 港股/美股/ETF/期货/期权/债券/外汇 ~100
