---
title: AI 自动化交易框架路线图
created: 2026-05-14
updated: 2026-05-16
type: decision
tags: [AI, ML, RL, architecture, roadmap, strategy, factor-DSL, PIT, LightGBM, RD-Agent, LLM]
---

# AI 自动化交易框架路线图

从手调规则策略 → AI/ML 驱动的自动化 R&D 循环。

## 当前进度 (截至 2026-05-16)

### 全A股扩满 ✅

- CIRCLE_STOCKS: 1000 → 5517 只 (过滤后 5204 有效)
- PIT特征: 100月 × 5204只 × 53列, 427K行, PE/PB 覆盖 70-92%
- 模型重训: Optuna 20 trials, CV IC 0.0373 (旧 0.0344), In-sample 0.6169
- 锦标赛: 全量 5204 只 (4策略对比, 正在跑)

### 已完成的 Phase

| Phase | 内容 | 状态 |
|-------|------|:----:|
| 1.0 | 数据基础 (AKShare日线, 三表, 申万行业) | ✅ |
| 2.0 | 三策略体系 (巴菲特/多因子/控制论) | ✅ |
| 2.5 | 策略注册表重构 (消除硬编码) | ✅ |
| 3.0 | ML基础设施 (因子DSL, PIT特征, LightGBM) | ✅ |
| 3.5 | 自动化R&D (build_features, tune_model, tournament) | ✅ |
| 4.0 | LLM因子发现 + DSL解析 + IC/OOS验证 | ✅ |
| 4.1 | 多资产架构 (5种资产适配器) | ✅ |
| 4.2 | 28维度数据注册表 + PIT富化 | ✅ |
| 4.3 | 风险控制 + 数据清洗 + 统一工作流 | ✅ |
| 5.0 | 全A股扩满 + 模型全量重训 | 🔄 tournament跑中 |

## 下阶段计划 (Phase 5.1+)

### P1 — 模型成熟度

- [ ] **regime ML 接入推理**: lgbm_{bull,bear,sideways}.pkl 已训好 (IC 0.91/0.92/0.74), 未接入 ml_signals.py 推理管线
- [ ] **因子记分板自动淘汰**: `data/factor_scoreboard.py` 数据已累积, 缺自动淘汰逻辑 (IC<0.01 或 ICIR<0.3 连续三轮淘汰)
- [ ] **模型 A/B 对比**: 新旧模型锦标赛并存, 自动切换更优模型
- [ ] **LLM 因子发现 rerun**: prompt 已修正 (失败案例+Rule-of-Thumb), 待 `--rounds 3 --auto-register` 重跑

### P2 — 数据广度

- [ ] **ETF 真实行情**: 当前 index proxy 占位 (short-term), 待 AKShare `fund_etf_hist_em` 恢复或接入 Tushare 付费 ETF 数据
- [ ] **Crypto CCXT 接入**: `data/assets/crypto.py` 框架已有, 需 `pip install ccxt` + 交易所 API key
- [ ] **北向/融资融券 日常积累**: 限速慢, cron 后台慢慢填 (已有 scripts/cron_fetch_slow.py)
- [ ] **因子/特征扩展到 ETF/债券**: 当前仅股票有完整 53 列特征

### P3 — 生产化

- [ ] **实盘 Broker 对接**: 当前 PaperBroker, 需券商 API (华泰/中信等)
- [ ] **信号推送 Telegram**: 已有 @buffett0320_bot, 需确认每日推送稳定性
- [ ] **Web 策略卡片实时数据**: 当前读 Parquet 静态快照, 可加 WebSocket 实时推送
- [ ] **回测引擎加速**: 巴菲特 DCF 评分 5204 只是瓶颈, 可分批/并行/缓存中间结果

## 瓶颈

| 瓶颈 | 影响 | 缓解 |
|------|------|------|
| 网络不稳定 (AKShare/Tushare) | 数据拉取卡死 | 磁盘缓存 + socket 30s超时 |
| Python DCF评分慢 (5204只) | 锦标赛 15min+ | 纯本地计算, 等就完了 |
| ETF/Crypto 数据源空窗 | 多资产回测缺真数据 | index proxy 占位 |
| 实盘需券商 API | 无法自动下单 | 信号推 Telegram, 手动确认 |

| 任务 | 状态 | 产出 |
|------|:--:|------|
| 3.0-1 Strategy 接口 | ✅ | `backtest/strategies/base.py` — BaseStrategy + StrategyRegistry |
| 3.0-2 Exchange 成本 | ✅ | `broker/exchange.py` — AShareExchange (印花税0.05%/佣金0.025%/过户费0.001%) |
| 3.0-3 因子 DSL | ✅ | `signals/expression.py` — 26因子声明式 (Ref/MA/Std/Delta/Ret/Gt/Lt/BinOp等19个Alpha因子) |
| 3.0-4 PIT 特征存储 | ✅ | `data/store/features/YYYY-MM.parquet` — 月切片零前视, `data/feature_store.py` 构建器 |
| 3.0-5 LightGBM | ✅ | `models/__init__.py` — LightGBMRegressor + sklearn GBR fallback (macOS libomp兼容) |

**验证**: 50股×6月 → 300行, IC=-0.12 (小样本预期内)

### Phase 3.5 — 自动化 R&D ✅

| 任务 | 状态 | 产出 |
|------|:--:|------|
| 3.5-1 Model Registry | ✅ | `models/__init__.py` — BaseModel + save/load/list_versions + `data/models/registry.json` |
| 3.5-2 Optuna 超参搜索 | ✅ | `scripts/tune_model.py` — 48月训练/6月测试/12月步长滚动CV |
| 3.5-3 策略锦标赛 | ✅ | `scripts/strategy_tournament.py` — 4策略自动对比 (回测+评分+导出JSON) |
| 3.5-4 ML 生产集成 | ✅ | `signals/ml_signals.py` + cron `scripts/compute_signals.py` 集成 ml_lgbm 策略 |

**结果**:
- Optuna 结果: 见 `data/models/lgbm_best_meta.json`。
- In-sample IC = 0.551
- 锦标赛 (100股 2020-2026): ML +28.31% / 多因子 +4.56% / 控制论 +0.49% / 巴菲特 n/a

### Phase 4.0 — AI Agent 驱动 (部分完成)

| 任务 | 状态 | 产出 |
|------|:--:|------|
| 4.0-1 LLM 因子生成 | ✅ | `scripts/factor_hypothesis.py` — deepseek-v4-pro 生成 → DSL解析器 → IC评估 |
| 4.0-2 因子-模型联合优化 | 🟡 | 单轮已验证，自动迭代循环尚未实现 |
| 4.0-3 自适应策略切换 | 🔜 | 待实现 |

LLM 因子研究结果: 见 `scripts/factor_hypothesis.py` 最新运行的输出。
- 8个候选因子 → 7个通过IC测试 (IC > 0.01)
- Top因子: `midpoint_bias` IC=0.216, `vol_adj_mom_5d` IC=0.215, `intraday_close_strength` IC=0.206
- $0.00/cycle (用自己的API key)
- 7个因子已加入 `alpha_factors()` → 26因子体系

**局限性**: ML +28.31% 低于纯LightGBM +36.22% (因子数13→26, 过拟合)。In-sample IC 0.194→0.551 但 OOS 下降, 验证了RD-Agent论文的发现：更多因子≠更好, 需要因子选择。

---

## 待实现

### Phase 4.0-2: 因子-模型联合优化循环

借鉴 RD-Agent 核心逻辑:
```
for round in range(max_rounds):
    1. Research: LLM 提出 K 个候选因子
    2. Development: LightGBM 训练 + 评估
    3. Feedback: IC 排序 → 保留 top-K
    4. 终止条件: 连续 N 轮无提升
```

当前单轮已通, 需添加:
- 多轮迭代 (阈值判断自动停止)
- 因子重要性 → 提示下一轮LLM ("exploited short-term volatility too much → suggest fundamental factors")
- 结果持久化 (因子历史表)

### Phase 4.0-3: 自适应策略切换

- 每月评估各策略近3-6月相对表现
- Regime变化时权重调整 (not equal-weight, dynamic)
- "策略组合"替代"单一策略"

---

### Phase 5.0 — 多资产架构 ✅

多资产系统，开关控制，5种资产类型可独立启用/禁用。

| 任务 | 状态 | 产出 |
|------|:--:|------|
| 5.0-1 MultiAssetExchange | ✅ | 按资产类型分发费率 (stock 0.102%, ETF 0.01%, bond 0.004%, futures按手) |
| 5.0-2 ETFAsset | ✅ | 8只ETF (权益/黄金/债券/货币), AKShare+指数代理 |
| 5.0-3 AssetAllocator | ✅ | regime → 动态权重 → 跨资产下单 |
| 5.0-4 配置开关 | ✅ | settings.yaml assets.{type}.enabled 控制 |

### Phase 5.1 — 资产扩展 ✅

| 任务 | 状态 | 产出 |
|------|:--:|------|
| 5.1-1 BondAsset | ✅ | 国债收益率曲线 (2/5/10/30Y) + 可转债 |
| 5.1-2 FuturesAsset | ✅ | 11只主力合约 (IF/IC/IH/IM/T/TF/TS/RB/AU/CU/SC) |
| 5.1-3 CryptoAsset | 🔜 | 占位框架, CCXT待接入 |
| 5.1-4 多资产锦标赛 | ✅ | stock-only -46% vs ETF-only +28% vs multi-asset -26% |

---

## 与现有系统的关系

```
手调策略（保留）               AI 策略（已集成）
├─ buffett (年调仓)            ├─ ml_lgbm (日预测, 月调仓)
├─ multifactor (月调仓)        │   51因子 LightGBM
└─ cybernetic (月+regime)      │   锦标赛最优
        │                              │
        └──────────┬───────────────────┘
                   ▼
         Strategy Registry (4策略平等竞争)
                   │
         run_all_strategies.py (统一回测)
                   │
         Web UI (4策略曲线叠加, 点击高亮)
                   │
         Multi-Asset Allocation (5种资产, 可开关)
```

---

## Qlib 模式映射 (以我们实现为准)

| Qlib 模式 | 我们的实现 | 状态 |
|-----------|-----------|:--:|
| BaseStrategy | `backtest/strategies/base.py` | ✅ |
| Exchange | `broker/exchange.py` | ✅ |
| ExpressionOps | `signals/expression.py` (26因子) | ✅ |
| PIT Database | `data/store/features/YYYY-MM.parquet` | ✅ |
| DataHandler | Parquet + DuckDB `:memory:` | ✅ |
| Backtest Analyzer | `backtest/analytics.py` (15项指标) | ✅ |
| Model Registry | `models/__init__.py` + `data/models/registry.json` | ✅ |
| Workflow (qrun) | Makefile + scripts/compute_signals.py (cron) | ✅ |
| RD-Agent | `scripts/factor_hypothesis.py` | 🟡 单轮 |

## See Also

- [[ml-pipeline]] — ML管道端到端文档
- [[system-architecture]] — 系统五层架构 (含ML层)
- [[strategy-evolution]] — 四策略回测结果
- [[duckdb-migration]] — Parquet 存储架构
