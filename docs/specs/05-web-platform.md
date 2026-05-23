# Spec: Web 平台 (Web Platform)

> 版本: 2.1 | 更新: 2026-05-23 | 关联: [PRD](../PRD.md) [Data Pipeline](01-data-pipeline.md) [Signal System](02-signal-system.md)

## 1. 概述

Web 平台提供 Quantum Terminal — Vue 3 SPA 前端 + FastAPI 后端 + WebSocket 实时推送。一级导航收敛为市场总览、市场研究、策略实验室、组合执行、数据中台、系统控制；原子功能通过二级 tab 或兼容 redirect 访问。

**设计原则：**
- **前后端分离** — Vue 3 (Vite) + FastAPI，独立开发/部署
- **零锁查询** — DuckDB :memory: 模式直接读 Parquet，不经过数据库锁
- **实时推送** — WebSocket 推送长时间任务（回测/训练）的进度
- **职责分离** — `/system?tab=monitor` 只读观测, `/system?tab=settings` 配置管理, 不交叉

## 2. 组件架构

```
┌─────────────────────────────────────────────────────┐
│              web/frontend/ (Vue 3 + Vite)             │
│   Pinia Store → Components → ECharts + Tailwind       │
│   Router: market / research / strategy-lab             │
│           portfolio / datahub / system                 │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP REST + WebSocket
┌──────────────────────▼──────────────────────────────┐
│              web/api/ (FastAPI)                        │
│   create_app() → CORS → Router → Error Handler        │
│   routes/ (10 domain modules) + ws.py + jobs.py        │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                 Data Layer                             │
│   DuckDB :memory: ← Parquet files (zero-lock reads)   │
│   DataHub.read_parquet() / dimension_path()            │
└─────────────────────────────────────────────────────┘
```

### 2.1 前端架构 (Vue 3 SPA)

**技术栈：** Vue 3 (Composition API) + ECharts (图表) + Tailwind CSS (样式) + Vite (构建)

**一级导航 (6 个入口):**

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | 市场总览 | Regime 球体 + 多资产卡片(含 data_source) + 宏观快照 + 策略矩阵 + 预警面板 |
| `/research` | 市场研究 | 二级 tab: 行业雷达、个股搜索；个股详情仍使用隐藏路由 `/stocks/:code` |
| `/strategy-lab` | 策略实验室 | 二级 tab: 策略中心、信号历史、回测分析 |
| `/portfolio` | 组合执行 | PaperBroker 持仓 + NAV 曲线 + 交易记录 + 手动下单 |
| `/datahub` | 数据中台 | DataRegistry 启用维度健康扫描 + 大小统计 + 单表修复 |
| `/system` | 系统控制 | 二级 tab: 系统信息、系统设置、记忆图谱 |

**兼容 redirect：** `/strategies`、`/signals`、`/backtest`、`/stocks`、`/sectors`、`/monitor`、`/settings`、`/db-health`、`/hindsight` 保留为旧入口重定向，不作为一级导航展示。

### 2.2 后端架构 (FastAPI)

**应用工厂：** `web/api/__init__.py` → `create_app()` → 注册路由 + CORS + 异常处理

**10 个业务路由模块 + Auth/WS/Jobs：**

| 模块 | 文件 | 端点 |
|------|------|------|
| Market | `routes/market.py` | `GET /market`, `GET /market/regime` |
| Stocks | `routes/stocks.py` | `GET /stocks/{code}`, `GET /stocks/{code}/kline` |
| Signals | `routes/signals.py` | `GET /signals/changes`, `GET /signals/{strategy}` |
| Strategies | `routes/strategies.py` | `GET /strategies`, `GET /strategies/{name}`, `GET /strategies/statuses`, `POST /strategies/run` |
| Backtest | `routes/backtest.py` | `GET /backtest`, `GET /backtest/{key}` |
| Portfolio | `routes/portfolio.py` | `GET /portfolio/positions`, `GET /portfolio/balance`, `POST /portfolio/order` |
| Sectors | `routes/sectors.py` | `GET /sectors/overview`, `GET /sectors/exposure`, `GET /sectors/{industry}`, `GET /sectors/{industry}/stocks` |
| Settings | `routes/settings.py` | `GET /settings`, `PUT /settings` |
| System | `routes/system.py` | `GET /system/monitor`, `GET /system/history`, `GET /system/api-health`, `GET /system/cron-jobs`, `GET /system/service-status`, `GET /system/audit`, `GET /system/mode` |
| Hindsight | `routes/hindsight.py` | `POST /hindsight/query` |
| Auth | `auth.py` | Bearer token 中间件 + CORS/OPTIONS 放行 |

**WebSocket：** `ws.py` → `/ws/{job_id}` — 任务进度实时推送。`broadcast_progress()` 使用 `list()` 拍平连接集合避免并发修改异常。

**任务队列：** `jobs.py` → `JobQueue` — 异步执行数据拉取/回测/模型训练，进度通过 WebSocket 推送。

### 2.3 DuckDB :memory: 查询

**设计理念：** FastAPI 启动时创建 DuckDB :memory: 实例，注册 Parquet 视图。所有查询零锁等待（DuckDB 只读 Parquet 不需要写锁）。

```python
# web/api/db.py — 简化示例
def get_db() -> Database:
    db = Database(backend="duckdb")
    db.connect(read_only=True)
    return db
```

## 3. 数据流

```
Browser (Vue 3)
    │  HTTP GET /signals/buffett
    ▼
FastAPI Route Handler
    │  hub.read_parquet(signal_path)
    ▼
DataHub → pd.read_parquet("data/store/signals/buffett.parquet")
    │  DataFrame
    ▼
Pydantic Model Serialization → JSON Response
    │
    ▼
Pinia Store → Vue Component → ECharts 渲染
```

**WebSocket 流：**
```
POST /backtest/run
    │ 创建 Job
    ▼
JobQueue.add(job) → 后台线程执行
    │ 每完成一步
    ▼
broadcast_progress(job_id, {"step": 3/5, "message": "..."})
    │ WebSocket
    ▼
Vue Component 实时更新进度条
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 前端框架 | Vue 3 + Vite | 轻量 SPA，Vite HMR 开发体验好，Tailwind 原子化 CSS |
| 后端框架 | FastAPI | 原生 async、自动 OpenAPI 文档、Pydantic 类型校验 |
| 数据库 | DuckDB :memory:（只读 Parquet） | 查询零锁等待，不需要数据库服务器 |
| 长任务处理 | WebSocket 推送进度 | 回测/训练可能跑几分钟，HTTP 轮询太低效 |
| 状态管理 | Pinia (per-page stores) | 页面间独立，不需要全局状态 |
| 配置管理 | YAML → Pydantic 校验 | settings.yaml 人类可读写 + API 层类型安全 |

## 5. 接口合约

### REST API 约定

- 成功响应优先使用页面/领域 payload shape；有稳定 schema 的端点使用 Pydantic `response_model`
- 错误响应由 `web/api/errors.py` 统一为 `{"error": ..., "detail": ..., "timestamp": ...}`
- 分页：`?page=1&page_size=50`
- 过滤：`?strategy=buffett&date=2026-05-20`
- 排序：`?sort_by=score&order=desc`

### WebSocket 消息格式

```json
{
  "type": "progress",
  "job_id": "uuid",
  "step": 3,
  "total_steps": 5,
  "message": "Training LightGBM model...",
  "percent": 60.0
}
```

### Settings API 安全校验

```python
# Pydantic 校验
class SettingsUpdate(BaseModel):
    strategies: dict | None
    risk_control: dict | None

# 必须段校验
REQUIRED_SECTIONS = {"strategies", "risk_control"}

# 策略名白名单
ALLOWED_STRATEGIES = list_strategy_names()
```

## 6. 错误处理

- **404：** 资源不存在 → `{"error": "Stock not found: 999999", "timestamp": "..."}`
- **422：** Pydantic 校验失败 → FastAPI 自动返回字段级错误
- **500：** 未捕获异常 → `errors.py` 全局处理器统一格式化
- **WebSocket 断连：** 前端指数退避重连（1s → 2s → 4s，最多 5 次）
- **Settings 更新非法：** 更新端点校验 section 白名单和关键字段，非法配置返回 4xx

## 7. 测试策略

- **合约测试：** 所有路由返回正确的 HTTP 状态码和 JSON schema
- **集成测试：** `GET /signals/buffett` 返回实际数据（需本地有信号文件）
- **WebSocket 测试：** 创建 Job → 验证进度消息格式
- **Settings 测试：** 非法配置更新返回 422，白名单外策略名返回 400
- **边界测试：** 空 Parquet 文件返回空列表，分页越界返回空数组

## 8. 已知限制 & 未来方向

- **行业/板块雷达页面** — 已合入 `/research?tab=sectors`，展示申万行业动量排名、策略信号分布和组合行业敞口；数据只读本地 `sector/*_snapshot` 缓存。
- **无移动端适配** — 当前仅桌面浏览器布局
- **DuckDB 只读** — 所有写操作通过 API 触发 Python 端 DataHub，不经过 DuckDB
- **未来：** 策略参数热调、回测结果交互式下钻、前端 smoke/e2e 自动化继续扩大到视觉回归。
