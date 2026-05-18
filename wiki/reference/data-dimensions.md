# Data Dimensions — 量化数据维度全览

## 架构总览

```
config/settings.yaml          ← 32 维度定义 (source/asset/status/freq)
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

共 32 个维度，按状态分类：

### 已启用 (19)

| key | 标签 | 来源 | 频率 | 资产 |
|-----|------|------|------|------|
| ohlcv_daily | 日线行情 OHLCV | akshare | daily | stock |
| adj_factor | 复权因子 | tushare_free | daily | stock |
| financial_summary | 同花顺财务摘要 | akshare | quarterly | stock |
| fina_indicator | Tushare 财务指标 | tushare_free | quarterly | stock |
| valuation_daily | 每日估值 PE/PB/PS | tushare_free | daily | stock |
| moneyflow_monthly | 月频资金流向 (全历史) | tushare_free | monthly | stock |
| moneyflow_daily | 日频资金流向 (近120日) | akshare | daily | stock |
| holder_number | 股东户数 | tushare_free | quarterly | stock |
| holder_trade | 股东增减持 | tushare_free | event | stock |
| broker_recommend | 券商月度金股 | tushare_free | monthly | stock |
| share_float | 限售股解禁 | tushare_free | event | stock |
| repurchase | 股票回购 | tushare_free | event | stock |
| macro_money_supply | 货币供应量 M0/M1/M2 | akshare | monthly | macro |
| macro_pmi | 制造业 PMI | akshare | monthly | macro |
| macro_cpi | CPI 居民消费价格 | akshare | monthly | macro |
| macro_ppi | PPI 工业品出厂价 | akshare | monthly | macro |
| macro_gdp | 国内生产总值 GDP | akshare | quarterly | macro |
| macro_shibor | Shibor 利率 | akshare | daily | macro |
| macro_lpr | LPR 贷款基础利率 | akshare | monthly | macro |

**来源分布**: akshare 10 | tushare_free 9

### 限流未启用 (3)

这些维度需要后台 cron 逐日拉取，当前未启用以免触发 Tushare 速率限制。

| key | 标签 | 原因 |
|-----|------|------|
| limit_list | 涨跌停统计 | 每日全量拉取, 频率高 |
| top_list | 龙虎榜 | 每日全量拉取, 频率高 |
| research_report | 券商研报 | 数据量大, 月频更新 |

### 付费 (4)

需要更高 Tushare 积分 (5000+)，当前积分为 2000。

| key | 标签 | 所需积分 |
|-----|------|---------|
| cyq_chips | 筹码分布 | 5000 |
| stk_factor_pro | 技术面因子专业版 | 5000 |
| stk_mins | 分钟行情 | 5000 |
| moneyflow_daily_full | 日频资金流向全历史 | 5000 |

### 规划中 (6)

未实现，预留接口。

| key | 标签 | 资产类型 |
|-----|------|---------|
| dividend | 分红送股 | stock |
| fund_daily | 基金日线 | fund |
| fund_portfolio | 基金持仓 | fund |
| fund_nav | 基金净值 | fund |
| futures_daily | 期货日线 | futures |
| crypto_daily | 加密货币日线 | crypto |

---

## 文件树 — data/store/

```
store/
├── scan_meta.parquet                3KB   扫描元数据
├── system_monitor.db               388KB   系统指标时序 (SQLite, 365d 保留)
│
├── stock/                                ← 个股维度
│   ├── broker_recommend/                 ← 月度金股 (按月: 202401.parquet)
│   ├── moneyflow/                        ← 资金流向
│   │   ├── {symbol}.parquet             ← 日频 (近120日, 单只 20KB)
│   │   └── monthly/{date}.parquet       ← 月频 (全历史, 单月 ~500KB)
│   ├── holders/{symbol}.parquet         ← 股东户数 (单只 ~6KB)
│   ├── holdertrade/{symbol}.parquet     ← 股东增减持 (单只 ~8KB)
│   ├── share_float/all.parquet    134KB  ← 限售股解禁
│   ├── repurchase/all.parquet      52KB  ← 股票回购
│   ├── research_report/{month}.parquet   ← 券商研报 (~95KB/月)
│   └── limit_list/{date}.parquet        ← 涨跌停统计
│
├── macro/                                ← 宏观数据
│   ├── cpi.parquet                   10KB
│   ├── gdp.parquet                    5KB
│   ├── lpr.parquet                   16KB
│   ├── money_supply.parquet          12KB
│   ├── pmi.parquet                    7KB
│   ├── ppi.parquet                    9KB
│   └── shibor.parquet               142KB
│
├── features/                             ← PIT 特征 (月度切片)
│   └── 2018-01.parquet ~ 2026-04.parquet  (100个文件, 1.0~1.7MB/月)
│
├── signals/                              ← 策略信号
│   ├── buffett.parquet                10KB
│   ├── buffett_scan.parquet           16KB
│   ├── cybernetic.parquet             18KB
│   ├── ml_lgbm.parquet                10KB
│   └── multifactor.parquet            13KB
│
├── signals_prev/                         ← 上一期信号快照
│   └── (同上)
│
├── paper/                                ← 模拟交易
│   ├── nav.parquet                     3KB
│   ├── state.parquet                   9KB
│   └── trades.parquet                  5KB
│
├── deepseek/daily_usage.parquet    6KB    ← DeepSeek Token 用量
├── bond/treasury_yields.parquet   396KB   ← 国债收益率
├── futures/daily/RB.parquet       146KB   ← 期货 (螺纹钢示例)
└── financials/                            ← 财务数据缓存 (空, 按需拉取)
```

**总量**: ~120MB (100 个月特征切片占 90%+)

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
| `data/datahub_schema.sql` | DuckDB 视图定义 |
| `data/fetcher.py` | AKShare 日线拉取 |
| `data/feature_store.py` | PIT 特征构建 + enrich |
| `scripts/build_features.py` | 批量特征构建 |
| `scripts/cron_fetch_slow.py` | 限流数据日常填充 |
