# 星盘 / Astrolabe Quant OS — 个人量化研究与执行操作系统

## 项目概览
- 目的: 分阶段打造个人量化系统 (分析助手 → 信号系统 → 半自动交易)
- 命名: 中文产品名“星盘”，英文全名 `Astrolabe Quant OS`，仓库/包 slug `astrolabe-quant`
- 频率: 日线级别, 低频
- 架构: 巴菲特价值投资 (决策约束层) + 钱学森控制论 (运行机制层), 正交不冲突
- 注意: 这两个原则已写入 ~/.hermes/SOUL.md，是 Hermes 本身的架构而非仅项目的。本项目是它们在量化领域的具体落地。

## 环境
- Python: `~/.hermes/hermes-agent/venv/bin/python3`
- 数据: AKShare 1.18.60, 优先用新浪源, 东方财富/腾讯作备选
- 回测: 自研日频回测与 PipelineBacktest（非 Backtrader）
- 缓存: parquet (需 pyarrow)
- 代理: fetcher.py 会自动绕过 v2ray

## 数据源约定
- **AKShare** (日线行情，免费不限流): `stock_zh_a_daily` (新浪), 备选 `stock_zh_a_hist`/`stock_zh_a_hist_tx`
- **Tushare MCP** (财务/指标/情绪/行业，2000积分): `fina_indicator`, `daily_basic`, `income`/`balance`/`cashflow`, `sw_daily`, `margin`, `hk_hold`
- 请求频率: 3s间隔, 指数退避重试3次
- Tushare MCP 模块文档: `docs/tushare-mcp-guide.md`
- AKShare↔Tushare 分工: AKShare管日线，Tushare管三张表+daily_basic+融资融券+北向+申万+宏观

## 记忆系统
- 已配置 Hindsight Local 模式 (deepseek-v4-flash, 星盘记忆库; bank_id=astrolabe-quant)
- 首次启动需 /reset, daemon 会自动拉起 (首次初始化约1分钟)

## 当前状态
- 当前能力链路以 `docs/acceptance-matrix.md`、测试和代码为准。
- 产品/实现契约分别见 `docs/PRD.md` 与 `docs/specs/`。
- 历史进度、实验结果和已完成计划不保留在工作树；需要追溯时使用 `git log`、`git show` 和生成产物。

## 关键文件
```
~/astrolabe-quant/  # 项目目录
├── config/settings.yaml          # 全局配置 (策略/数据/资产注册表)
├── data/
│   ├── fetcher.py                # AKShare 3源 fallback
│   ├── financials.py             # 财务数据提取 (三层缓存)
│   ├── symbols.py                # 全量A股 universe + 申万行业映射
│   ├── feature_store.py          # PIT 特征存储 + enrich
│   ├── data_registry.py          # ★ 维度+健康注册表: source/label/SLA/repair/partition 单源
│   ├── cleaner.py                # 6规则数据清洗
│   ├── tushare_utils.py          # Token 统一管理
│   ├── datahub.py                 # ★ 数据中台: dimension_path()/manifest/原子写入/追加去重/审计
│   ├── strategy_plugins.py        # 策略运行时注册: 配置驱动dispatch, 动态import
│   ├── db.py + results_db.py     # Parquet存储 + DuckDB视图
│   ├── sectors.py                 # 行业流水线: membership/performance/signals/exposure
│   ├── assets/{base,stock}.py    # 多资产架构 + StockAsset
│   ├── fetchers/{moneyflow,holders,macro}.py  # 数据获取器
│   └── store/                    # Parquet: stock/macro/signals/features/_manifest/
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
│   ├── pipeline.py               # 可插拔回测流水线
│   └── strategies/{base,ml_strategy}.py
├── broker/{__init__,exchange,risk,persistence,allocator}.py  # PaperBroker + 持久化 + 风控
├── scripts/
│   ├── compute_signals.py        # Cron 15:30 日频扫描 (五维评分含行业动量)
│   ├── execute_paper_trades.py   # Cron 09:30 模拟交易执行
│   ├── build_sector_snapshots.py # 行业快照: membership/performance/signals/exposure
│   ├── build_features.py         # 批量PIT特征构建
│   ├── tune_model.py             # Optuna训练
│   ├── weekly_retrain.py         # Cron 周六 模型重训
│   ├── strategy_tournament.py    # 锦标赛对比
│   ├── factor_hypothesis.py      # LLM因子发现
│   ├── run_workflow.py           # qrun YAML工作流
│   └── cron_fetch_slow.py        # 限流数据日常填充
├── web/api/routes/{market,strategies,stocks,portfolio,signals,sectors,settings,backtest,system,hindsight,pipeline,assets}.py
├── web/frontend/                 # Vue 3 SPA 星盘终端
├── wiki/                         # 长期概念、架构决策和参考知识
├── tests/                        # 合约测试 + 边界测试
├── docs/tushare-mcp-guide.md     # Tushare文档
├── config/workflows/*.yaml       # 研究/因子发现 pipeline
├── Makefile                      # 构建/扫描命令
└── CLAUDE.md
```
