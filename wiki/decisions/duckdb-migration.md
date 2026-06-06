---
title: DuckDB + Parquet 存储架构演进
created: 2026-05-12
updated: 2026-05-26
type: decision
tags: [duckdb, parquet, database, migration, architecture, ADR, concurrency]
---

# Decision: DuckDB as Query Engine, Parquet as Storage

- **Date**: 2026-05-12 (Phase 1: SQLite→DuckDB), 2026-05-14 (Phase 2: DuckDB→Parquet), 2026-05-15 (Phase 3: PIT特征存储)
- **Status**: Implemented (Phase 3 — 生产稳定)
- **Author**: 星盘

## Phase 1: SQLite → DuckDB (2026-05-12)

1000 只股票 × 日线 + 财务 + 策略信号。DuckDB 列存+向量化执行，分析查询比 SQLite 快 10-100 倍。

## Phase 2: DuckDB-as-Storage → Parquet Storage (2026-05-14)

**根因**: macOS DuckDB 不支持并发，cron 写锁导致 Web 读 500。单文件无法扩展至多资产。

**新架构**:
```
存储层: data/store/signals/{strategy}.parquet  (pd.to_parquet, 无文件锁)
查询层: DuckDB :memory: → read_parquet() → CREATE VIEW (内存, 永不锁)
```

**对比**:

| | Phase 1 (DuckDB 单文件) | Phase 2 (Parquet + 内存 DuckDB) |
|---|---|---|
| 并发 | macOS 不支持, 必锁 | 无锁, 多进程安全 |
| 扩展 | 单文件越来越大 | 按资产/日期分区, 增量追加 |
| Web 读 | 等 cron 释放锁 | 永不等 |
| 新增资产 | 改 schema 重建 | 新目录 + 新 Parquet |

## 读写分离

- Web: `duckdb.connect(":memory:")` + `CREATE VIEW FROM read_parquet()` → 永不锁
- Cron: `pd.DataFrame.to_parquet()` → 直接写文件, 不经过 DuckDB

## 写入模式

Pandas → Parquet, 无需 SQL 写入, 无锁, 无 INSERT 陷阱。

## Migration Details

- `data/store/signals/{strategy}.parquet` — 策略信号 (一文件一策略)
- `data/store/signals/buffett_scan.parquet` — 巴菲特扫描 (含财务详情列)
- `data/store/scan_meta.parquet` — 扫描元数据
- DuckDB `:memory:` 连接 → `_register_views()` 自动映射 Parquet 视图
- `data/db.py` 保持统一接口, 读/写透明

## See Also

- [[web-architecture]] — Web SPA fallback + health endpoint
- [[data-sources]] — 数据管道输出
- [[financial-cache]] — 财务数据用 parquet 缓存
- [[ml-pipeline]] — ML 管道 (PIT 特征 + LightGBM)
- [[system-architecture]] — 五层架构总览

---

## Phase 3: Feature Store 扩展 (2026-05-15)

Parquet 模式成功 → 自然扩展到 ML 特征存储：

```
data/store/
├── signals/                    # Phase 2: 策略信号
│   ├── buffett.parquet
│   ├── multifactor.parquet
│   ├── cybernetic.parquet
│   └── ml_lgbm.parquet
├── features/                   # Phase 3: PIT 特征 (NEW)
│   ├── 2020-01-02.parquet      # as-of 日期视图, 零前视
│   ├── 2020-01-03.parquet
│   └── 2020-01.parquet         # 兼容月末快照
├── buffett_scan.parquet
└── scan_meta.parquet
```

**特征表 schema** (因子列 + symbol + as_of_date + month):
```
symbol, as_of_date, month,
ret_1d, ret_5d, ret_20d, ret_60d,          # 收益率
ma5_bias, ma20_bias, ma60_bias,             # 均线偏离
vol_5d, vol_20d, vol_60d,                   # 波动率
volume_ratio_5, volume_ratio_20,            # 成交量
amplitude, high_low_ratio,                  # 价格范围
ma5_20_cross, ma20_60_cross,                # 趋势
rsi_14,                                     # 动量
fund_roe, fund_gross_margin, fund_de_ratio, # 基本面 (3)
fund_roe_5y_avg, fund_gm_trend,             # 基本面趋势 (2)
val_pe, val_pb, val_ps,                     # 估值 (3)
val_pe_percentile, val_total_mv,            # 估值 (2)
vol_adj_mom_5d, midpoint_bias, ...          # LLM因子 (7) ★
ret_fwd_20d                                 # 目标变量
```

**读取模式**:
```python
# DuckDB 视图自动注册
db = duckdb.connect(":memory:")
db.execute("CREATE VIEW features_2024_01 AS SELECT * FROM read_parquet('data/store/features/2024-01.parquet')")
# 查询: symbols × month ∈ training window
```

**关键特性**:
- 写: `pd.to_parquet()` — 无锁, 无并发冲突
- 读: DuckDB视图 — 内存查询, 永不等
- PIT严格: 每个 as-of 文件只含该日期已知的数据, FeatureStore 强制 as_of 限制
- 可扩展: 新增资产 → 同 schema 新文件, 无需改表

## Phase 2/3 读写模式

- Web: `duckdb.connect(":memory:")` + `CREATE VIEW FROM read_parquet()` → 永不锁
- Cron: `pd.DataFrame.to_parquet()` → 直接写文件, 不经过 DuckDB
- Features: `scripts/build_features.py --frequency daily` → `to_parquet()` → 按 as-of 日期存储，月末快照兼容
