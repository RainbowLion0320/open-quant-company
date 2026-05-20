---
title: DataHub 数据中台决策
created: 2026-05-17
updated: 2026-05-21
type: decision
tags: [datahub, storage, parquet, duckdb, architecture]
---

# DataHub 数据中台决策

日期: 2026-05-17

## 结论

当前项目不需要把主数据迁到 PostgreSQL/MySQL 这类重型数据库。更合理的方案是保持既有的 **Parquet 持久化 + DuckDB 只读查询视图**，在上面增加一个轻量 DataHub 层，统一路径、读写、追加、最新批次和存储审计。

原因:

- 策略信号、PIT 特征、paper trading 状态、宏观数据和缓存本质都是本地批量数据，Parquet 更适合列式扫描和回测。
- Web 端只读查询用 DuckDB `:memory:` 映射 Parquet，不会和 cron 写入抢锁。
- 真正混乱点不是存储格式，而是路径和读写入口分散，很多模块自己拼 `data/store/...`、`data/cache/...`，难以扩展和审计。
- 后续数据维度会增多，先把数据目录和逻辑数据集收敛成 DataHub catalog，比提前引入服务型数据库更稳。

## 实现

核心模块: `data/datahub.py`

DataHub 负责:

- 统一目录: `store_root`, `cache_root`, `signals`, `features`, `macro`, `paper`, `system_monitor`, token cache。
- 统一路径: `signal_path(strategy)`, `feature_path(month)`, `macro_path(name)`, `paper_path(name)`。
- 原子写入: Parquet/JSON 先写临时文件，再 `os.replace` 覆盖，降低半写入风险。
- 追加写入: `append_parquet(..., dedupe_subset=...)` 统一处理追加和去重。
- 最新批次: `latest_batch(path, ts_col="computed_at")` 统一读取策略最新信号。
- 轻量审计: `audit()` 返回已知逻辑数据集的存在性、文件数量和大小。

## 接入范围

已接入:

- `data/db.py`: DuckDB 视图注册统一使用 DataHub 的 store/cache 目录。
- `data/results_db.py`: 策略结果、巴菲特扫描、scan meta 改为 DataHub 原子写入。
- `data/feature_store.py`: PIT 月切片和 registry enrichment 改为 DataHub 路径。
- `broker/persistence.py`: paper trading 状态目录改为 DataHub，并修复相对配置路径解析。
- `scripts/execute_paper_trades.py`: 使用 `latest_batch` 读取最新信号。
- `web/api/routes/system.py`, `scripts/collect_system_metrics.py`: 系统监控库和 token cache 不再写死绝对路径。
- 多个离线脚本和 fetcher: 移除硬编码 `/Users/fushao/quant-agent/...`，逐步用 DataHub 管理。

## 后续扩展规则

新增数据维度时优先遵循:

1. 在 `config/settings.yaml -> data_registry` 描述维度来源、资产类别、频率、状态和缓存模式。
2. 在 DataHub 增加明确路径 helper，避免业务脚本自己拼深层目录。
3. 写入 Parquet/JSON 走 `DataHub.write_parquet/write_json`。
4. 追加型数据走 `append_parquet`，必须明确去重键或批次时间列。
5. Web 查询继续走 DuckDB 只读视图，只有确实需要事务、并发写、多用户权限时再引入服务型数据库。

## 迁移原则

本次不移动历史数据，不改变现有 Parquet 文件名，不破坏旧路径。DataHub 先作为统一入口覆盖新增和关键路径，后续模块可以渐进式迁入。
