# 星盘 / Astrolabe Quant OS — 产品需求文档 (PRD)

> 版本: 1.1 | 更新: 2026-05-23 | 状态: 产品范围基线

## 1. 产品定义

星盘（Astrolabe Quant OS）是一个个人量化研究与执行操作系统。分阶段从数据分析助手演进为信号生成系统，最终支持半自动交易。核心理念：**巴菲特价值投资为决策约束层，钱学森控制论为运行机制层**——两者正交，前者管边界和原则，后者管执行和反馈。

- **频率**: 日线级别，低频交易
- **市场**: A股全量 + 申万行业
- **资产**: 股票为核心，ETF/债券/期货/加密货币为可开关扩展

## 2. 目标用户

| 优先级 | 用户角色 | 典型场景 |
|--------|---------|---------|
| P0 | 个人量化研究者（系统所有者） | 日频信号扫描、策略对比、模拟交易 |
| P1 | AI 协作系统（Claude/Codex） | 代码审查、因子发现、bug 修复、Wiki 维护 |
| P2 | 开源社区量化开发者 | 学习架构、复用组件、贡献策略 |

## 3. 核心能力

### 3.1 数据管道
从 AKShare + Tushare 拉取多源数据，经清洗、缓存、存储为本地 Parquet，通过 DataHub 统一路径访问。覆盖日线行情、财务摘要、每日估值、资金流向、行业数据、宏观指标。数据维度由 `config/settings.yaml` 的 `data_registry` 声明，不在 PRD 中复制固定数量。

### 3.2 信号体系
四种策略生成交易信号：巴菲特价值过滤（能力圈→护城河→安全边际）、多因子打分（质量/估值/技术/市场/行业动量五维加权 + 横截面排名）、LightGBM ML（PIT特征→模型预测）、控制论自适应（regime 检测→参数调整）。因子 DSL 支持声明式因子表达和 LLM 公式解析。

### 3.3 回测引擎
日频回测，严格 PIT 无前视防护。支持 N 策略同时跑对比（锦标赛模式），输出 15 项风险指标（Sharpe/Sortino/Calmar/Alpha/Beta/MaxDD 等）。风险调整收益必须使用本地无风险利率曲线，缺少曲线数据时停止指标计算。

### 3.4 执行层
PaperBroker 本地模拟撮合，5 规则风控（仓位上限/总敞口/下单次数/回撤熔断/单笔金额），Parquet 持久化状态和 NAV。Cron 日频调度（15:30 扫描，09:30 执行）。

### 3.5 Web 平台
Vue 3 星盘终端（Pinia + ECharts + Tailwind），FastAPI 后端按业务域拆分路由，WebSocket 实时进度推送，DuckDB :memory: 零锁查询。

### 3.6 多资产架构
Stock/ETF/Bond/Futures/Crypto 五类资产，统一 AssetAdapter ABC 接口，AssetAllocator 按 regime 动态分配权重。开关控制：`config/settings.yaml` 中每个资产类型可独立启用/禁用。

## 4. 系统边界

**覆盖范围:**
- A股日线行情、财务数据、估值、资金流向、宏观指标
- 日频策略信号生成和回测
- 模拟交易（PaperBroker）
- 单用户本地运行

**不覆盖:**
- 分钟级/分时级高频交易
- 期权、期货实盘交易
- 多用户 SaaS 平台
- 实时行情推送（仅日末批量拉取）
- 无人工确认的全自动实盘交易

## 5. 成功标准

| 维度 | 指标 | 目标 |
|------|------|------|
| 策略收益 | 年化收益率 | > 跑赢基准（上证综指） |
| 风险控制 | Sharpe Ratio | > 0.5 |
| 风险控制 | Max Drawdown | < 25% |
| 数据就绪 | 日频数据拉取完成时间 | 交易日 15:30 前 |
| 回测可信 | 前视偏差 | 零容忍 |
| 回测可信 | 金融指标公式 | 行业标准（Sortino 用 RMS 法，Beta 用 cov 矩阵） |
| 回测可信 | 无风险利率 | 本地曲线驱动，禁止固定值/fallback |
| 代码质量 | 测试覆盖 | 合约测试 + 边界测试 20+ |
| 操作可靠 | Cron 错误可观测 | 自动记录到 `data/store/_cron_log/` |

## 6. 非功能需求

### 6.1 数据安全
- 所有行情和财务数据存储为本地 Parquet 文件，不依赖云端数据库
- `data/store/` 目录在 `.gitignore` 中，不提交历史行情

### 6.2 API 治理
- AKShare 请求节流：全局最小间隔 3 秒
- Tushare 请求节流：0.3 秒间隔，频率超限自动停止当日请求
- 重试机制：指数退避 2s→4s→8s，最多 3 次
- 代理绕过：自动清除代理环境变量，直连境内数据源

### 6.3 可观测性
- Cron 作业运行日志记录到 `data/store/_cron_log/{script}.jsonl`
- 自动轮转：每文件最多 500 行
- Web 端 DB Health 页面展示 DataRegistry 中启用维度的健康状态
- 错误通知：支持 Telegram/企业微信/飞书推送（需配置）

### 6.4 性能
- 全量 A 股日线缓存命中时 < 1 秒返回
- DuckDB :memory: 模式，Web 查询零锁等待
- 财务数据三层缓存：内存 → Parquet 磁盘 → AKShare API

## 7. 技术约束

| 约束 | 选择 | 原因 |
|------|------|------|
| 语言 | Python 3.11+ | 量化生态（pandas/numpy/scikit-learn） |
| 数据存储 | Parquet + DuckDB | 列存压缩，SQL 查询，零配置 |
| 数据源 | AKShare + Tushare MCP | 免费不限流 + 财务深度数据互补 |
| 回测框架 | 自研（非 Backtrader） | 需要 PIT 特征存储和锦标赛对比，Backtrader 不满足 |
| 前端框架 | Vue 3 + Vite | SPA，与 FastAPI 分离部署 |
| 配置管理 | YAML (settings.yaml) | 人类可读写，支持注释 |

## 8. 项目结构

```
~/astrolabe-quant/
├── config/settings.yaml          # 全局配置 (策略/数据/风控/资产)
├── data/                         # 数据层
│   ├── fetcher.py                # AKShare 三源 fallback
│   ├── datahub.py                # 统一路径+原子写入+清单审计
│   ├── financials.py             # 财务数据提取 (三层缓存)
│   ├── feature_store.py          # PIT 特征构建
│   ├── data_registry.py          # 数据维度注册表+健康检查
│   ├── cleaner.py                # 6 规则数据清洗
│   ├── symbols.py                # A股股票池+申万行业映射
│   └── cron_logger.py            # Cron 错误可观测性
├── signals/                      # 信号层
│   ├── expression.py             # 因子 DSL 表达式引擎
│   ├── dsl_parser.py             # LLM 公式→计算
│   ├── buffett.py                # 巴菲特三重过滤
│   ├── multifactor.py            # 多因子五维打分
│   ├── ml_signals.py             # ML 信号生成
│   └── selection.py              # 横截面排名→受限 buy list + hold rows
├── backtest/                     # 回测层
│   ├── run_all_strategies.py     # N 策略锦标赛
│   ├── analytics.py              # 15 项风险指标
│   ├── pipeline.py               # 可插拔回测流水线
│   └── strategies/               # ML + Base 策略
├── broker/                       # 执行层
│   ├── __init__.py               # PaperBroker 模拟券商
│   ├── risk.py                   # 5 规则风控
│   ├── exchange.py               # 多资产交易所
│   ├── allocator.py              # Regime 资产分配
│   └── persistence.py            # Parquet 状态持久化
├── cybernetics/                  # 控制论层
│   └── orchestrator.py           # 市场状态检测+自适应参数
├── web/                          # Web 平台
│   ├── api/                      # FastAPI (业务路由 + WebSocket + Jobs)
│   └── frontend/                 # Vue 3 SPA 星盘终端
├── models/                       # ML 模型注册表
├── scripts/                      # Cron/工作流脚本
├── tests/                        # 合约测试+边界测试
├── wiki/                         # LLM Wiki 知识库 (概念/决策/参考)
├── docs/                         # PRD/spec/验收矩阵/开发计划
│   ├── PRD.md
│   ├── DOCUMENTATION.md
│   └── specs/
├── Makefile                      # 构建/扫描命令
└── pyproject.toml                # Python 包配置
```

## 9. 演进脉络

本项目的演进由 git 历史和 `docs/acceptance-matrix.md` 追踪。PRD 只保留稳定能力边界：

- 数据基础：AKShare/Tushare、Parquet、DataHub、DataRegistry。
- 信号生成：巴菲特约束、多因子、ML、控制论、因子 DSL。
- 回测研究：PIT 防护、风险指标、锦标赛对比。
- 执行模拟：PaperBroker、风控、NAV/交易状态持久化。
- Web 平台：市场总览、市场研究、策略实验室、组合执行、数据中台、系统控制。
- 扩展方向：人工确认式半自动执行、更多数据源、真实浏览器回归测试、研究实验治理。
