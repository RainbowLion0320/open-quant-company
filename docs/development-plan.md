# Quant Agent 开发计划

> 日期: 2026-05-22  
> 来源: Codex 架构审查  
> 目的: 记录下一轮系统级优化任务，供后续 agent 拆分执行。当前完成状态以 git、测试、运行产物为准，本文件只记录计划和验收口径。

## 总体判断

项目已经具备数据中台、策略注册、PIT 特征、回测、PaperBroker、Web UI 和 PRD/spec 文档骨架。下一阶段的重点不应只是继续堆策略或页面，而是把系统升级为可追踪、可复现、可验收的研究与交易平台。

核心方向:
- 统一环境、依赖、版本和 CI，减少 agent 重复踩坑。
- 建立 PRD/spec 到代码和测试的追踪矩阵。
- 把每次特征构建、模型训练、锦标赛、paper trading 记录为同一个可查询 run。
- 强化 PIT 和 lookahead bias 自动检测，让前视偏差从“约定”变成“门禁”。
- 重构策略到组合和执行的边界，逐步靠近成熟量化框架的职责分离。

## P0: 工程底座收敛

### 1. 统一依赖、版本和开发入口

现状:
- `README.md` 写了 `pip install -r requirements.txt`，但仓库没有 `requirements.txt`。
- `pyproject.toml` 的版本与 `config/settings.yaml`、前端 `package.json`、README 展示版本不一致。
- GitHub Actions 直接手写 `pip install akshare pandas ...`，容易和本地环境漂移。
- 当前 shell 下 `pytest` 不可用，需使用 `/Users/fushao/.hermes/hermes-agent/venv/bin/python3 -m pytest`。

建议:
- 以 `pyproject.toml` 作为 Python 依赖和工具配置单源。
- 补齐 optional dependency groups: `dev`, `web`, `ml`, `data`。
- 统一项目版本来源，README、API、前端、settings 不再各写一份。
- Makefile 增加 `test`, `lint`, `typecheck`, `web-build`, `ci`。
- GitHub Actions 改为从项目依赖安装，不再维护手写包列表。

验收:
- `python -m pytest -q` 可直接运行。
- `npm run build` 通过。
- `make ci` 一次跑完后端测试和前端构建。
- README 的安装命令在干净环境中可执行。

### 2. 建立 PRD/spec 验收矩阵

现状:
- `docs/PRD.md` 和 `docs/specs/*.md` 已补全，但还没有“需求 -> 代码 -> 测试 -> 页面/API”的追踪关系。
- spec 中的部分承诺尚未被测试或 API 合约强制保障。

建议:
- 新增 `docs/acceptance-matrix.md`。
- 每条核心能力记录:
  - PRD/spec 条目
  - 相关代码文件
  - 相关 API 或 Web 页面
  - 测试文件
  - 手工验收命令
  - 当前状态和缺口

验收:
- 至少覆盖数据管道、信号系统、回测、执行层、Web、多资产六个能力域。
- 每个 P0/P1 能力至少绑定一个自动化测试或明确标注“待补测试”。

### 3. API 合约统一

现状:
- Web spec 约定统一 `{"data": ..., "error": ...}` 响应，但实际路由存在裸对象、`{"error": ...}`、异常处理器混用。
- 前端 API client 直接消费各路由真实结构，缺少统一错误模型。

建议:
- 要么正式采用 envelope 响应，要么修订 spec，明确不同端点的响应模型。
- 为 FastAPI 增加 OpenAPI snapshot 或 contract tests。
- 后端错误统一使用 `web/api/errors.py`，避免路由直接返回 `{"error": ...}`。

验收:
- `web/api/routes/*` 不再混用互相矛盾的错误格式。
- 核心端点有 `response_model` 或 contract test。
- 前端 API client 的类型定义与后端测试保持一致。

## P0: 可信研究闭环

### 4. ResearchRun / ExperimentRegistry

现状:
- DataHub manifest 已记录单个 Parquet 写入的 schema、hash、producer。
- workflow 只是顺序执行脚本，未把特征、模型、回测、锦标赛、配置和 git commit 串成同一个可追踪 run。

建议:
- 新增实验注册表，例如 `data/experiment_registry.py` 或 `research/runs.py`。
- 每次 workflow 生成 `run_id`，记录:
  - git commit
  - config hash
  - DataHub manifest snapshot/hash
  - feature months and schema hash
  - model name/version/params
  - tournament/backtest metrics
  - artifacts paths
  - status: scheduled/running/finished/failed
- `scripts/run_workflow.py`, `scripts/tune_model.py`, `scripts/strategy_tournament.py` 写入同一 run。

验收:
- 任意模型或回测结果都能反查到当时的代码、配置、数据和参数。
- Web 或 CLI 可列出最近 runs。
- 失败 run 有错误信息和已完成步骤记录。

成熟项目参照:
- Qlib `qrun` 把 Data、Model、Evaluation 串成一次 execution，并记录训练、预测、评估产物。
- MLflow Tracking 以 run/experiment 记录参数、指标、代码版本和产物。

### 5. PIT 数据视图和 lookahead bias 扫描器

现状:
- 项目强调 PIT 零前视，但很多地方仍靠调用方自行截断数据。
- `get_stock_daily()` 默认返回完整本地历史，调用方若忘记 as-of 约束，容易重新引入前视偏差。

建议:
- 引入统一 `MarketDataView(as_of=...)` 或在 DataHub/fetcher 层提供强制 as-of read API。
- 回测、训练、因子检验只允许通过 as-of 数据视图读取历史。
- 新增 `scripts/lookahead_check.py`，对策略运行基线和切片运行结果做差异检测。

验收:
- 回测入口无法无意读取 `date > current_dt` 的数据。
- 构造未来暴涨样本时，策略不会提前买入。
- lookahead check 可在 CI 或 `make ci` 中以小样本运行。

成熟项目参照:
- Freqtrade 提供 lookahead-analysis 专项命令，通过多轮回测检测指标和进出场是否受未来数据影响。

## P1: 架构边界升级

### 6. 策略流水线职责分离

现状:
- 当前策略计算、regime、选股、信号、部分组合意图混在一起。
- 回测、日频扫描和 paper trading 已有注册表，但还没有统一的 `PortfolioTarget` 中间层。

建议:
- 引入标准流水线:
  - Universe Selection: 股票池/资产池
  - Alpha/Signal: 只产方向、置信度、期限、原因
  - Portfolio Construction: alpha -> target weights
  - Risk Management: target weights -> risk-adjusted targets
  - Execution: targets -> orders/fills
- 增加 `PortfolioTarget` dataclass，并让回测、paper trading、未来实盘共用。

验收:
- 策略不直接下单，也不直接决定最终成交。
- 同一策略输出可被不同组合构建模型复用。
- 回测和 PaperBroker 使用同一 target/order/fill 数据结构。

成熟项目参照:
- QuantConnect LEAN Algorithm Framework 使用 Universe、Alpha、Portfolio Construction、Risk、Execution 的职责分离。

### 7. 执行层订单状态机和成交模型

现状:
- PaperBroker 支持 T+1、基础风控和立即成交。
- 仍缺少部分成交、涨跌停/停牌/ST、成交失败、冲击成本、对账和审计账本。

建议:
- 事件账本表达 `SignalSet -> TargetPortfolio -> Orders -> Fills -> Positions -> NAV`。
- 把 commission/slippage/fill model 从 broker 中抽出为可插拔模型。
- MiniQMT 之前先完成 paper/live 统一订单生命周期。

验收:
- 每笔 NAV 变化能追溯到 fill。
- 支持 rejected/partial_filled/cancelled/expired 状态。
- 回测和 paper trading 的成本模型来自同一配置。

成熟项目参照:
- Backtrader 对 commission、slippage、broker 和 analyzer 有成熟抽象。

## P1: 数据中台扩展

### 8. ProviderAdapter 和 DataContract

现状:
- DataRegistry 作为维度注册表已经有雏形。
- fetcher/provider 还不是真正插件化，schema version、迁移、补数账本不足。

建议:
- 引入:
  - `ProviderAdapter`: AKShare/Tushare/Wind/Choice/OpenBB 等数据源统一接口。
  - `DataContract`: 每个维度声明 schema、主键、频率、SLA、owner、PIT 规则。
  - `BackfillLedger`: 记录补数范围、状态、错误、重试。
  - `SchemaMigration`: schema 变化时记录版本和兼容策略。

验收:
- 新增数据源不修改核心 DataHub 读写逻辑。
- DB Health 可区分 missing/stale/schema_mismatch/provider_error。
- 每次补数有可查询账本。

成熟项目参照:
- OpenBB 的 provider extension 允许数据源独立安装、移除和暴露能力覆盖。

### 9. 数据质量门禁

建议:
- 对 OHLCV、财务、估值、资金流、宏观分别定义质量规则。
- 增加数据快照健康分和 freshness gate。
- 策略生产扫描前检查依赖数据是否 fresh，不满足则降级或拒绝运行。

验收:
- 日频扫描报告包含数据依赖状态。
- 关键数据 stale 时不会静默产出强信号。

## P1: Web 和运维

### 10. Web 性能和可维护性

现状:
- `npm run build` 通过，但存在大 chunk 警告，最大 chunk 约 1 MB。

建议:
- 对 HindsightGraph、ECharts、Three 相关模块做 route-level dynamic import 和 manualChunks。
- 加前端 smoke/e2e 测试，至少覆盖市场总览、DB Health、策略中心、组合页。

验收:
- build 无大 chunk 警告，或明确设置合理阈值并解释。
- 核心页面可由自动化浏览器打开并无 console error。

### 11. 系统设置安全边界

现状:
- Settings API 可直接写 `config/settings.yaml`。
- 本地单用户阶段可接受，但实盘前风险较高。

建议:
- 增加只读模式和 API key/JWT。
- 对敏感配置变更增加审计日志和二次确认。
- 实盘前区分 research、paper、live 三个运行模式。

验收:
- 未认证请求不能修改设置。
- 配置修改有 diff、时间、操作者、来源记录。

## P2: 策略和资产能力

### 12. 策略晋级制度

建议:
- 每个策略必须有:
  - 策略卡片
  - 依赖数据清单
  - 参数空间
  - OOS 结果
  - 交易成本敏感性
  - 最大回撤和失效场景
- LLM 自动发现因子只能进入候选池，不能直接进入生产。

验收:
- 新策略 PR 不满足策略卡片和测试不得启用。

### 13. 多资产从真实数据契约开始

建议:
- ETF、债券、期货、黄金等扩展必须先完成数据契约和回测口径。
- ETF proxy 可以保留为实验模式，但生产策略应标记为 proxy/not_real。
- 增加 FX/currency、交易日历、合约乘数、期货换月、ETF 折溢价等资产元数据。

验收:
- Web 和回测能明确区分真实行情、proxy、缺失数据。

## 执行顺序建议

1. P0-1 统一依赖、版本、CI、Makefile。
2. P0-2 建立 `docs/acceptance-matrix.md`。
3. P0-3 统一 Web API 合约。
4. P0-4 实现 ResearchRun / ExperimentRegistry。
5. P0-5 实现 PIT 数据视图和 lookahead check。
6. P1-6 引入 PortfolioTarget 流水线。
7. P1-7 执行层订单状态机和事件账本。
8. P1-8 ProviderAdapter / DataContract / BackfillLedger。
9. P1-10 前端拆包和 smoke/e2e。
10. P2 策略晋级制度和多资产真实化。

## 参考项目

- QuantConnect LEAN: Algorithm Framework 的 Universe/Alpha/Portfolio/Risk/Execution 分层。
- Freqtrade: lookahead-analysis 和 backtesting/dry-run/live 一致性。
- Qlib: qrun workflow 和 recorder/experiment 管理。
- MLflow: experiment/run/model/artifact tracking。
- OpenBB: provider extension 数据源插件化。
- Backtrader: broker、commission、slippage、analyzer 抽象。
