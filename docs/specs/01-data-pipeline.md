# Spec: 数据管道 (Data Pipeline)

> 版本: 1.1 | 更新: 2026-05-23 | 关联: [PRD](../PRD.md) [Signal System](02-signal-system.md)

## 1. 概述

数据管道负责从多源拉取、清洗、缓存、存储 A 股全量数据，并通过 DataHub 统一路径向上层（信号/回测/执行/Web）暴露。覆盖维度由 `config/settings.yaml` 的 `data_registry` 声明，按频率分为日频（行情/估值/资金流向/行业快照）、月频/季频（财务指标/三张表）、事件驱动（龙虎榜/研报/限售解禁）。

**核心理念：**
- **离线优先** — 所有数据存储为本地 Parquet，不依赖云端数据库
- **多源互补** — AKShare（免费不限流，行情）+ Tushare（深度财务数据）
- **声明式注册** — 数据维度统一在 `settings.yaml` → `DataRegistry` 中声明，含 source/label/SLA/repair/partition

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
│ 节流+重试   │ │ 异常值检测 │ │ 月度切片 (YYYY-MM)  │
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
- `freq`: daily / monthly / quarterly / event
- `cache`: 相对路径模板，如 `stock/daily/{symbol}.parquet`
- `health`: table / label / freshness_sla_days / repair_policy / partition_key

`DataRegistry.validate()` 在启动时运行合约检验，确保所有 enabled 维度 source/asset/status/freq/cache 字段合法。

行业/板块相关维度同样通过注册表管理，包括行业指数行情、行业成员映射、行业动量快照、行业信号聚合和组合行业敞口。上层代码不应硬编码 `data/store/sector/*` 路径，而应使用 `DataHub.dimension_root()` 或 `DataHub.dimension_path()`。

### 2.2 DataHub — 统一数据中台

| 操作 | 方法 | 关键保障 |
|------|------|---------|
| 读 | `read_parquet(path)` | 文件不存在返回 default |
| 写 | `write_parquet(df, path)` | tmp + os.replace 原子写入 |
| 追加 | `append_parquet(path, rows, dedupe, sort)` | fcntl.flock + drop_duplicates |
| 路径 | `dimension_path(key, **values)` | 注册表 pattern 展开为具体路径 |
| 清单 | `manifest` → `datasets.parquet` | 每次 write 记录 schema_hash/size/date_range |
| 审计 | `audit()` / `catalog()` | 遍历所有 dataset，统计文件数/大小 |

### 2.3 Fetcher — 数据获取层

**多源 fallback 链：** 新浪 → 东方财富 → 腾讯
**稳定性机制：**
- 代理绕过：自动清除 `http_proxy/https_proxy`，设置 `no_proxy` 包含 eastmoney.com/10jqka.com.cn/sina.com.cn
- 请求节流：全局最小间隔 3 秒（`threading.Lock` + `time.sleep`）
- 指数退避重试：2s → 4s → 8s，最多 3 次，识别 `ConnectionError/Timeout/ChunkedEncodingError`
- Socket 超时：30s 全局默认，防止 AKShare 长连接 hang

**两层缓存：**
1. 内存缓存（`_mem_cache` dict，max 64 entries）— 会话内避免重复磁盘读取
2. 磁盘缓存（Parquet，`data/cache/api/`）— 跨会话，三级 TTL：
   - TTL_FOREVER (365d): 历史数据永不过期
   - TTL_DAILY (24h): 日线行情
   - TTL_REALTIME (1h): 实时快照

**API 调用安全阀：** 默认 `get_stock_daily()` 只读本地 Parquet，不触网。设置 `QUANT_ALLOW_API_FALLBACK=1` 或 `force_refresh=True` 才发起 API 请求。

### 2.4 Cleaner — 6 规则数据清洗

1. **MissingValueRule** — 缺失值前向填充
2. **OutlierDetectionRule** — 涨跌幅 > 阈值（默认 11%）用前一日收盘价修正
3. **SuspensionRule** — 连续停牌 > N 天标记
4. **DuplicateRule** — 按 date 去重
5. **NegativePriceRule** — 负价格修正为 NaN
6. **VolumeSpikeRule** — 成交量突增 > N 倍标准差标记

### 2.5 Feature Store — PIT 特征工程

**Point-in-Time 严格性：** 每个月切片使用该月最后一天之前的所有数据构建特征，绝不使用未来信息。
- 输出：`data/store/features/YYYY-MM.parquet`
- `enrich()` 方法支持当日因子实时计算（不上报 PIT 特征存储）

### 2.6 Cron Logger — 可观测性

- 格式：JSONL (`data/store/_cron_log/{script}.jsonl`)
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
  CleanerRule.apply() × 6
       │
       ▼ (原子写入)
  DataHub.write_parquet(): tmp → os.replace → manifest
       │
       ▼ (PIT 特征构建)
  FeatureStore.build_slice(month)
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

## 5. 接口合约

### DataHub 核心接口

```python
# 路径解析 — 上层不应硬编码路径
hub.dimension_path("ohlcv_daily", symbol="000001")
# → data/store/stock/daily/000001.parquet

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

- **合约测试：** `tests/` 中验证 DataRegistry.validate() 对所有已知维度的配置格式正确
- **边界测试：** 空 DataFrame 读写、不存在文件读取、并发追加去重
- **集成测试：** `get_stock_daily("000001")` 返回有效 DataFrame（需本地已有数据）
- **回归测试：** Manifest schema_hash 变化检测
- **行业数据测试：** 行业快照构建、行业动量 contract、行业信号/敞口 schema 由 `tests/test_sector_pipeline.py` 覆盖

## 8. 已知限制 & 未来方向

- **AKShare 网络不稳定：** 新浪源偶尔限流，已通过 3 源 fallback 缓解
- **多资产回测数据质量不均：** ETF 适配器已有真实行情路径，但 `multi_asset_tournament.py` 仍可能在缺少本地缓存时使用 proxy（见 [06-multi-asset.md](06-multi-asset.md)）
- **Tushare 2000 积分限制：** 部分维度 status=rate_limited，需 `cron_fetch_slow.py` 分批拉取
- **未来：** 可接入 Wind/Choice 等专业数据终端，并把付费/限流源统一纳入 DataRegistry SLA
