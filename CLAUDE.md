# 星盘 / Astrolabe Quant OS — 个人量化研究与执行操作系统

## 项目概览
- 目的: 分阶段打造个人量化系统 (分析助手 → 信号系统 → 半自动交易)
- 命名: 中文产品名“星盘”，英文全名 `Astrolabe Quant OS`，仓库/包 slug `astrolabe-quant`
- 频率: 日线级别, 低频
- 架构: 巴菲特价值投资 (决策约束层) + 钱学森控制论 (运行机制层), 正交不冲突
- 注意: 这两个原则已写入 ~/.hermes/SOUL.md，是 Hermes 本身的架构而非仅项目的。本项目是它们在量化领域的具体落地。

## 环境
- Python: `.venv/bin/python`
- 数据: AKShare 与 Tushare 按 `data.ingestion.*` 和 `data.market.*` 分层接入；Tushare token 只读系统环境变量 `TUSHARE_TOKEN`
- 回测: 自研日频回测与 `PipelineBacktest`，生产流水线由 `backtest/pipeline_runner.py` + `pipeline/` 共享模块组成
- 本地运行产物: `var/`，包括 store/cache/artifacts/db/logs；不提交真实数据、模型、缓存、数据库和报告

## 数据源约定
- **AKShare** (日线行情，免费不限流): `stock_zh_a_daily` (新浪), 备选 `stock_zh_a_hist`/`stock_zh_a_hist_tx`
- **Tushare MCP** (财务/指标/情绪/行业，2000积分): `fina_indicator`, `daily_basic`, `income`/`balance`/`cashflow`, `sw_daily`, `margin`, `hk_hold`
- 请求频率: 3s间隔, 指数退避重试3次
- Tushare MCP 模块文档: `docs/tushare-mcp-guide.md`
- AKShare↔Tushare 分工: AKShare管日线，Tushare管三张表+daily_basic+融资融券+北向+申万+宏观

## 记忆系统
- Hindsight 保留为后台记忆服务和健康检查项。
- System Web 图谱入口是 CodeGraph 可视化，索引来自本地 `.codegraph/`，只在用户显式同步时更新。

## 当前状态
- 当前能力链路以 `docs/acceptance-matrix.md`、测试和代码为准。
- 产品/实现契约分别见 `docs/PRD.md` 与 `docs/specs/`。
- 历史进度、实验结果和已完成计划不保留在工作树；需要追溯时使用 `git log`、`git show` 和生成产物。

## 关键文件
```
~/astrolabe-quant/  # 项目目录
├── config/settings.yaml          # 全局配置 (策略/数据/资产注册表)
├── data/                          # Python 数据层源码包，不存放运行产物
│   ├── storage/                   # DataHub、Parquet、Manifest、DuckDB 视图、结果库
│   ├── ingestion/                 # provider、fetcher、Tushare 工具和补数治理
│   ├── market/                    # 价格服务、复权类型、symbols、行业流水线、市场视图
│   ├── features/                  # 日频 as-of PIT feature store 与因子记分板
│   ├── quality/                   # schema contract、quality gate、freshness gate
│   ├── ops/                       # audit、backfill、cron logger
│   ├── llm/                       # 通用 LLM provider usage ledger
│   ├── rates/                     # 无风险利率曲线 provider
│   ├── strategy/                  # strategy catalog 与插件注册
│   └── reference/                 # 可提交的静态 reference 数据和 seed 模型
├── var/                           # 本地运行产物根目录，git ignore
│   ├── store/                     # API 获取后的 parquet 原始/衍生数据
│   ├── cache/                     # 临时缓存与运行状态
│   ├── artifacts/                 # backtests/models/tournaments/reports
│   ├── db/                        # SQLite/DuckDB 本地数据库
│   └── logs/                      # 运行日志
├── signals/
│   ├── expression.py             # 因子 DSL 表达式引擎
│   ├── dsl_parser.py             # LLM公式→计算
│   ├── buffett.py                # 巴菲特价值过滤 (安全边际/DCF)
│   ├── multifactor.py            # 多因子打分 (五维加权含行业动量)
│   ├── ml_signals.py             # ML信号生成
│   └── selection.py              # 横截面排名→受限 buy list + hold rows
├── cybernetics/
│   └── orchestrator.py           # 市场状态检测 + 自适应参数
├── models/__init__.py            # LightGBM + 注册表
├── backtest/
│   ├── run_all_strategies.py     # N策略对比回测 (日频)
│   ├── buffett_real_scorer.py    # 滚动PIT评分器
│   ├── analytics.py              # 15项风险指标
│   ├── pipeline_runner.py        # 生产 PipelineBacktest 入口
│   └── strategies/{base,ml_strategy}.py
├── pipeline/                      # alpha/portfolio/risk/execution 共享流水线模块
├── broker/{__init__,exchange,risk,persistence,allocator}.py  # PaperBroker + 持久化 + 风控
├── scripts/
│   ├── compute_signals.py        # Cron 15:30 日频扫描 (五维评分含行业动量)
│   ├── execute_paper_trades.py   # Cron 09:30 模拟交易执行
│   ├── build_sector_snapshots.py # 行业快照: membership/performance/signals/exposure
│   ├── build_features.py         # 批量PIT特征构建
│   ├── tune_model.py             # Optuna训练
│   ├── weekly_retrain.py         # Cron 周六 模型重训
│   ├── strategy_tournament.py    # 锦标赛对比
│   ├── run_workflow.py           # qrun YAML工作流
│   └── cron_fetch_slow.py        # 限流数据日常填充
├── research/factors/hypothesis/   # LLM 因子假说、DSL、IC/OOS 评估和 CLI
├── web/api/routes/{market,strategies,stocks,portfolio,signals,sectors,settings,backtest,system,codegraph,pipeline,assets}.py
├── web/frontend/                 # Vue 3 SPA 星盘终端
├── wiki/                         # 长期概念、架构决策和参考知识
├── tests/                        # 合约测试 + 边界测试
├── docs/tushare-mcp-guide.md     # Tushare文档
├── config/workflows/*.yaml       # 研究/因子发现 pipeline
├── Makefile                      # 构建/扫描命令
└── CLAUDE.md
```
