---
title: DataHub 数据中台决策
created: 2026-05-17
updated: 2026-06-06
type: decision
tags: [datahub, storage, parquet, duckdb, architecture]
---

# DataHub 数据中台决策

日期: 2026-05-17

## 结论

当前项目不需要把主数据迁到 PostgreSQL/MySQL 这类重型数据库。更合理的方案是保持 **Parquet 持久化 + DuckDB 只读查询视图**，由 DataHub 统一路径、读写、追加、最新批次、存储审计和运行产物目录。

原因:

- 策略信号、PIT 特征、paper trading 状态、宏观数据和缓存本质都是本地批量数据，Parquet 更适合列式扫描和回测。
- Web 端只读查询用 DuckDB `:memory:` 映射 Parquet，不会和 cron 写入抢锁。
- 真正混乱点不是存储格式，而是路径和读写入口分散。仓库内部不得再自己拼 `var/store/...`、`var/cache/...` 这类深层路径，运行产物统一经 DataHub 或配置路径解析。
- 后续数据维度会增多，先把数据目录和逻辑数据集收敛成 DataHub catalog，比提前引入服务型数据库更稳。
- `data/` 保留为源码包，运行数据统一迁到 `var/`，避免源码、缓存、数据库、模型和回测产物混放。

## 实现

核心 facade: `data/storage/datahub.py`

DataHub 对外负责统一入口。内部实现拆为小组件，避免单文件承担过多细节:

| 组件 | 文件 | 边界 |
|------|------|------|
| `DataHubPaths` | `data/storage/datahub_paths.py` | 路径解析、目录 helper、registry cache pattern 展开 |
| `ParquetStore` | `data/storage/datahub_parquet.py` | Parquet 原子读写、追加锁、latest batch、目录扫描 |
| `ManifestStore` | `data/storage/datahub_manifest.py` | manifest 记录、schema hash、文件 hash、日期范围 |
| `DimensionStore` | `data/storage/datahub_dimensions.py` | DataRegistry 维度 root/path/list/latest |

DataHub facade 负责:

- 统一目录: `runtime_root`, `store_root`, `cache_root`, `artifact_root`, `db_root`, `signals`, `features`, `macro`, `paper`, `system_monitor`, token cache。
- 运行产物 API: `runtime_dir()`, `artifact_dir(kind)`, `artifact_path(kind, name)`, `db_path(name)`, `migration_dir()`。
- 统一路径: `signal_path(strategy)`, `feature_path(month)`, `macro_path(name)`, `paper_path(name)`。
- 注册表路径展开: `dimension_root(key)` / `dimension_path(key, **values)` 从 `data_registry.cache` 占位符模式生成真实路径。**设计理由**: 路径只定义一次（config.yaml），消费脚本不硬编码深层目录。占位符 `{symbol}`/`{YYYYMMDD}` 在调用点展开，`validate()` 拒绝 `..` 和绝对路径。
- 路径 vs 创建分离: `store_path(asset)` 纯路径计算（dimension 展开用），`store_dir(asset)` 创建目录（init 用）。**设计理由**: dimension 路径展开不应产生空目录副作用。
- 原子写入: Parquet/JSON 先写临时文件，再 `os.replace` 覆盖，降低半写入风险。
- 写入清单: `write_parquet(..., producer=)` 成功后更新 `_manifest/datasets.parquet`，记录 producer/行数/日期范围/schema_hash/file_sha256。**设计理由**: 每次写入可追溯来源、可检测 schema 变更、可校验文件完整性。manifest 写入失败不抛异常——可观测性不阻塞主数据流。
- 追加写入: `append_parquet(..., dedupe_subset=...)` 统一处理追加和去重。
- 最新批次: `latest_batch(path, ts_col="computed_at")` 统一读取策略最新信号。
- 轻量审计: `audit()` 返回已知逻辑数据集的存在性、文件数量和大小。

默认运行布局:

```text
var/
  store/
  cache/
  artifacts/
    backtests/
    models/
    tournaments/
    reports/
  db/
  logs/
  migration/
```

环境变量覆盖优先级保留：`ASTROLABE_VAR`、`ASTROLABE_STORE`、`ASTROLABE_CACHE`、`ASTROLABE_ARTIFACTS`、`ASTROLABE_DB`。旧 `ASTROLABE_STORE` / `ASTROLABE_CACHE` 仍可继续使用。

设计约束: 很多模块依赖 DataHub 是合理的，因为 DataHub 是数据访问边界。反向依赖不合理: DataHub 及其内部组件不得依赖策略、Web、CLI、执行层业务逻辑。业务模块也不应绕过 DataHub/registry 自己拼深层存储路径。

## 接入范围

已接入:

- `data/storage/db.py`: DuckDB 视图注册统一使用 DataHub 的 store/cache/db 目录。
- `data/storage/results_db.py`: 策略结果、巴菲特扫描、scan meta 改为 DataHub 原子写入。
- `data/features/feature_store.py`: PIT as-of 日期视图、兼容月末快照和 registry enrichment 改为 DataHub 路径。
- `broker/persistence.py`: paper trading 状态目录改为 DataHub，并修复相对配置路径解析。
- `scripts/execute_paper_trades.py`: 使用 `latest_batch` 读取最新信号。
- `web/api/routes/system.py`, `scripts/collect_system_metrics.py`: 系统监控库和 token cache 不再写死绝对路径。
- `scripts/db_health_check.py`: 健康扫描从 data registry 注入 source/label/SLA/repair/partition 元数据。
- 多个离线脚本和 fetcher: 通过 DataHub/registry 解析路径，不依赖固定本机路径。

## 后续扩展规则

新增数据维度时优先遵循:

1. 在 `config/settings.yaml -> data_registry` 描述维度来源、资产类别、频率、状态和缓存模式。
2. 优先使用 `DataHub.dimension_path()` 生成维度路径；只有高频公共路径才增加明确 helper。
3. 写入 Parquet/JSON 走 `DataHub.write_parquet/write_json`，并传入清晰的 `producer`。
4. 追加型数据走 `append_parquet`，必须明确去重键或批次时间列。
5. Web 查询继续走 DuckDB 只读视图，只有确实需要事务、并发写、多用户权限时再引入服务型数据库。

## 当前约束

新增或重构模块不得再引入绕过 DataHub/registry 的读写路径。已迁入 DataHub 的维度不保留扁平文件 fallback；确需迁移旧数据时，应写一次性迁移脚本，而不是在运行时代码中长期保留兼容分支。
