<div align="center">
  <img src="docs/assets/readme-quant-iceberg.png" alt="蜉蝣见青天，星盘只是量化世界的一瞬微光" width="100%">
  <p><em>寄蜉蝣于天地，见青天之无垠。</em></p>

  <h1>星盘</h1>
  <h3>Astrolabe Quant OS — 个人量化研究与执行操作系统</h3>
  <p>
    <img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python">
    <img src="https://img.shields.io/badge/version-2.0.0-orange" alt="Version">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/A%20Share-universe-cyan" alt="A Share">
    <img src="https://img.shields.io/badge/platform-macOS-lightgrey" alt="macOS">
  </p>
</div>

---

## 概述

星盘（Astrolabe Quant OS）是一个日频 A 股量化研究与执行系统，自托管，全链路闭环。**巴菲特价值投资**为决策约束层，**钱学森工程控制论**为运行机制层——两者正交不冲突。

- **4 策略并行**：巴菲特价值精选 / 多因子月度调仓 / 控制论自适应 / LightGBM ML
- **全量 A 股 universe**：申万行业分类，日线 + 财务 + 估值 + 资金流 + 筹码 + 宏观
- **AI 驱动 R&D**：LLM 因子发现 → DSL 表达式 → IC/OOS 验证 → 自动注册
- **Web 终端**：Vue 3 星盘终端，6 个一级模块 + 二级 tab 的暗色金融工作台
- **日频自动化**：15:30 cron 扫描 → Telegram 推送 → 次日 09:30 模拟执行

## 架构

```
认知层 (感知与进化)       约束层 (边界与安全)       执行层 (运行机制)
━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━
Data Registry → 声明式维度 RiskManager → 5规则预检   Cron 15:30 → 日频扫描
DataHub → 维度路径+清单   Data Cleaner → 6规则清洗  Tournament → 4策略对比
Factor DSL → 声明式计算   PIT零前视 → 无未来数据    PaperBroker → 模拟交易
Feature Store → PIT富化   Circuit Breaker → -15%    Telegram → 实时推送
Model Registry → 版本化   Rate Limit → API稳定      Self-healing → 重试/降级
```

三层正交穿透所有组件——不是三层分别对应三个策略，而是每层在策略、数据、执行中同时生效。

## 功能

| 模块 | 说明 |
|------|------|
| **策略引擎** | 4 策略可插拔注册表；巴菲特三重过滤（能力圈→护城河→安全边际）；多因子五维打分（质量/估值/技术/市场/行业动量）；控制论 regime 自适应；LightGBM PIT 特征 ML |
| **数据栈** | AKShare（日线/财务/宏观，免费不限流）+ Tushare MCP（PE/PB/资金/筹码/行业）→ DataHub → Parquet 本地存储 |
| **因子体系** | 价量因子 + LLM 发现 + 外部富化（资金/筹码/宏观）+ 基本面 + 估值 + 动量增强，声明式 DSL 表达式引擎 |
| **回测** | PIT 滚动窗口零前视，信号驱动调仓（非日历），4 策略对比，15 项风险指标 |
| **ML** | LightGBM + Optuna 贝叶斯优化 + 滚动窗口 CV + regime-aware 模型 |
| **模拟交易** | PaperBroker（T+1/0.081%佣金/风控5规则），日频执行 → Parquet 持久化 → Web 展示 |
| **Web** | Vue 3 + ECharts + FastAPI + DuckDB :memory:，6 个一级模块 + 二级 tab 暗色金融终端 |
| **通知** | Telegram @buffett0320_bot，信号变化推送，可开关 |

## 锦标赛结果

长期 README 不固化样本内/OOS 排名、收益率或精选池数量，避免和本地数据、参数、回测窗口漂移。最新策略对比结果以 `data/tournament/`、Web `/strategy-lab` 和生成报告为准。

## 快速开始

**前置条件**：Python 3.11+，Git

```bash
# 克隆
git clone https://github.com/RainbowLion0320/astrolabe-quant.git
cd astrolabe-quant

# 创建 venv 并安装依赖
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 配置环境变量（可选，用于 PE/PB/资金流等）
export TUSHARE_TOKEN=your_token_here
export DEEPSEEK_API_KEY=your_key_here

# 拉取全量日线（首次约40分钟，亦可跳过直接启动Web按需加载）
python scripts/cron_fetch_daily.py

# 启动后端 API
uvicorn web.api.app:create_app --factory --port 8501

# 启动前端开发服务器
cd web/frontend
npm install
npm run dev
# 打开 http://localhost:5173
```

生产/本地单进程预览可先在 `web/frontend` 执行 `npm run build`，再由 FastAPI 在 `http://localhost:8501` 挂载 `dist/`。

> 详细环境配置见 `CLAUDE.md`，完整规格文档见 `docs/specs/`。

## 项目结构

```
astrolabe-quant/
├── config/
│   ├── settings.yaml              # 全局配置（唯一入口）
│   └── workflows/                 # qrun YAML 研究管线
├── data/
│   ├── fetcher.py                 # AKShare 3源 fallback
│   ├── datahub.py                 # ★ 数据中台：维度路径/manifest/原子写入
│   ├── data_registry.py           # ★ 声明式维度注册表：source/label/SLA/repair
│   ├── strategy_plugins.py        # 策略运行时注册：配置驱动 dispatch
│   ├── symbols.py                 # 全量A股 universe + 申万行业映射
│   ├── feature_store.py           # PIT 特征存储 + enrich
│   ├── financials.py              # 财务数据提取（三层缓存）
│   ├── cleaner.py                 # 6规则数据清洗
│   ├── db.py / results_db.py      # Parquet存储 + DuckDB视图
│   ├── assets/{base,stock}.py     # 多资产架构
│   ├── fetchers/                  # 资金流/筹码/宏观数据获取器
│   └── store/                     # Parquet: stock/macro/signals/features/
├── signals/
│   ├── buffett.py                 # 巴菲特三重过滤（安全边际/DCF）
│   ├── multifactor.py             # 五维加权打分引擎
│   ├── ml_signals.py              # ML信号生成
│   ├── expression.py              # 因子 DSL 表达式引擎
│   ├── dsl_parser.py              # LLM 公式→计算
│   └── selection.py               # 横截面排名→交易信号
├── backtest/
│   ├── run_all_strategies.py      # 4策略对比回测（日频引擎）
│   ├── analytics.py               # 15项风险指标
│   ├── pipeline.py                # 可插拔回测流水线
│   └── strategies/                # BaseStrategy + ML策略
├── broker/
│   ├── __init__.py                # PaperBroker（T+1/佣金/风控）
│   ├── exchange.py                # 多资产交易所
│   ├── risk.py                    # RiskManager 5规则预检
│   ├── persistence.py             # 状态持久化（Parquet）
│   └── allocator.py               # AssetAllocator（regime→权重）
├── models/                        # LightGBM + 模型注册表 + 版本化
├── cybernetics/                   # 市场状态检测 + 自适应参数
├── scripts/
│   ├── compute_signals.py         # Cron 15:30 日频扫描
│   ├── execute_paper_trades.py    # 模拟交易日频执行
│   ├── build_features.py          # 批量PIT特征构建
│   ├── tune_model.py              # Optuna 训练
│   ├── weekly_retrain.py          # Cron 周六 模型重训
│   ├── strategy_tournament.py     # 锦标赛对比
│   ├── factor_hypothesis.py       # LLM因子发现
│   └── run_workflow.py            # qrun YAML工作流
├── web/
│   ├── api/                       # FastAPI（10 routes + ws + jobs）
│   └── frontend/                  # Vue 3 SPA（星盘终端）
├── wiki/                          # 长期概念、架构决策和参考知识
├── docs/specs/                    # ★ 6份能力域技术规格文档
├── tests/                         # 合约测试 + 边界测试
├── CLAUDE.md                      # Claude Code 项目指令
├── Makefile                       # 构建/扫描命令
└── README.md
```

## Cron 任务

| 任务 | 调度 | 说明 |
|------|------|------|
| 日频信号扫描 | 交易日 15:30 | 4策略串行扫描 → Telegram |
| 模拟交易执行 | 交易日 09:30 | 读昨日信号 → 模拟成交 → Parquet |
| 限流数据积累 | 交易日 16:00 | 涨跌停/研报慢速爬取 |
| 周模型重训 | 周六 06:00 | LightGBM 重训 + 特征重建 |

## 许可证

MIT License — 详见 [LICENSE](LICENSE)
