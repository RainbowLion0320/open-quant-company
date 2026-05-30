# Spec: Web 平台 (Web Platform)

> 版本: 2.3 | 更新: 2026-05-30 | 关联: [PRD](../PRD.md) [Data Pipeline](01-data-pipeline.md) [Signal System](02-signal-system.md)

## 1. 概述

Web 平台提供 星盘终端 — Vue 3 SPA 前端 + FastAPI 后端 + WebSocket 实时推送。一级导航收敛为市场总览、市场研究、策略实验室、组合执行、流程图、数据中台、系统控制；原子功能通过二级 tab 或关键参数 Pipeline 访问。

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
│           portfolio / pipeline / datahub / system      │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP REST + WebSocket
┌──────────────────────▼──────────────────────────────┐
│              web/api/ (FastAPI)                        │
│   create_app() → CORS → Router → Error Handler        │
│   routes/ (11 domain modules) + ws.py + jobs.py        │
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

**一级导航 (7 个入口):**

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | 市场总览 | Regime 球体 + 数值分数 + 4 个小仪表盘 + 状态卡 + 核心指数相对强弱图 + 宏观快照 + 热门行业脉冲 |
| `/research` | 市场研究 | 二级 tab: 行业雷达、个股搜索；行业雷达以行业资金方块矩阵为主视图，个股详情仍使用隐藏路由 `/stocks/:code` |
| `/strategy-lab` | 策略实验室 | 二级 tab: 策略目录、信号历史、回测证据 |
| `/portfolio` | 组合执行 | PaperBroker 持仓 + NAV 曲线 + 交易记录 + 手动下单 |
| `/pipeline` | 流程图 | 关键参数计算透明度入口；v1 展示 Market Regime 7 节点计算链路 |
| `/datahub` | 数据中台 | DataRegistry 启用维度健康扫描 + 大小统计 + 单表修复 |
| `/system` | 系统控制 | 二级 tab: 系统信息、系统设置、记忆图谱 |

旧一级页面 redirect 已移除。除 `/stocks/:code` 个股详情隐藏路由外，用户应通过七个一级模块、二级 tab 和 Pipeline 透明度页访问原子功能。

**市场总览 Regime 面板契约：**

- 顶部为 animated regime orb + confirmed regime 名称 + 居中纯数字 score；不再额外显示分数字段标题或卡片边框。
- 中部保留 4 个核心小仪表盘：Risk Buffer、A-share Breadth、Index Trend、Above MA20。
- 稳定性状态以紧凑状态卡展示 Confirmed / Raw / Pending / Dwell；Pending 空闲时显示 `—`，有候选时显示 `x/y`。
- 全局页脚只展示 MODE / REGIME / FRESH 与系统健康状态，不再承担行情 ticker 或点位/日涨跌展示。

**市场研究行业雷达契约：**

- `GET /api/sectors/overview` 返回 `turnover_amount`、`amount_5d_avg`、`amount_share`、`amount_source` 和 `capital_source`，供前端表达行业资金分布。
- 行业雷达主视图为行业资金方块矩阵：每个申万一级行业是独立方块，边长按近 5 日平均成交额开方映射，保持方形且让面积近似表达资金量；缺失时回退成份股数量并在 UI 标注口径。
- 行业方块内部不展示具体股票，避免行业雷达变成个股看板；方块矩阵支持资金热力、动量热力、信号热力三种模式。点击行业方块同步展开行业级信号分布，不替代精确排名表。

**策略实验室契约：**

- 默认 tab 是 Strategy Catalog，对应 `GET /api/strategies/catalog`。
- 首屏必须展示策略目录、生命周期、策略类型、研究层级、数据需求、最新扫描和动作。
- 当存在 `candidate` / `validated` 策略时，必须展示生产隔离横幅：候选策略只允许研究扫描和回测，不参与生产信号。
- 候选策略动作标记为“研究扫描”，前端调用 `POST /api/strategies/run` 时使用 `mode=research`；生产策略和“运行生产策略”使用 `mode=production`。
- `GET /api/strategies/evaluation` 返回强基准和候选晋级证据要求，回测证据 tab 用于承接后续 artifact 下钻。

**Pipeline 页面契约：**

- `/pipeline` 是一级页面，不归入 Market 或 System 的二级 tab。
- v1 只展示 `market_regime` 关键参数计算链路：`inputs`、`features`、`rule_score`、`hmm_inference`、`hybrid_decision`、`stability`、`outputs` 七个固定节点。
- 前端不引入新图形库，使用 Vue + CSS grid + inline SVG arrows；节点可点击，右侧详情面板展示节点输入、输出和关键指标。
- Pipeline 页面用于解释关键参数如何形成，不替代市场总览页面的行情、宏观和热门行业展示。

### 2.2 后端架构 (FastAPI)

**应用工厂：** `web/api/__init__.py` → `create_app()` → 注册路由 + CORS + 异常处理

**11 个业务路由模块 + Auth/WS/Jobs：**

| 模块 | 文件 | 端点 |
|------|------|------|
| Market | `routes/market.py` | `GET /market`, `GET /market/regime` |
| Stocks | `routes/stocks.py` | `GET /stocks/{code}`, `GET /stocks/{code}/kline` |
| Signals | `routes/signals.py` | `GET /signals/changes`, `GET /signals/{strategy}` |
| Strategies | `routes/strategies.py` | `GET /strategies`, `GET /strategies/catalog`, `GET /strategies/evaluation`, `GET /strategies/{name}`, `GET /strategies/statuses`, `POST /strategies/run` |
| Backtest | `routes/backtest.py` | `GET /backtest`, `GET /backtest/{key}` |
| Portfolio | `routes/portfolio.py` | `GET /portfolio/positions`, `GET /portfolio/balance`, `POST /portfolio/order` |
| Sectors | `routes/sectors.py` | `GET /sectors/overview`, `GET /sectors/exposure`, `GET /sectors/{industry}` |
| Pipeline | `routes/pipeline.py` | `GET /pipeline/market-regime` |
| Settings | `routes/settings.py` | `GET /settings`, `PUT /settings` |
| System | `routes/system.py` | `GET /system/monitor`, `GET /system/history`, `GET /system/api-health`, `GET /system/cron-jobs`, `GET /system/service-status`, `GET /system/audit`, `GET /system/mode` |
| Hindsight | `routes/hindsight.py` | `GET /hindsight/graph` |
| Auth | `auth.py` | Bearer token 中间件 + CORS/OPTIONS 放行 |

**Pipeline API 契约：**

`GET /api/pipeline/market-regime` 返回稳定 JSON：

- `pipeline_key: "market_regime"`
- `updated`
- `summary`: confirmed/raw regime、score、engine、detection_method、confidence、entropy、adaptive_params
- `nodes`: 固定 7 节点数组
- `edges`: 节点连线数组，source/target 必须引用有效 node id
- `warnings`: HMM 模型缺失、fallback、样本不足等提示

服务端复用 `QuantOrchestrator().detect()` 输出的 `score_components`、`breadth_detail`、`regime_probs`、`detection_method` 和 HMM `meta.json`，不得在 API 层重写 Market Regime 计算公式。

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

### 2.4 Agent-facing Control Plane

`astroq` 是 Web/API 之外的本地控制平面，用于 agent、cron 和人工维护。CLI 只做编排：策略扫描仍走 `data.strategy_plugins`，数据修复仍走 `scripts.repair_table`，Web 服务仍走 `uvicorn web.api.app:create_app`。所有 agent 依赖命令必须支持 `--json`。

| 命令域 | 命令 | 契约 |
|--------|------|------|
| Health | `astroq health --json` | 返回项目版本、DataHub store/cache 路径 |
| Config | `astroq config validate --json` | 校验 settings 和策略注册表 |
| Data | `astroq data status --json` / `astroq data repair <table> --dry-run --json` | 委托 DB health 和单表修复，dry-run 不触发写入 |
| Strategy | `astroq strategy catalog --json` / `astroq strategy run <name|all>` | 委托 Strategy Catalog 和 runtime gates，candidate 必须显式 `--mode research` |
| Regime | `astroq regime status --json` / `astroq regime train-profit --dry-run --json` | 读取当前生产 regime；训练命令默认可 dry-run |
| Backtest | `astroq backtest run [--strategy NAME] --dry-run --json` | 委托回测 runner，不在 CLI 重写回测逻辑 |
| Docs | `astroq docs check --json` | 扫描已知陈旧文档短语 |
| Web | `astroq web build --json` / `astroq web serve --host HOST --port PORT` | 委托 Vite build 和 FastAPI/uvicorn |

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

- **行业/板块雷达页面** — 已合入 `/research?tab=sectors`，展示申万行业动量排名和策略信号分布；组合行业敞口归属 `/portfolio`，避免研究页重复持仓归因。
- **无移动端适配** — 当前仅桌面浏览器布局
- **DuckDB 只读** — 所有写操作通过 API 触发 Python 端 DataHub，不经过 DuckDB
- **Pipeline v2 规划：** Pipeline 页面当前 v1 只覆盖 Market Regime。后续 Pipeline v2 应扩展到 Data Quality、Strategy Evidence、Portfolio/Execution 三条关键链路。
- **Web API 契约：** Web API 的稳定契约以 Pydantic `response_model` 和前端 TypeScript 类型共同约束；新关键端点必须同时补齐后端模型、前端类型和合约测试。
- **未来：** 策略参数热调、回测结果交互式下钻、前端 smoke/e2e 自动化继续扩大到视觉回归。
