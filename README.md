<div align="center">
  <h1>星盘</h1>
  <h3>Astrolabe Quant OS — 个人量化研究与执行操作系统</h3>
  <p>
    <img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python">
    <img src="https://img.shields.io/badge/version-2.0.0-orange" alt="Version">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/A%20Share-universe-cyan" alt="A Share">
    <img src="https://img.shields.io/badge/local--first-Parquet%20%2B%20DuckDB-0f766e" alt="Local first">
  </p>
</div>

---

星盘是一个本地运行的日频量化研究系统，集成了数据、策略、回测、模拟执行、配置和诊断功能。

系统提供两种使用方式：

- **Web UI**：查看市场状态、策略证据、流程图、数据健康、组合执行和系统诊断。
- **CLI**：通过 `astroq` 命令以 JSON 格式执行数据检查、补数、回测、诊断等操作。

## Web UI

### 市场总览
显示当前市场状态，包括 market regime、核心指数、行业脉冲和宏观快照。

![市场总览](docs/assets/readme/screenshots/01-market-overview.png)

### 策略实验室
按 production / paper / candidate 分层展示策略。

![策略实验室](docs/assets/readme/screenshots/02-strategy-lab.png)

### Pipeline 流程图
展示关键参数、阈值、权重和分支判断，说明每个结论的形成过程。

![Pipeline 流程图](docs/assets/readme/screenshots/03-pipeline.png)

### 数据中台
查看本地数据维度、健康状态、存储大小，支持单表修复。

![数据中台](docs/assets/readme/screenshots/04-datahub.png)

### 系统控制
配置中心、生命周期门禁、测试设计、AST 检测、CodeGraph 和架构诊断。

![系统控制](docs/assets/readme/screenshots/05-system-control.png)

### 组合执行
PaperBroker 的持仓、NAV、订单和交易账本。

![组合执行](docs/assets/readme/screenshots/06-portfolio.png)

## 策略分层

| 层级 | 策略 | 说明 |
|------|------|------|
| 质量过滤 | Buffett | 能力圈、护城河、安全边际，过滤财务质量和估值风险 |
| 主 Alpha | Multifactor | 质量、估值、技术、市场、行业动量五维打分 |
| 辅助 Alpha | LightGBM | 使用 PIT 特征捕捉非线性关系，默认 paper 状态 |
| 风险覆盖 | Cybernetic | market regime、仓位、止损、风险预算和资产配置 |
| 研究候选 | Candidate | 趋势、Donchian、RPS、行业轮动、质量价值、低波防御等 |

## 配置

参数集中在 [config/settings.yaml](config/settings.yaml)，Web 配置中心提供可视化编辑，CLI 提供校验命令。

| 配置域 | 内容 |
|--------|------|
| `signals.multifactor.weights` | 多因子五维权重 |
| `signal_selection` | Top-N、最低分、每策略买入上限 |
| `buffett` | 能力圈、护城河、安全边际、DCF 和评分参数 |
| `cybernetics` | regime 阈值、指数权重、广度权重、HMM 和稳定确认 |
| `risk_control` | 单票仓位、总敞口、下单次数、回撤熔断、单笔金额 |
| `asset_allocation` | bull / sideways / bear 下的资产权重 |

## 系统架构

```mermaid
flowchart LR
  subgraph Data["数据层"]
    Sources["AKShare / Tushare / 本地缓存"]
    Registry["DataRegistry\n维度声明 / SLA / 修复策略"]
    Hub["DataHub\nParquet / manifest / 原子写入"]
    Features["Feature Store\nPIT 特征切片"]
  end

  subgraph Research["研究与信号"]
    Factor["Factor DSL\n表达式 / IC / ICIR"]
    Catalog["Strategy Catalog\nproduction / paper / candidate"]
    Signals["Signal Runtime\n统一信号契约"]
    Evidence["Research Evidence\nOOS / 回测 / 晋级门槛"]
  end

  subgraph Execution["执行与风控"]
    Regime["Cybernetic Regime\n规则评分 + HMM + 稳定确认"]
    Risk["RiskManager\n仓位 / 敞口 / 熔断"]
    Broker["PaperBroker\n撮合 / ledger / NAV"]
  end

  subgraph Control["控制面"]
    CLI["astroq CLI\nagent / cron / JSON"]
    API["FastAPI\nREST / WebSocket"]
    UI["Vue 3 Web UI\n图表 / 流程图 / 双语"]
  end

  Sources --> Registry --> Hub --> Features
  Features --> Factor --> Signals
  Catalog --> Signals --> Evidence
  Hub --> Regime --> Risk --> Broker
  Signals --> Risk
  CLI --> Registry
  CLI --> Catalog
  CLI --> Evidence
  API --> Hub
  API --> Broker
  API --> Evidence
  UI --> API
```

## Web 路由

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | 市场总览 | market regime、核心指标、行业脉冲、宏观快照 |
| `/research` | 市场研究 | 行业雷达、个股搜索、个股详情 |
| `/strategy-lab` | 策略实验室 | 策略目录、生产隔离、研究扫描、回测证据 |
| `/portfolio` | 组合执行 | PaperBroker 持仓、NAV、交易记录、手动下单 |
| `/pipeline` | 流程图 | 关键链路拆解、参数解释、节点详情、流向高亮 |
| `/datahub` | 数据中台 | 维度状态、数据健康、存储统计、单表修复 |
| `/system` | 系统控制 | 系统信息、配置中心、生命周期门禁、测试设计、AST 检测、CodeGraph、架构诊断 |

前端支持中文 / English 切换，入口在左侧导航栏底部。

## CLI

项目安装后可执行 `astroq`，或通过 `python -m astrolabe_cli.main ...` 运行。常用命令示例：

```bash
astroq health --json          # 项目健康检查
astroq data status --json     # 数据健康扫描
astroq strategy catalog --json  # 策略目录
astroq backtest check --json  # 回测质量检查
```

完整命令清单见 [AGENTS.md](AGENTS.md)。

## 快速开始

### 1. 环境准备

需要 Python 3.11+、Node.js 18+、Git。

```bash
git clone https://github.com/RainbowLion0320/astrolabe-quant.git
cd astrolabe-quant

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

可选依赖：

```bash
# ML 训练和调参
python -m pip install -e ".[ml]"

# 本地开发测试
python -m pip install -r requirements-dev.txt
```

### 2. 配置密钥

基础功能无需密钥。完整数据和 AI 因子研究需要配置以下环境变量，不要写入 `config/settings.yaml` 或 `.env` 文件。

| 环境变量 | 用途 |
|----------|------|
| `TUSHARE_TOKEN` | Tushare 数据（估值、资金流、财务扩展等） |
| `DEEPSEEK_API_KEY` | DeepSeek LLM 因子发现和用量监控 |
| `ASTROLABE_API_KEY` | FastAPI Bearer Token 认证 |
| `ASTROLABE_VAR` | 覆盖默认运行产物目录 `var/` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram 通知推送，参考 [config/notify.example.yaml](config/notify.example.yaml) |
| `WECHAT_WEBHOOK_URL`, `FEISHU_WEBHOOK_URL` | 企业微信 / 飞书通知 webhook |

真实通知配置放在 `config/notify.yaml`（已被 `.gitignore` 忽略）。

检查环境变量状态：

```bash
astroq config env --json
```

### 3. 启动 Web

开发模式建议开两个终端。

终端 A — FastAPI 后端：

```bash
source .venv/bin/activate
uvicorn web.api.app:create_app --factory --host 0.0.0.0 --port 8501 --reload
```

终端 B — Vite 前端：

```bash
cd web/frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

生产模式先构建前端，再由后端挂载静态资源：

```bash
cd web/frontend
npm run build
cd ../..
astroq web serve --host 0.0.0.0 --port 8501
```

## 文件与数据

| 路径 | 提交到 Git | 说明 |
|------|------------|------|
| `config/settings.yaml` | 是 | 参数、权重、风控、资产和策略注册表 |
| `config/notify.example.yaml` | 是 | 通知配置模板 |
| `config/notify.yaml` | 否 | 本地真实通知密钥 |
| `data/` | 是 | 数据层源码包 |
| `data/reference/` | 是 | 静态参考数据和 seed 模型（如 HMM 初始参数） |
| `var/store/` | 否 | 行情、信号、特征、paper 状态等运行产物 |
| `var/cache/` | 否 | API 缓存 |
| `var/artifacts/` | 否 | 回测、模型、锦标赛、诊断产物 |
| `var/db/` | 否 | DuckDB/SQLite 运行数据库 |
| `reports/` | 否 | 训练、regime、回测和诊断报告 |
| `docs/specs/` | 是 | 模块行为契约 |
| `wiki/` | 是 | 概念说明、架构决策和操作参考 |

## 项目结构

```text
astrolabe-quant/
├── astrolabe_cli/          # CLI 控制面
├── backtest/               # 日频回测、风险指标、策略锦标赛
├── broker/                 # PaperBroker、风控、撮合、ledger、NAV
├── config/                 # settings.yaml、workflow、通知模板
├── cybernetics/            # market regime、HMM、稳定确认、风险预算
├── data/                   # 数据层源码包
│   ├── storage/            # DataHub、manifest、DuckDB、DataRegistry
│   ├── ingestion/          # provider、fetcher、Tushare 工具
│   ├── market/             # 价格服务、复权、行业、资产和市场视图
│   ├── features/           # PIT Feature Store、factor scoreboard
│   ├── quality/            # cleaner、contract、quality gate、freshness gate
│   ├── ops/                # audit、backfill、cron logger
│   ├── llm/                # LLM provider usage ledger
│   ├── rates/              # 无风险利率 provider
│   ├── strategy/           # Strategy Catalog 和插件注册
│   └── reference/          # 静态参考数据和 seed 模型
├── docs/                   # PRD、技术规格、验收矩阵、文档治理
├── models/                 # 模型注册与加载
├── pipeline/               # alpha/risk/portfolio/execution 流水线
├── research/               # 策略治理、OOS 证据、regime 训练
├── scripts/                # cron、数据拉取、训练、修复、报告脚本
├── signals/                # 生产策略、候选策略、DSL、信号选择
├── tests/                  # 合约测试、边界测试、Web/API/CLI 测试
├── web/
│   ├── api/                # FastAPI REST、WebSocket、jobs
│   └── frontend/           # Vue 3 + Vite + ECharts
├── var/                    # 本地运行产物（不提交）
│   ├── store/              # DataHub 主存储
│   ├── cache/              # API、回测缓存
│   ├── artifacts/          # 回测、模型、锦标赛、诊断产物
│   └── db/                 # DuckDB/SQLite
└── wiki/                   # 概念、参考、架构决策
```

## 文档导航

| 文档 | 面向 | 内容 |
|------|------|------|
| [产品范围](docs/PRD.md) | 新用户 | 项目做什么、不做什么 |
| [技术规格](docs/specs/) | 开发者 | 数据、信号、回测、执行、Web、多资产契约 |
| [验收矩阵](docs/acceptance-matrix.md) | 维护者 | 需求、代码、测试、文档追踪 |
| [文档治理](docs/DOCUMENTATION.md) | 维护者 | README、spec、wiki、代码的权威边界 |
| [策略文档](docs/strategies/) | 策略研究者 | 生产策略、候选策略、研究晋级规则 |
| [Wiki](wiki/index.md) | 深入阅读 | 概念、架构决策、数据维度、CLI 控制面 |

## 开发检查

文档或代码改动后至少运行：

```bash
git diff --check
astroq docs check --json
astroq test design --json
astroq architecture ast --json
astroq test check --suite quick --json
```

按风险选择测试范围：

```bash
python -m pytest tests/ -q
python -m pytest tests/test_frontend_i18n_contracts.py -q
cd web/frontend && npm run typecheck && npm run build
```

## 声明

星盘用于个人研究和学习，不构成投资建议，不保证收益。

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
