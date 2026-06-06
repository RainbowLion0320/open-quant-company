# Spec: 数据管道 (Data Pipeline)

> 版本: 1.4 | 更新: 2026-06-06 | 关联: [PRD](../PRD.md) [Signal System](02-signal-system.md)

## 1. 概述

数据管道负责从多源拉取、清洗、缓存、存储 A 股全量数据，并通过 DataHub 统一路径向上层（信号/回测/执行/Web）暴露。`data/` 是 Python 数据层源码包，运行数据、缓存、数据库、模型训练产物和回测产物统一写入 `var/`。覆盖维度由 `config/settings.yaml` 的 `data_registry` 声明，按频率分为日频（行情/估值/资金流向/行业快照）、月频/季频（财务指标/三张表）、事件驱动（龙虎榜/研报/限售解禁/公司行动）。

**核心理念：**
- **离线优先** — 所有数据存储为本地 Parquet，不依赖云端数据库
- **源码与运行产物分离** — `data/` 只放源码和静态 reference，`var/` 放本地运行产物且默认不进 git
- **多源互补** — AKShare（免费不限流，行情）+ Tushare（深度财务数据）
- **声明式注册** — 数据维度统一在 `settings.yaml` → `DataRegistry` 中声明，含 source/label/SLA/repair/partition
- **价格口径显式** — OHLCV 通过 `PriceService` 声明 `raw` / `qfq` / `hfq`，消费者按 use case 取价，避免复权语义散落在业务代码里

## 2. 组件架构

```
┌─────────────────────────────────────────────────────┐
│                    config/settings.yaml               │
│              data_registry: declared dimensions        │
└──────────────────────┬──────────────────────────────┘
                       │ 声明式注册
┌──────────────────────▼──────────────────────────────┐
│                 DataRegistry                          │
│   get(key) / get_enabled() / get_available()          │
│   validate() — 合约检验 source/asset/status/freq      │
│   health_metadata() — DB Health 页面元数据             │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                    DataHub                            │
│   dimension_path(key, **values) — 注册表→具体路径      │
│   read_parquet / write_parquet — 原子写入 (tmp+rename) │
│   append_parquet — fcntl 锁 + 去重 + 排序             │
│   manifest — 每次写入记录元数据 (schema/row_count/sha) │
│   catalog() / audit() — 存储审计                       │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────────────┐
│   fetcher   │ │ cleaner   │ │  feature_store      │
│ AKShare 3源 │ │ 6 规则清洗 │ │ PIT 特征构建         │
│ 节流+重试   │ │ 异常值检测 │ │ as-of 日期视图       │
│ 两层缓存    │ │ 停牌填充  │ │ enrich 当日因子     │
└──────┬──────┘ └─────┬─────┘ └────────────────────┘
       │              │
┌──────▼──────────────▼──────────────────────────────┐
│              Fetchers (按数据源分包)                   │
│  stock_daily.py  financial.py  moneyflow.py           │
│  holders.py      macro.py                             │
└─────────────────────────────────────────────────────┘
```

### 2.1 DataRegistry — 声明式维度注册表

`config/settings.yaml` → `data_registry` 段，每个维度声明：
- `source`: akshare / tushare_free / tushare_paid / computed
- `asset`: stock / sector / macro / fund / futures / bond
- `status`: available / rate_limited / paid / planned
- `freq`: daily / monthly / quarterly / event / minute
- `cache`: 相对路径模板，如 `stock/daily/{symbol}.parquet`
- `health`: table / label / freshness_sla_days / repair_policy / partition_key

`DataRegistry.validate()` 在启动时运行合约检验，确保所有 enabled 维度 source/asset/status/freq/cache 字段合法。

行业/板块相关维度同样通过注册表管理，包括行业指数行情、行业成员映射、行业动量快照、行业信号聚合和组合行业敞口。上层代码不应硬编码任何 `var/store/*` 深层路径，而应使用 `DataHub.dimension_root()` 或 `DataHub.dimension_path()`。

Tushare 维度治理入口统一在 CLI：
- `astroq config env --json` 检查当前进程是否已配置 `TUSHARE_TOKEN` 和 LLM provider key，输出只包含脱敏状态。
- `astroq data tushare-audit --json` 探测当前账号可访问接口，并输出本地 `var/store` 覆盖率。
- `astroq data tushare-backfill --scope missing --resume --json` 按缺口补齐非分钟维度；`stk_mins` 分钟接口只审计权限，不默认全市场全历史拉取。

### 2.2 DataHub — 统一数据中台

`DataHub` 是外部稳定 facade，目标是把数据访问中心化，而不是让业务模块绕开它各自读写路径。内部实现按职责拆分：

| 内部组件 | 文件 | 职责 |
|----------|------|------|
| `DataHubPaths` | `data/storage/datahub_paths.py` | project/runtime/store/cache/artifact/db 路径、逻辑数据集路径、registry cache pattern 展开 |
| `ParquetStore` | `data/storage/datahub_parquet.py` | Parquet 读写、原子写入、追加锁、最新批次、目录扫描 |
| `ManifestStore` | `data/storage/datahub_manifest.py` | `_manifest/datasets.parquet` 读写、schema hash、文件 hash、日期范围 |
| `DimensionStore` | `data/storage/datahub_dimensions.py` | DataRegistry 维度 root/path/list/latest 解析 |

仓库内部代码依赖 canonical import：`data.storage.datahub.DataHub` / `get_datahub()`。`data/` 根目录不保留历史快捷入口；业务代码必须从对应领域分包导入。内部组件是 DataHub 的实现细节，用来降低维护复杂度，不替代 DataHub facade。

默认路径配置：

| 配置 | 默认值 | 环境变量覆盖 | 语义 |
|------|--------|--------------|------|
| `paths.runtime_root` | `var` | `ASTROLABE_VAR` | 本地运行产物根目录 |
| `paths.store_root` | `var/store` | - | DataHub 主数据 |
| `paths.cache_root` | `var/cache` | - | API、回测矩阵和运行缓存 |
| `paths.artifact_root` | `var/artifacts` | - | 回测、模型、锦标赛、报告 |
| `paths.db_root` | `var/db` | - | DuckDB/SQLite 本地数据库 |

新增公共路径 API：

```python
hub.runtime_dir()
hub.artifact_dir("backtests")
hub.artifact_path("models", "lgbm_best.pkl")
hub.db_path("quant_results.duckdb")
```

股票价格路径按口径显式分层：

| 维度 | 路径 | 语义 |
|------|------|------|
| `ohlcv_daily` | `stock/daily/{symbol}.parquet` | 研究/回测默认前复权视图 |
| `ohlcv_daily_raw` | `stock/daily_raw/{symbol}.parquet` | 未复权市场成交价 |
| `ohlcv_daily_hfq` | `stock/daily_hfq/{symbol}.parquet` | 后复权视图 |
| `adj_factor` | `stock/adj_factor/{symbol}.parquet` | Tushare 复权因子 |
| `corporate_actions` | `stock/corporate_actions/{symbol}.parquet` | 标准化现金分红和送转/拆股事件 |

| 操作 | 方法 | 关键保障 |
|------|------|---------|
| 读 | `read_parquet(path)` | 文件不存在返回 default |
| 写 | `write_parquet(df, path)` | tmp + os.replace 原子写入 |
| 追加 | `append_parquet(path, rows, dedupe, sort)` | fcntl.flock + drop_duplicates |
| 路径 | `dimension_path(key, **values)` | 注册表 pattern 展开为具体路径 |
| 清单 | `manifest` → `datasets.parquet` | 每次 write 记录 schema_hash/size/date_range |
| 审计 | `audit()` / `catalog()` | 遍历所有 dataset，统计文件数/大小 |

### 2.3 PriceService — 价格口径契约

`data/market/price_service.py` 是股票价格的统一入口。Fetcher 可以继续负责拉取和缓存，但策略、特征、回测、估值、执行和 Web 不应直接猜测某个 Parquet 的复权语义。

| Use case | 默认口径 | 典型消费者 |
|----------|----------|------------|
| `research` | `qfq` | 特征工程、研究分析 |
| `backtest` | `qfq` | 回测价格矩阵 |
| `signal` | `qfq` | 技术因子和策略信号 |
| `execution` | `raw` | PaperBroker/委托价格 |
| `valuation` | `raw` | DCF 当前价、持仓市值 |
| `display` | `raw` | Web 个股 K 线展示 |

`qfq` / `hfq` 优先由 `raw + adj_factor` 派生；若外部数据源临时不可用，读取层必须在 manifest 中记录 `requested_price_mode`、`price_mode`、`price_adjustment_source` 和 fallback reason。

公司行动不直接混入 OHLCV。`data/market/corporate_actions.py` 把 `dividend` 原始事件归一为 `corporate_actions`，并提供 `apply_corporate_actions_to_position()` 给未来回测账本处理现金分红、送转和拆股。

### 2.4 Fetcher — 数据获取层

**多源 fallback 链：** 新浪 → 东方财富 → 腾讯
**稳定性机制：**
- 代理绕过：自动清除 `http_proxy/https_proxy`，设置 `no_proxy` 包含 eastmoney.com/10jqka.com.cn/sina.com.cn
- 请求节流：全局最小间隔 3 秒（`threading.Lock` + `time.sleep`）
- 指数退避重试：2s → 4s → 8s，最多 3 次，识别 `ConnectionError/Timeout/ChunkedEncodingError`
- Socket 超时：30s 全局默认，防止 AKShare 长连接 hang

**两层缓存：**
1. 内存缓存（`_mem_cache` dict，max 64 entries）— 会话内避免重复磁盘读取
2. 磁盘缓存（Parquet，`var/cache/api/`）— 跨会话，三级 TTL：
   - TTL_FOREVER (365d): 历史数据永不过期
   - TTL_DAILY (24h): 日线行情
   - TTL_REALTIME (1h): 实时快照

**API 调用安全阀：** 默认 `get_stock_daily()` 只读本地 Parquet，不触网。设置 `QUANT_ALLOW_API_FALLBACK=1` 或 `force_refresh=True` 才发起 API 请求。

### 2.5 Cleaner — 6 规则数据清洗

规则注册表位于 `data/quality/cleaner.py` 的 `RULE_CLASSES`，启用和参数由 `config/settings.yaml` → `data_cleaning` 控制。

1. **OHLCVIntegrityRule** — 验证必需 OHLCV 列、修正 high/low/close 区间、移除非正价格或负成交量
2. **OutlierDetectionRule** — 对收益率极端值、异常单日涨跌幅和成交量尖峰做缩尾/回补
3. **SuspendedDetectionRule** — 连续价格不变超过阈值的停牌/退市段落移除
4. **MissingValueRule** — OHLCV 缺失值有限前向填充，仍缺 close 的行移除
5. **FinancialValidationRule** — 财务因子边界裁剪（ROE、利润率、D/E、PE、PB）
6. **WinsorizeRule** — 特征列按 1%/99% 默认分位缩尾

### 2.6 Feature Store — PIT 特征工程

**Point-in-Time 严格性：** 每个 as-of 切片只使用该日期及之前已可见的数据构建特征，绝不使用未来信息。日频价量、估值、资金流可以按交易日更新；财务、宏观、持有人等低频特征自然取 as-of 之前最新已披露值。
- 目标输出：`var/store/features/YYYY-MM-DD.parquet`
- 构建入口：`scripts/build_features.py --frequency daily`，以及 `FeatureStoreBuilder.build_asof(as_of_date, symbols)`
- 读取入口：`iter_feature_files()`、`load_feature_panel()`、`latest_feature_frame()`
- 注册表扩展：`enrich_from_registry(df, as_of_key, symbols)` 从 DataRegistry 维度补充资金流、持有人、宏观等 PIT 因子

### 2.6 Cron Logger — 可观测性

- 格式：JSONL (`var/store/_cron_log/{script}.jsonl`)
- 自动轮转：每文件最多 500 行
- 上下文管理器：`with cron_run("script_name") as log:`
- 方法：`log_cron_success()`, `log_cron_error()`, `get_recent_errors()`

## 3. 数据流

```
AKShare/Tushare API
       │
       ▼ (节流 3s + 重试 3 次)
  Fetcher._throttle() → retry_with_backoff()
       │
       ▼ (两层缓存检查)
  _read_cache(): 内存 → 磁盘 Parquet
       │ (未命中)
       ▼
  AKShare API 调用 → DataFrame
       │
       ▼ (清洗管道)
  CleanerRule.apply() × enabled rules
       │
       ▼ (原子写入)
  DataHub.write_parquet(): tmp → os.replace → manifest
       │
       ▼ (PIT 特征构建)
  build_features.py --frequency daily
       │
       ▼ (上层消费)
  Signals / Backtest / Broker / Web
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 存储格式 | Parquet (列存) | 压缩率高，pandas 原生支持，DuckDB 可直接查询 |
| 原子写入 | tmp + os.replace | POSIX 保证原子性，避免读到半写文件 |
| 追加锁 | fcntl.flock | 进程级文件锁，防止并发追加导致数据损坏 |
| 注册表驱动路径 | dimension_path(key, **params) | 消除硬编码路径，新增维度只需改 yaml |
| API 安全阀 | 默认不触网 | 回测和研究路径不应隐式触发网络请求 |
| 财务数据三层缓存 | 内存→Parquet→API | 财务数据拉取慢（逐只股票），最大化缓存命中 |
| DataHub facade | 外部 API 稳定，内部组件化 | 降低 DataHub 文件复杂度，不打散数据访问中心 |

## 5. 接口合约

### DataHub 核心接口

```python
# 路径解析 — 上层不应硬编码路径
hub.dimension_path("ohlcv_daily", symbol="000001")
# → var/store/stock/daily/000001.parquet
hub.artifact_path("backtests", "backtest_ml_lgbm.pkl")
hub.db_path("quant_results.duckdb")
hub.stock_daily_raw_path("000001")
hub.stock_adj_factor_path("000001")
hub.stock_corporate_actions_path("000001")

# 读写
hub.read_parquet(path, default=pd.DataFrame())
hub.write_parquet(df, path, producer="script_name")
hub.append_parquet(path, rows, dedupe_subset=["date", "symbol"])

# 审计
hub.audit(include_rows=True)
hub.catalog()
```

### Fetcher 核心接口

```python
get_stock_daily(symbol, adjust="qfq")       → pd.DataFrame
get_index_daily(symbol="sh000001")          → pd.DataFrame
get_financial_indicator(symbol)             → pd.DataFrame
get_stock_spot()                            → pd.DataFrame
provider.fetch("sw_daily", trade_date=...)  → pd.DataFrame
```

### PriceService 核心接口

```python
get_stock_prices("000001", use_case="backtest")   → qfq OHLCV
get_stock_prices("000001", use_case="execution")  → raw OHLCV
get_stock_price_matrix(pool, use_case="backtest") → qfq close matrix + panels
load_corporate_actions("000001")                  → normalized corporate_actions
apply_corporate_actions_to_position(...)          → adjusted shares/cash
```

### Feature Store 核心接口

```python
builder = FeatureStoreBuilder(alpha_factors())
builder.build_asof("2026-05-08", symbols)   → pd.DataFrame | None
latest_feature_frame()                      → pd.DataFrame
load_feature_panel()                        → pd.DataFrame
```

### DataRegistry 核心接口

```python
reg = get_registry()
reg.get("ohlcv_daily")          → DataDimension
reg.get_enabled()               → List[DataDimension]
reg.get_available()             → List[DataDimension] (status=available + enabled)
reg.validate()                  → List[str] (合约问题清单)
reg.health_metadata()           → dict[str, HealthTableMeta]
```

## 6. 错误处理

- **API 不可达：** 指数退避重试 3 次后返回空 DataFrame，不抛异常
- **数据为空：** 所有 read 方法接受 `default` 参数，文件不存在返回 default
- **Manifest 写入失败：** 静默捕获异常，Manifest 是元数据，不能阻塞数据写入
- **并发追加：** fcntl 锁保护，超时时由 OS 处理
- **代理干扰：** 启动时自动清除代理环境变量

## 7. 测试策略

- **合约测试：** `tests/` 中验证 DataRegistry.validate() 对所有已知维度的配置格式正确，`tests/test_price_service_contracts.py` 覆盖 `PriceService` 口径、manifest 元数据、`corporate_actions` 和主要消费者 use case
- **边界测试：** 空 DataFrame 读写、不存在文件读取、并发追加去重
- **集成测试：** `get_stock_daily("000001")` 返回有效 DataFrame（需本地已有数据）
- **回归测试：** Manifest schema_hash 变化检测
- **行业数据测试：** 行业快照构建、行业动量 contract、行业信号/敞口 schema 由 `tests/test_sector_pipeline.py` 覆盖

## 8. 已知限制 & 未来方向

- **AKShare 网络不稳定：** 新浪源偶尔限流，已通过 3 源 fallback 缓解
- **多资产回测数据质量不均：** ETF 适配器已有真实行情路径，但 `scripts/multi_asset_tournament.py` 仍可能在缺少本地缓存时使用 proxy（见 [06-multi-asset.md](06-multi-asset.md)）
- **Tushare 权限与限流：** 以 `astroq data tushare-audit --json` 的当前账号探测为准；权限缺失标记为 `no_permission`，限流维度由 `tushare-backfill`/cron 分批补齐
- **未来：** 可接入 Wind/Choice 等专业数据终端，并把付费/限流源统一纳入 DataRegistry SLA
