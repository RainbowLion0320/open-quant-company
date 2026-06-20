# Spec: Web 平台 (Web Platform)

> 版本: 2.8 | 更新: 2026-06-14 | 关联: [PRD](../product/prd.md) [Data Pipeline](01-data-pipeline.md) [Signal System](02-signal-system.md) [Agent Company OS](07-agent-company-os.md)

## 1. 概述

Web 平台提供 Open Quant Company Console — Vue 3 SPA 前端 + FastAPI 后端 + WebSocket 实时推送。当前一级导航收敛为 CEO Office、市场总览、市场研究、策略实验室、组合执行、流程图、数据中台、系统控制；原子功能通过二级 tab、关键参数 Pipeline 或 CEO Office evidence deep link 访问。

Agent Company OS 已将默认 `/` 迁移为 CEO Office 对话主控页，原市场总览迁移到 `/market`。Agent Company OS 的完整长期契约见 [07-agent-company-os.md](07-agent-company-os.md)。

**设计原则：**
- **前后端分离** — Vue 3 (Vite) + FastAPI，独立开发/部署
- **零锁查询** — DuckDB :memory: 模式直接读 Parquet，不经过数据库锁
- **异步进度** — WebSocket 跟踪策略扫描等后台任务的进度
- **职责收敛** — `/system?tab=settings` 只读展示 API Health、Cron Jobs 和当前配置摘要; `/system?tab=config` 只读展示参数 schema 和当前值，配置修改由 agent/CLI/API 执行
- **证据下钻** — CEO Office 只汇总行动和证据，详细数据、策略、生命周期、CodeGraph、AST 和测试设计仍由对应页面承载

## 2. 组件架构

```
┌─────────────────────────────────────────────────────┐
│              web/frontend/ (Vue 3 + Vite)             │
│   Pinia Store → Components → ECharts + Tailwind       │
│   Router: CEO Office / market / research / strategy-lab │
│           portfolio / pipeline / datahub / system       │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP REST + WebSocket
┌──────────────────────▼──────────────────────────────┐
│              web/api/ (FastAPI)                        │
│   app.py:create_app() → CORS → Router → Error Handler │
│   routes/ (14 domain modules) + ws.py + jobs.py        │
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

**当前一级导航 (8 个入口):**

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | CEO Office | 用户作为 CEO 直接描述需求，系统自动分配主责 desk agent，在消息内查看证据并处理需要审批的行动 |
| `/market` | 市场总览 | Regime 球体 + 数值分数 + 4 个小仪表盘 + 状态卡 + 核心指数相对强弱图 + 宏观快照 + 热门行业脉冲 |
| `/research` | 市场研究 | 二级 tab: 行业雷达、个股搜索；行业雷达以行业资金方块矩阵为主视图，个股详情仍使用隐藏路由 `/stocks/:code` |
| `/strategy-lab` | 策略实验室 | 二级 tab: 策略目录、信号历史、回测分析、证据面板 |
| `/portfolio` | 组合执行 | PaperBroker 持仓 + NAV 曲线 + 交易记录 + 手动下单 |
| `/pipeline` | 流程图 | 关键参数计算透明度入口；展示四条关键链路，Market Regime 为细粒度 DAG |
| `/datahub` | 数据中台 | 二级 tab: 健康扫描、资产覆盖、数据源能力；展示 DataRegistry 健康、本地覆盖和外部 source capability diff |
| `/system` | 系统控制 | 二级 tab: 系统设置、配置中心、测试设计、AST 检测、代码图谱与架构诊断 |

旧一级页面 redirect 已移除。除 `/stocks/:code` 个股详情隐藏路由外，用户应通过八个一级模块、二级 tab 和 Pipeline 透明度页访问原子功能。

**Agent Company OS evidence deep links:**

| 路由 | 页面 | 功能 |
|------|------|------|
| `/system?tab=lifecycle` | 生命周期证据链 | 作为 CEO Office evidence deep link，不被对话页复制全部细节 |
| `/datahub?tab=sources` | 数据源矩阵 | 作为 Data Desk evidence deep link |
| `/strategy-lab?tab=evidence` | 策略证据 | 作为 Research Desk evidence deep link |

该设计必须保留可回溯性：CEO Office 只做主控和摘要，不能替代 DataHub、Strategy Lab、Pipeline、System 等专业视图。
CEO Office 也不展示 autonomy step/run/program 或 provider 调试控件；这些能力只作为 CLI/API/internal runtime 机制保留。

**市场总览 Regime 面板契约：**

- 顶部为 animated regime orb + confirmed regime 名称 + 居中纯数字 score；不再额外显示分数字段标题或卡片边框。
- 中部保留 4 个核心小仪表盘：Risk Buffer、A-share Breadth、Index Trend、Above MA20。
- 稳定性状态以紧凑状态卡展示 Confirmed / Raw / Pending / Dwell；Pending 空闲时显示 `—`，有候选时显示 `x/y`。
- 全局页脚只展示 REGIME / FRESH、CEO 会话模型上下文和三态纯色系统健康灯，不再承担行情 ticker、文字健康状态或点位/日涨跌展示。

**市场研究行业雷达契约：**

- `GET /api/sectors/overview` 返回 `turnover_amount`、`amount_5d_avg`、`amount_share`、`amount_source` 和 `capital_source`，供前端表达行业资金分布。
- 行业雷达主视图为行业资金方块矩阵：每个申万一级行业是独立方块，边长按近 5 日平均成交额开方映射，保持方形且让面积近似表达资金量；缺失时回退成份股数量并在 UI 标注口径。
- 行业方块内部不展示具体股票，避免行业雷达变成个股看板；方块矩阵支持资金热力、动量热力、信号热力三种模式。点击行业方块同步展开行业级信号分布，不替代精确排名表。

**策略实验室契约：**

- 默认 tab 是 Strategy Catalog，对应 `GET /api/strategies/catalog`。
- 首屏必须展示策略目录、生命周期、策略类型、研究层级、数据需求、最新扫描和动作。
- 当存在 `candidate` / `validated` 策略时，必须展示生产隔离横幅：候选策略只允许研究扫描和回测，不参与生产信号。
- 候选策略动作标记为“研究扫描”，前端调用 `POST /api/strategies/run` 时使用 `mode=research`；生产策略和“运行生产策略”使用 `mode=production`。
- `GET /api/strategies/evaluation` 返回强基准和候选晋级证据要求；`GET /api/strategies/evidence` 返回策略目录与 artifact 合并后的 evidence 状态，缺失报告必须显式显示 `missing`，不能只展示已有文件。

**Pipeline 页面契约：**

- `/pipeline` 是一级页面，不归入 Market 或 System 的二级 tab。
- 当前支持 `market_regime`、`data_quality`、`strategy_evidence`、`portfolio_execution` 四条关键链路。`market_regime` 展示从市场输入、benchmark/breadth/volume 快照、规则评分、HMM 特征与推断、engine/hybrid/置信度决策分支、raw regime、dwell gate 到下游输出的细粒度 DAG。
- 前端使用 `elkjs` layered + orthogonal routing 生成流程布局，节点高度按内容测量自适应；节点可点击，右侧详情面板展示节点输入、输出和全部关键指标；选中节点时关联边保持可见并显示流动高亮。
- Pipeline 页面用于解释关键参数如何形成，不替代市场总览页面的行情、宏观和热门行业展示。

### 2.2 后端架构 (FastAPI)

**应用工厂：** `web/api/app.py` → `create_app()` → 注册 CORS、AuthMiddleware、当前业务路由、错误处理和生产静态文件 fallback。`web/api/__init__.py` 只保留包级说明。

**14 个业务路由模块 + Auth/WS/Jobs：**

| 模块 | 文件 | 端点 |
|------|------|------|
| Market | `routes/market.py` | `GET /api/market`, `GET /api/market/regime` |
| Stocks | `routes/stocks.py` | `GET /api/stocks`, `GET /api/stocks/{code}`, `POST /api/stocks/dcf` |
| Signals | `routes/signals.py` | `GET /api/signals/changes` |
| Strategies | `routes/strategies.py` | `GET /api/strategies`, `GET /api/strategies/statuses`, `GET /api/strategies/governance`, `GET /api/strategies/catalog`, `GET /api/strategies/evaluation`, `GET /api/strategies/evidence`, `GET /api/strategies/evidence/{strategy}`, `GET /api/strategies/jobs/{job_id}`, `GET /api/strategies/{name}`, `POST /api/strategies/run` |
| Backtest | `routes/backtest.py` | `GET /api/backtest`, `GET /api/backtest/{strategy}` |
| Portfolio | `routes/portfolio.py` | `GET /api/portfolio/positions`, `GET /api/portfolio/balance`, `GET /api/portfolio/nav`, `GET /api/portfolio/trades`, `GET /api/portfolio/summary`, `GET /api/portfolio/orders`, `POST /api/portfolio/order`, `POST /api/portfolio/refresh` |
| Sectors | `routes/sectors.py` | `GET /api/sectors/overview`, `GET /api/sectors/exposure`, `GET /api/sectors/{industry}`, `GET /api/sectors/{industry}/stocks` (410 retired) |
| Pipeline | `routes/pipeline.py` | `GET /api/pipeline`, `GET /api/pipeline/market-regime`, `GET /api/pipeline/{pipeline_key}` |
| Assets | `routes/assets.py` | `GET /api/assets/overview` |
| Data Sources | `routes/data_sources.py` | `GET /api/data-sources/capabilities` |
| Settings | `routes/settings.py` | `GET /api/settings`, `GET /api/settings/schema`, `PUT /api/settings`, `PATCH /api/settings/section/{section}` |
| System | `routes/system.py` | `GET/PATCH /api/system/llm-runtime`, `GET /api/system/db-health`, `POST /api/system/db-health/repair/{table_name}`, `GET /api/system/db-health/repair-status/{job_id}`, `GET /api/system/api-health`, `GET /api/system/auth`, `GET /api/system/cron-jobs`, `GET /api/system/quality-gate`, `GET /api/system/runs`, `GET /api/system/runs/{run_id}`, `GET /api/system/orders`, `GET /api/system/orders/{order_id}/trace`, `GET /api/system/backfill`, `GET /api/system/backfill/{dimension}/last`, `GET /api/system/providers/health`, `GET /api/system/contracts`, `GET /api/system/audit`, `GET /api/system/tests/design`, `GET /api/system/ast-intelligence` |
| CodeGraph | `routes/codegraph.py` | `GET /api/codegraph/status`, `GET /api/codegraph/graph`, `GET /api/codegraph/search`, `GET /api/codegraph/neighborhood`, `GET /api/codegraph/diagnostics`, `POST /api/codegraph/sync` |
| Agent Company OS | `routes/agent.py` | `GET /api/agent/sessions`, `POST /api/agent/sessions`, `GET /api/agent/sessions/{session_id}`, `PATCH /api/agent/sessions/{session_id}`, `GET /api/agent/sessions/{session_id}/context`, `POST /api/agent/sessions/{session_id}/context/compact`, `GET /api/agent/model-runtime`, `POST /api/agent/sessions/{session_id}/messages`, `GET /api/agent/actions`, `GET /api/agent/handoffs`, `POST /api/agent/handoffs/{handoff_id}/resolve`, `GET /api/agent/actions/{action_id}`, `POST /api/agent/actions/{action_id}/approve`, `POST /api/agent/actions/{action_id}/reject`, `POST /api/agent/actions/{action_id}/cancel`, `POST /api/agent/actions/expire`, `POST /api/agent/actions/{action_id}/run`, `GET /api/agent/runs/{run_id}`, `GET /api/agent/evidence/{evidence_id}`, `GET /api/agent/desks`, `GET /api/agent/live/readiness`, `GET /api/agent/reports`, `POST /api/agent/reports`, `GET /api/agent/memory`, `POST /api/agent/memory/export`, `POST /api/agent/memory/prune`, `POST /api/agent/memory/clear` |
| Auth | `auth.py` | Bearer token 中间件 + CORS/OPTIONS 放行 |

**Agent Company OS API:**

| 模块 | 文件 | 端点 |
|------|----------|----------|
| Agent Company OS | `routes/agent.py` | `GET /api/agent/sessions`, `POST /api/agent/sessions`, `GET /api/agent/sessions/{session_id}`, `PATCH /api/agent/sessions/{session_id}`, `GET /api/agent/sessions/{session_id}/stream`, `GET /api/agent/sessions/{session_id}/context`, `POST /api/agent/sessions/{session_id}/context/compact`, `GET /api/agent/model-runtime`, `POST /api/agent/sessions/{session_id}/messages`, `POST /api/agent/plans`, `GET /api/agent/actions`, `GET /api/agent/handoffs`, `POST /api/agent/handoffs/{handoff_id}/resolve`, `GET /api/agent/work-orders`, `POST /api/agent/work-orders`, `PATCH /api/agent/work-orders/{work_order_id}`, `GET /api/agent/actions/{action_id}`, `POST /api/agent/actions/{action_id}/approve`, `POST /api/agent/actions/{action_id}/reject`, `POST /api/agent/actions/{action_id}/cancel`, `POST /api/agent/actions/expire`, `POST /api/agent/actions/{action_id}/run`, `GET /api/agent/runs/{run_id}`, `GET /api/agent/runs/{run_id}/stream`, `GET /api/agent/evidence/{evidence_id}`, `GET /api/agent/desks`, `GET /api/agent/policies`, `POST /api/agent/paper/proposals`, `POST /api/agent/paper/actions/{action_id}/submit`, `POST /api/agent/paper/actions/{action_id}/cancel`, `GET /api/agent/live/readiness`, `GET /api/agent/live/environment`, `POST /api/agent/live/smoke`, `POST /api/agent/live/preview`, `POST /api/agent/live/proposals`, `POST /api/agent/live/actions/{action_id}/submit`, `POST /api/agent/live/reconciliation`, `POST /api/agent/live/monitor`, `GET/POST /api/agent/live/kill-switch(/activate,/deactivate)`, `GET /api/agent/reports`, `POST /api/agent/reports`, `POST /api/agent/reports/{report_id}/notify`, `POST /api/agent/reports/rhythm`, `POST /api/agent/reports/rhythm/scheduled`, `GET /api/agent/memory`, `POST /api/agent/memory/export`, `POST /api/agent/memory/prune`, `POST /api/agent/memory/clear` |

这些端点当前覆盖 Agent Company OS 的本地 runtime、CEO Office 基础页面、handoff/work-order、报告节奏、paper execution、MiniQMT/QMT live readiness/environment/smoke/preview/proposal/approval-gated submit/reconciliation/monitor/kill-switch 和透明 memory：本地 ledger、会话 metadata 更新、审批状态、action expiry、证据解析、desk registry、provider-backed desk response、固定 registry 命令的安全/已批准 dispatch、跨 desk handoff ledger、handoff resolve、transparent memory inspect/export/prune/clear、evidence-cited CEO reports、默认首页、会话消息写入、LLM-first 部门分诊、最外层 Web 底部状态栏里的本机全局 LLM provider/model/推理程度和当前 session CTX telemetry，以及消息内 action/evidence card、内联审批决策、run history 和 evidence 深链。Advanced open-ended execution 和更高阶实时协作仍按 [07-agent-company-os.md](07-agent-company-os.md) 的边界实现；实现前不得在 Web 端调用假端点或展示伪成功。

LLM 成本与 provider 能力配置以 `llm.providers.{provider}` 为边界，`llm.use_cases.*` 只声明默认调用形状。OpenAI-compatible provider 必须声明 `protocol: openai_compatible`、`api_key_env`、`base_url`、`default_model`，可通过 `request.*` 声明默认请求参数，并可通过 `reasoning_modes` 声明 provider-specific 推理档位。`GET/PATCH /api/system/llm-runtime` 管理本机全局 provider/model/reasoning profile，写入 `var/db/llm_runtime.sqlite`，不修改 `config/settings.yaml`；该 profile 覆盖 `agent_routing`、`agent_tool_planning`、`agent_response`、`agent_planning` 和 `factor_hypothesis` 的 provider/model/reasoning，同时保留各 use case 的 timeout、temperature、JSON 输出等调用形状。未知 provider、禁用 provider、缺 secret、缺 base_url、缺 model 或 unsupported protocol 必须 fail-closed；缺 pricing 不阻断调用，但 usage/cost 汇总必须标记为 partial/unpriced，不得借用其他 provider 的价格。

Agent provider planning must use the Agent Context Compression contract before sending session context to a model. The CEO Office reads `GET /api/agent/model-runtime` for compact CTX telemetry, while manual context inspection/compaction remains CLI/API only. Context pack creation never deletes raw session messages; it writes runtime artifacts under `var/artifacts/agent/context/` when compaction is explicitly requested or needed before provider planning.

**Pipeline API 契约：**

`GET /api/pipeline` 返回可用 pipeline 列表。`GET /api/pipeline/{pipeline_key}` 返回稳定 JSON：

- `pipeline_key`: `market_regime` / `data_quality` / `strategy_evidence` / `portfolio_execution`
- `updated`
- `summary`: confirmed/raw regime、score、engine、detection_method、confidence、entropy、adaptive_params
- `nodes`: 细粒度节点数组；Market Regime 节点来自 `web/api/services/pipelines/market_regime_nodes.py`
- `edges`: 节点连线数组，source/target 必须引用有效 node id；边可携带 `label` / `condition` / `active`
- `warnings`: HMM 模型缺失、fallback、样本不足等提示

服务端复用 `QuantOrchestrator().detect()` 输出的 `score_components`、`breadth_detail`、`regime_probs`、`detection_method` 和 HMM `meta.json`，不得在 API 层重写 Market Regime 计算公式。

**WebSocket：** `routes/strategies.py` 暴露 `/api/strategies/ws/{job_id}` 并委托 `web/api/ws.py:ws_endpoint()`。连接后按 `job_id` 校验任务存在性；服务端每秒读取 `web/api/jobs.py` 中的 `_jobs` 状态并发送 `{job_id,status,progress,message}`，收到文本 `ping` 时返回 `pong`。

**任务队列：** `jobs.py` 提供 `create_job()` / `run_job()` / `run_strategy_async()`，用后台线程执行策略扫描，并通过 `progress_callback` 更新 job 状态；WebSocket 只读取并转发该状态，不跨 event loop 直接广播。

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

`astroq` 是 Web/API 之外的本地控制平面，用于 agent、cron 和人工维护。CLI 只做编排：策略扫描仍走 `data.strategy.plugins`，数据修复仍走 `scripts.repair_table`，Web 服务仍走 `uvicorn web.api.app:create_app`。所有 agent 依赖命令必须支持 `--json`。

| 命令域 | 命令 | 契约 |
|--------|------|------|
| Health | `astroq health --json` | 返回项目版本、DataHub store/cache 路径 |
| Config | `astroq config validate --json` | 校验 settings 和策略注册表 |
| Data | `astroq data status --json` / `astroq data repair <table> --dry-run --json` | 委托 DB health 和单表修复，dry-run 不触发写入 |
| Data Sources | `astroq data sources --json` / `astroq data sources audit --source all --discovery-depth full-sample --resume --json` / `astroq data sources diff-registry --json` | 生成和读取外部 source capability registry，并与项目 `data_registry` 做 diff；Web 只读消费 artifact，区分 discovered / sample_probed / contracted / project_integrated，并展示探测成功、阻断原因、无权限、限流和错误状态 |
| Strategy | `astroq strategy catalog --json` / `astroq strategy run <name|all>` | 委托 Strategy Catalog 和 runtime gates，candidate 必须显式 `--mode research` |
| Regime | `astroq regime status --json` / `astroq regime train-profit --dry-run --json` | 读取当前生产 regime；训练命令默认可 dry-run |
| Backtest | `astroq backtest run [--strategy NAME] --dry-run --json` | 委托回测 runner，不在 CLI 重写回测逻辑 |
| Docs | `astroq docs check --json` | 扫描已知陈旧文档短语 |
| Tests | `astroq test check --suite quick --json` / `astroq test design --json` | `test check` 运行固定测试 suite；`test design` 生成 `var/artifacts/tests/design/latest.json`，Web 只读展示测试设计图谱、风险矩阵和异味诊断 |
| Architecture | `astroq architecture ast --json` | 生成 `var/artifacts/architecture/ast/latest.json`，Web 只读展示 Python/TS/Vue/CSS 的重复实现、近似 clone、重复 helper 和 canonical helper 绕行风险 |
| Lifecycle | `astroq lifecycle check --json` | 生成 `var/artifacts/lifecycle/latest.json`；Web 只读展示 source capability、local freshness、strategy evidence 和 execution readiness，缺数据/缺能力/缺证据必须显示 blocked/not_applicable |
| Web | `astroq web build --json` / `astroq web serve --host HOST --port PORT` | 委托 Vite build 和 FastAPI/uvicorn |

## 3. 数据流

```
Browser (Vue 3)
    │  HTTP GET /api/strategies/buffett
    ▼
FastAPI Route Handler
    │  data.storage.results_db.load_strategy_signals(name)
    ▼
DataHub → load_strategy_signals("buffett")
    │  DataFrame
    ▼
Pydantic Model Serialization → JSON Response
    │
    ▼
Pinia Store → Vue Component → ECharts 渲染
```

**WebSocket 流：**
```
POST /api/strategies/run
    │ 创建 Job
    ▼
create_job() → run_job() 后台线程执行策略扫描
    │ progress_callback 更新 _jobs[job_id]
    ▼
ws_endpoint() 每秒读取 job 状态
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
| 长任务处理 | WebSocket 推送进度 | 策略扫描等异步任务可能跑一段时间，HTTP 轮询太低效 |
| 状态管理 | Pinia (per-page stores) | 页面间独立，不需要全局状态 |
| 配置管理 | YAML + schema 校验 | settings.yaml 人类可读写 + API 层字段/范围校验 |

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
  "job_id": "uuid",
  "status": "running",
  "progress": 60,
  "message": "LightGBM ML done"
}
```

### Settings API 安全校验

```python
# Config Center schema
GET /api/settings/schema

# Dotted section patch keeps canonical nested YAML:
PATCH /api/settings/section/ingestion.fetcher

# 必须段校验
REQUIRED_SECTIONS = {"strategies", "risk_control"}
```

`/system?tab=settings` 是只读系统设置摘要页，不提供整页保存、会话认证输入、通知开关或审计记录管理。`/system?tab=config` 是只读 schema 化配置查看页，帮助用户理解当前参数结构和取值；配置修改由 agent/CLI/API 执行，不在 Web 系统控制页提供手动写入控件。

`GET /api/settings/schema` 返回 `groups` + `sections`：左侧一级域包括策略管理、市场状态、执行与风控、数据与清洗、研究回测、AI 服务；每个 section 带 `group`、`subgroup`、`subgroup_label` 和字段元数据。Config Center 只切一级域，右侧把二级分组纵向展开，不把策略参数平铺成同级 tab，也不展示保存/重置/输入控件。

`PATCH /api/settings/section/{section}` 支持 dotted section，例如 `ingestion.fetcher`、`buffett.margin_of_safety`、`strategies.buffett`、`signal_selection.strategies.multifactor`。服务端必须写回嵌套 YAML，不允许生成顶层 `ingestion.fetcher:` 这类重复 key。

## 6. 错误处理

- **404：** 资源不存在 → `{"error": "Stock not found: 999999", "timestamp": "..."}`
- **422：** Pydantic 校验失败 → FastAPI 自动返回字段级错误
- **500：** 未捕获异常 → `errors.py` 全局处理器统一格式化
- **WebSocket 断连：** 前端显示进度连接失败并停止当前运行态；后续可补指数退避重连
- **Settings 更新非法：** 更新端点校验认证、schema 字段类型和范围，非法配置返回 4xx/422

## 7. 测试策略

- **合约测试：** 所有路由返回正确的 HTTP 状态码和 JSON schema
- **集成测试：** `GET /api/strategies/{name}` 返回实际策略信号（需本地有信号文件）
- **WebSocket 测试：** 创建 Job → 验证进度消息格式
- **Settings 测试：** 非法配置更新返回 422，dotted section PATCH 不生成顶层重复 key，配置中心 schema 字段必须存在于 canonical settings，并保持 group/subgroup 二级只读配置模型
- **边界测试：** 空 Parquet 文件返回空列表，分页越界返回空数组

## 8. 已知限制 & 未来方向

- **行业/板块雷达页面** — 已合入 `/research?tab=sectors`，展示申万行业动量排名和策略信号分布；组合行业敞口归属 `/portfolio`，避免研究页重复持仓归因。
- **无移动端适配** — 当前仅桌面浏览器布局
- **DuckDB 只读** — 所有写操作通过 API 触发 Python 端 DataHub，不经过 DuckDB
- **Pipeline v2：** Pipeline 页面已覆盖 Market Regime、Data Quality、Strategy Evidence、Portfolio/Execution 四条关键链路；后续扩展应继续复用统一 `nodes` / `edges` / `summary` 契约。
- **Web API 契约：** Web API 的稳定契约以 Pydantic `response_model` 和前端 TypeScript 类型共同约束；新关键端点必须同时补齐后端模型、前端类型和合约测试。
- **未来：** 策略参数热调、回测结果交互式下钻、前端 smoke/e2e 自动化继续扩大到视觉回归。
