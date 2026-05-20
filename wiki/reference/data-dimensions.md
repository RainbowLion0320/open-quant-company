---
title: Data Dimensions — 量化数据维度全览
created: 2026-05-13
updated: 2026-05-21
type: reference
tags: [data, dimensions, registry, datahub, storage, parquet]
---

# Data Dimensions — 量化数据维度全览

> 最后更新: 2026-05-21. 维度定义在 `config/settings.yaml` → `data_registry`.

## 架构总览

```
config/settings.yaml          ← 33 维度定义 (source/asset/status/freq)
        │
        ▼
data/data_registry.py         ← 单例注册表, 加载 YAML → DataDimension[] 
        │
        ▼
data/datahub.py               ← 存储中间层: 路径映射, 原子写入, 追加去重
        │
        ▼
data/store/                   ← Parquet 持久化 (按月/按 symbol 分区)
        │
        ▼
data/db.py → DuckDB :memory:  ← 只读视图, 零文件锁冲突
```

三层含义：
- **DataRegistry** 告诉你「有什么维度」
- **DataHub** 管「存在哪里、怎么读写」
- **Parquet** 是持久化格式，**DuckDB** 是查询层

---

## 维度总表

共 33 个维度，按状态分类：

### 已启用 (20)

| key | 标签 | 来源 | 频率 | 资产 |
|-----|------|------|------|------|
| ohlcv_daily | 日线行情 OHLCV | akshare | daily | stock |
| adj_factor | 复权因子 | tushare_free | daily | stock |
| financial_summary | 同花顺财务摘要 | akshare | quarterly | stock |
| fina_indicator | Tushare 财务指标 | tushare_free | quarterly | stock |
| valuation_daily | 每日估值 PE/PB/PS | tushare_free | daily | stock |
| moneyflow_monthly | 月频资金流向 (全历史) | tushare_free | monthly | stock |
| moneyflow_daily | 日频资金流向 (近120日) | akshare | daily | stock |
| moneyflow_tushare_daily | 日频资金流向 (Tushare全市场) | tushare_free | daily | stock |
| holder_number | 股东户数 | tushare_free | quarterly | stock |
| holder_trade | 股东增减持 | tushare_free | event | stock |
| broker_recommend | 券商月度金股 | tushare_free | monthly | stock |
| share_float | 限售股解禁 | tushare_free | event | stock |
| repurchase | 股票回购 | tushare_free | event | stock |
| macro_money_supply | 货币供应量 M0/M1/M2 | akshare | monthly | macro |
| macro_pmi | 制造业 PMI | tushare_free | monthly | macro |
| macro_cpi | CPI 居民消费价格 | tushare_free | monthly | macro |
| macro_ppi | PPI 工业品出厂价 | tushare_free | monthly | macro |
| macro_gdp | 国内生产总值 GDP | tushare_free | quarterly | macro |
| macro_shibor | Shibor 利率 | akshare | daily | macro |
| macro_lpr | LPR 贷款基础利率 | tushare_free | monthly | macro |

**来源分布**: akshare 5 | tushare_free 23 | tushare_paid 4 | future 1

### 限流启用 (3)

这些维度需要后台 cron 逐日拉取，Web 健康页支持单表修复，但 `limit_list` 必须遵守 1次/小时节流。

| key | 标签 | 原因 |
|-----|------|------|
| limit_list | 涨跌停统计 | 1次/小时, 每次最多请求1天 |
| top_list | 龙虎榜 | 每日全量拉取, 后台增量 |
| research_report | 券商研报 | 数据量大, 月频更新 |

### 付费 (4)

需要更高 Tushare 积分 (5000+)，当前积分为 2000。

| key | 标签 | 所需积分 |
|-----|------|---------|
| cyq_chips | 筹码分布 | 5000 |
| stk_factor_pro | 技术面因子专业版 | 5000 |
| stk_mins | 分钟行情 | 5000 |
| moneyflow_daily_full | 日频资金流向全历史 | 5000 |

### 扩展可用 (5)

已接入 Tushare Free 拉取脚本、DB 健康扫描和单表修复。

| key | 标签 | 资产类型 |
|-----|------|---------|
| dividend | 分红送股 | stock |
| fund_daily | 基金日线 | fund |
| fund_portfolio | 基金持仓 | fund |
| fund_nav | 基金净值 | fund |
| futures_daily | 期货日线 | futures |

### 规划中 (1)

未实现，预留接口。

| key | 标签 | 资产类型 |
|-----|------|---------|
| crypto_daily | 加密货币日线 | crypto |

---

## 文件树 — data/store/

```
store/
├── scan_meta.parquet                 扫描元数据
├── system_monitor.db                 系统指标时序 (SQLite, 365d 保留)
│
├── stock/                                ← 个股维度
│   ├── daily/{symbol}.parquet            ← OHLCV 日线
│   ├── financials/{symbol}.parquet       ← 财务摘要 (原 cache/)
│   ├── valuation/{symbol}.parquet        ← PE/PB 估值 (原 cache/)
│   ├── broker_recommend/                 ← 月度金股 (按月分区)
│   ├── moneyflow/                        ← 资金流向
│   │   ├── {symbol}.parquet              ← AKShare 个股近120日
│   │   ├── daily/{date}.parquet          ← Tushare 全市场日频
│   │   └── monthly/{date}.parquet        ← Tushare 月频 (全历史)
│   ├── holders/{symbol}.parquet         ← 股东户数
│   ├── holdertrade/{symbol}.parquet     ← 股东增减持
│   ├── share_float/all.parquet          ← 限售股解禁
│   ├── repurchase/all.parquet           ← 股票回购
│   ├── dividend/all_dividends.parquet    ← 分红送股
│   ├── research_report/{month}.parquet   ← 券商研报
│   ├── top_list/{date}.parquet           ← 龙虎榜
│   └── limit_list/{date}.parquet         ← 涨跌停统计
│
├── fund/                                 ← 基金维度
│   ├── daily/{symbol}.parquet            ← 基金日线
│   ├── portfolio/{period}.parquet        ← 基金持仓
│   └── nav/{symbol}.parquet              ← 基金净值
│
├── futures/                              ← 期货维度
│   └── daily/{symbol}.parquet            ← 期货日线
│
├── macro/                                ← 宏观数据
│   ├── cpi.parquet
│   ├── gdp.parquet
│   ├── lpr.parquet
│   ├── money_supply.parquet
│   ├── pmi.parquet
│   ├── ppi.parquet
│   └── shibor.parquet
│
├── features/                             ← PIT 特征 (月度切片)
│   └── YYYY-MM.parquet                   ← 按月分区
│
├── signals/                              ← 策略信号
│   ├── buffett.parquet
│   ├── buffett_scan.parquet
│   ├── cybernetic.parquet
│   ├── ml_lgbm.parquet
│   └── multifactor.parquet
│
├── signals_prev/                         ← 上一期信号快照
│   └── (同上)
│
├── paper/                                ← 模拟交易
│   ├── nav.parquet
│   ├── state.parquet
│   └── trades.parquet
│
├── deepseek/daily_usage.parquet         ← DeepSeek 日度用量 (CDP 自动)
├── bond/treasury_yields.parquet         ← 国债收益率
├── futures/daily/{contract}.parquet     ← 期货主连合约
└── cache/api/*.parquet                  ← AKShare API 响应 MD5 缓存 (可再生)
```

---

## 用法速查

### 查维度状态

```python
from data.data_registry import get_registry

reg = get_registry()

# 所有可用维度
for d in reg.get_available():
    print(d.key, d.source, d.freq)

# 按来源筛选
for d in reg.by_source("akshare"):
    print(d.key)

# 检查单个维度
from data.data_registry import is_available
if is_available("fina_indicator"):
    ...
```

### 读写数据

```python
from data.datahub import DataHub

hub = DataHub()

# 读宏观数据
df = hub.read_parquet(hub.macro_path("cpi"))

# 读特征切片
df = hub.read_parquet(hub.feature_path("2026-04"))

# 按 data_registry 生成具体维度路径
path = hub.dimension_path("moneyflow_tushare_daily", YYYYMMDD="20260520")

# 原子写入 (tmp + os.replace)
hub.write_parquet(df, hub.signal_path("multifactor"))

# 追加去重 (按月频数据)
hub.append_parquet(
    hub.macro_path("money_supply"),
    new_rows,
    dedupe_subset=["month"],
    sort_by=["month"],
)
```

---

## 新增维度流程

1. 在 `config/settings.yaml` → `data_registry` 下添加条目：
```yaml
  new_dim:
    source: akshare
    asset: stock
    status: available
    freq: daily
    enabled: true
    label: 新维度
    cache: stock/new_dim/
    description: 描述
```

2. 在 `datahub.py` 添加路径方法 (如果有特殊路径结构):
```python
def new_dim_path(self, symbol: str) -> Path:
    return self.store_dir("stock") / "new_dim" / f"{symbol}.parquet"
```

3. 在对应的 fetcher 中添加数据拉取逻辑。

4. 如有合约约束，在 `tests/test_architecture_contracts.py` 中添加测试。

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `config/settings.yaml` | 维度定义 (data_registry 段) |
| `data/data_registry.py` | 注册表单例 |
| `data/datahub.py` | 存储中间层 |
| `data/db.py` | DuckDB 连接与视图管理 |
| `data/fetcher.py` | AKShare 日线拉取 |
| `data/feature_store.py` | PIT 特征构建 + enrich |
| `scripts/build_features.py` | 批量特征构建 |
| `scripts/cron_fetch_slow.py` | 限流数据日常填充 |
