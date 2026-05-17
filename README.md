<div align="center">
  <h1>Hermes Quant Agent</h1>
  <h3>个人A股量化交易系统 — 巴菲特价值投资 × 钱学森控制论</h3>
  <p>
    <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
    <img src="https://img.shields.io/badge/version-5.1-orange" alt="Version">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/A%20Share-5204%20stocks-cyan" alt="A Share">
    <img src="https://img.shields.io/badge/platform-macOS-lightgrey" alt="macOS">
  </p>
</div>

---

## 概述

日频 A 股量化系统。巴菲特价值投资哲学为决策约束层，钱学森工程控制论为系统运行机制层——两者正交不冲突。

- **4 策略并行**：巴菲特价值精选 / 多因子月度调仓 / 控制论自适应 / LightGBM ML
- **5204 只全 A 股**：申万 31 行业分类，日线 + 财务 + 估值 + 资金 + 筹码 + 宏观
- **AI 驱动 R&D**：LLM 因子发现 → DSL 表达式 → IC/OOS 验证 → 自动注册
- **Web 终端**：Vue 3 Quantum Terminal，11 页暗色金融风
- **日频自动化**：15:30 cron 扫描 → Telegram 推送 → 次日 09:30 模拟执行

## 架构

```
认知层 (感知与进化)       约束层 (边界与安全)       执行层 (运行机制)
━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━
Data Registry → 28维度   RiskManager → 5规则预检   Cron 15:30 → 日频扫描
Factor DSL → 声明式计算   Data Cleaner → 6规则清洗  Tournament → 4策略对比
Feature Pipeline → PIT   PIT零前视 → 无未来数据    PaperBroker → 模拟交易
Model Registry → 版本化   Circuit Breaker → -15%    Telegram → 实时推送
LLM → 自动化R&D           Rate Limit → API稳定     Self-healing → 重试/降级
```

三层正交穿透所有组件——不是三层分别对应三个策略，而是每层在策略、数据、执行中同时生效。

## 功能

| 模块 | 说明 |
|------|------|
| **策略引擎** | 4 策略可插拔注册表；巴菲特三重过滤（能力圈→护城河→安全边际）；多因子四维打分（质量/估值/技术/市场）；控制论 regime 自适应；LightGBM PIT 特征 ML |
| **数据栈** | AKShare（日线/财务/宏观，免费不限流）+ Tushare MCP（PE/PB/资金/筹码/行业，258工具 2000积分门槛制）→ Parquet 本地存储 |
| **因子体系** | 19 价量因子 + 7 LLM 发现 + 9 外部富化（资金/筹码/宏观）+ 8 基本面 + 6 估值 + 4 动量增强 → 35+ 因子 |
| **回测** | PIT 滚动窗口零前视，信号驱动调仓（非日历），4 策略对比，15 项风险指标 |
| **ML** | LightGBM + Optuna 贝叶斯优化 + 滚动窗口 CV + regime-aware 模型 |
| **模拟交易** | PaperBroker（T+1/0.081%佣金/风控5规则），日频执行 → Parquet → Web 展示 |
| **Web** | Vue 3 + ECharts + FastAPI + DuckDB :memory:，11 页暗色金融终端 |
| **通知** | Telegram @buffett0320_bot，信号变化推送，可开关 |

## 锦标赛结果 (2026-05-16, 5204股全量)

| 策略 | 收益 | Sharpe | MaxDD |
|------|-----:|-------:|------:|
| 🥇 多因子月度调仓 | **+65.97%** | 0.47 | -15.5% |
| 🥈 控制论自适应 | +26.20% | 0.13 | -16.3% |
| 🥉 巴菲特价值精选 | 0.00% | 0.00 | 0.0% |
| 4. LightGBM ML | -38.63% | -0.38 | -52.6% |
| *基准 (CSI 300)* | *-17.46%* | | |

> 巴菲特 0 收益是因为 5204 股全池中符合安全边际的股票极少。200 股中盘池中巴菲特 +40.77% 🥇。ML 回撤-52.6%需要调参。最新结果见 `data/tournament/`。

## 快速开始

**前置条件**：Python 3.10+，Git

```bash
# 克隆
git clone https://github.com/RainbowLion0320/hermes-quant-agent.git
cd hermes-quant-agent

# 创建 venv
python3 -m venv venv && source venv/bin/activate

# 安装依赖
pip install akshare pandas numpy pyarrow pyyaml duckdb lightgbm optuna

# 配置 Tushare token（可选，用于 PE/PB/资金流等）
export TUSHARE_TOKEN=your_token_here

# 拉取全量日线（5204只，首次约40分钟）
python scripts/precache_financials.py

# 跑一次信号扫描
python scripts/compute_signals.py --limit 50

# 启动 Web
python -m web.api
# 打开 http://localhost:8501
```

## 项目结构

```
hermes-quant-agent/
├── config/
│   └── settings.yaml          # 全部可调参数 (唯一配置入口)
├── data/
│   ├── fetcher.py             # AKShare 3源 fallback
│   ├── financials.py          # 同花顺财务摘要 (三层缓存)
│   ├── symbols.py             # 5204只全A股 + 申万31行业
│   ├── feature_store.py       # PIT 特征存储 + enrich
│   ├── data_registry.py       # 28维度注册表
│   ├── cleaner.py             # 6规则数据清洗
│   ├── db.py / results_db.py  # Parquet存储 + DuckDB视图
│   ├── assets/                # 多资产适配器 (stock/etf/bond/futures/crypto)
│   ├── fetchers/              # 资金流/筹码/宏观数据获取
│   └── store/                 # Parquet: signals/ features/ paper/
├── signals/
│   ├── buffett.py             # 巴菲特三重过滤 (安全边际/DCF)
│   ├── multifactor.py         # 四维加权打分引擎
│   ├── ml_signals.py          # ML信号生成
│   ├── expression.py          # 因子 DSL 表达式引擎
│   ├── dsl_parser.py          # LLM 公式→计算
│   └── selection.py           # 横截面排名→交易信号
├── backtest/
│   ├── run_all_strategies.py  # 4策略对比回测 (日频引擎)
│   ├── analytics.py           # 15项风险指标
│   ├── pipeline.py            # 可插拔回测流水线
│   └── strategies/            # BaseStrategy + ML策略
├── broker/
│   ├── __init__.py            # PaperBroker (T+1/佣金/风控)
│   ├── exchange.py            # 多资产交易所 (A股/ETF/债券/期货)
│   ├── risk.py                # RiskManager 5规则预检
│   ├── persistence.py         # 状态持久化 (Parquet)
│   └── allocator.py           # AssetAllocator (regime→权重)
├── models/                    # LightGBM + 模型注册表 + 版本化
├── cybernetics/               # 市场状态检测 + 自适应参数
├── scripts/
│   ├── compute_signals.py     # Cron 15:30 日频扫描
│   ├── execute_paper_trades.py# 模拟交易日频执行
│   ├── build_features.py      # 批量PIT特征构建
│   ├── tune_model.py          # Optuna 训练
│   ├── strategy_tournament.py # 锦标赛对比
│   └── factor_hypothesis.py   # LLM因子发现
├── web/
│   ├── api/                   # FastAPI (routes + ws + jobs)
│   └── frontend/              # Vue 3 SPA (Quantum Terminal)
├── wiki/                      # LLM Wiki (16页知识库)
├── tests/                     # 边界测试
└── config/workflows/          # qrun YAML工作流
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
