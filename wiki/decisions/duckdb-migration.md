---
title: DuckDB + Parquet 存储架构演进
created: 2026-05-12
updated: 2026-05-14
type: decision
tags: [duckdb, parquet, database, migration, architecture, ADR, concurrency]
---

# Decision: DuckDB as Query Engine, Parquet as Storage

- **Date**: 2026-05-12 (Phase 1: SQLite→DuckDB), 2026-05-14 (Phase 2: DuckDB→Parquet)
- **Status**: Implemented (Phase 2)
- **Author**: Quant Agent

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

## 读写分离 (已废弃旧方案)

~~Web 以 `get_db(read_only=True)` 连接，实践中采用"关 Web → 扫描 → 重启 Web"的顺序。~~

**Phase 2 新方案**: 
- Web: `duckdb.connect(":memory:")` + `CREATE VIEW FROM read_parquet()` → 永不锁
- Cron: `pd.DataFrame.to_parquet()` → 直接写文件, 不经过 DuckDB

## 写入模式 (已废弃旧方案)

~~`INSERT OR REPLACE` 在 DuckDB 复合主键 + `executemany` 批量插入下有 bug……~~

**Phase 2**: Pandas → Parquet, 无需 SQL 写入, 无锁, 无 INSERT 陷阱。

## Migration Details

- `data/store/signals/{strategy}.parquet` — 策略信号 (一文件一策略)
- `data/store/buffett_scan.parquet` — 巴菲特扫描 (含财务详情列)
- `data/store/scan_meta.parquet` — 扫描元数据
- DuckDB `:memory:` 连接 → `_register_views()` 自动映射 Parquet 视图
- `data/db.py` 保持统一接口, 读/写透明

## See Also

- [[web-architecture]] — Web SPA fallback + health endpoint
- [[data-sources]] — 数据管道输出
- [[financial-cache]] — 财务数据用 parquet 缓存
- [[system-architecture]] — 五层架构总览
