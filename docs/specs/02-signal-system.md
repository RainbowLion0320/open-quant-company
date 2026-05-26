# Spec: 信号系统 (Signal System)

> 版本: 1.1 | 更新: 2026-05-23 | 关联: [PRD](../PRD.md) [Data Pipeline](01-data-pipeline.md) [Backtest Engine](03-backtest-engine.md)

## 1. 概述

信号系统是量化策略的核心——从原始数据生成交易信号（买/卖/持有）。四种策略仍可独立运行，但研究定位不再是简单平级：Buffett 是质量过滤层，Multifactor 是主 Alpha，ML 是辅助 Alpha，Cybernetic 是 regime 风险覆盖层。每日输出信号到 `data/store/signals/{strategy}.parquet`，供回测引擎和执行层消费。

**设计原则：**
- **策略独立性** — 每种策略可独立运行、独立回测、独立对比（锦标赛模式）
- **可解释性** — 巴菲特策略输出自然语言判定理由，ML 策略输出特征重要性
- **因子复用** — DSL 表达式引擎使因子可声明式组合，LLM 可发现新因子
- **研究晋级** — 策略进入 paper / production 前必须通过 OOS、风险收益、IC/ICIR、换手和交易次数门槛

## 2. 组件架构

```
┌─────────────────────────────────────────────────────┐
│                  config/settings.yaml                 │
│        signals.buffett / signals.multifactor          │
│        signals.ml_lgbm / signals.cybernetic           │
└──────────────────────┬──────────────────────────────┘
                       │
       ┌───────────────┼───────────────┬───────────────┐
       │               │               │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│  buffett    │ │multifactor  │ │ ml_signals  │ │cybernetics  │
│ 三重过滤     │ │ 五维加权     │ │ LightGBM    │ │ 控制论自适应  │
│ 价值约束层   │ │ 打分排名     │ │ PIT 特征    │ │ regime 检测  │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │               │
       └───────────────┼───────────────┴───────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  selection.py                         │
│         横截面排名 → 交易信号 (buy/sell/hold)           │
│         输出: data/store/signals/{strategy}.parquet    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Factor DSL Layer                         │
│  expression.py — 声明式因子表达 (RSI/MA/MACD/Delta)   │
│  dsl_parser.py — LLM 公式 → 可执行计算 + IC 检验      │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│              Research Governance                     │
│  research/strategy_governance.py — 策略分层 + 晋级门槛 │
│  signals/factor_research.py — IC/ICIR/分组收益/相关性 │
└─────────────────────────────────────────────────────┘
```

### 2.1 巴菲特价值过滤 (buffett.py)

**定位：决策约束层，不是信号生成器。** 在多因子/ML 信号之上增加硬约束——不符合巴菲特标准的，信号再强也不操作。

**三重过滤：**

| 过滤层 | 检查项 | 阈值 (可配置) |
|--------|--------|-------------|
| 能力圈 | 行业在 `circle_of_competence` 白名单内 | 银行/保险/券商/消费/制造 |
| 护城河 | 5Y 平均 ROE + 毛利率 + 负债率 | ROE > 15%, 毛利率 > 30%, D/E < 2.0 |
| 安全边际 | DCF 内在价值 vs 当前股价 | 安全边际 > 20% |

**金融板块特殊处理：** 银行/保险/券商不适用毛利率指标，改为销售净利率（`avg_net_margin_5y`）。

**输出：** `BuffettScore` dataclass，含 verdict（PASS/FAIL_MARGIN/FAIL_MOAT/FAIL_CIRCLE）+ 0-100 综合分 + 判定理由列表。

### 2.2 多因子打分 (multifactor.py)

**五维加权模型：**

| 维度 | 权重 | 因子 |
|------|------|------|
| 质量 (Quality) | 35% | 巴菲特综合评分 + 5Y ROE + ROE 趋势 |
| 估值 (Valuation) | 25% | 安全边际 + PE/PB 分位数 |
| 技术 (Technical) | 15% | 1M/3M 动量 + 波动率 |
| 市场 (Market) | 10% | 市场状态下的板块适配 |
| 行业动量 (Industry Momentum) | 15% | 申万行业 20D/60D 动量，经行业成员映射到个股 |

权重来源为 `config/settings.yaml` → `signals.multifactor.weights`，文档中的百分比只描述当前默认配置。

**行业动量数据源：** 优先读取 `DataHub.dimension_root("sector_performance_snapshot")` 下的最新快照，并通过行业成员维度完成个股→行业映射。缺少行业快照或映射时回退到中性分 50，不阻断信号生成。

**输出：** `MultiFactorScorer.score_components()` → `{quality, valuation, technical, market, industry, total}`，每维度 0-100 分。

### 2.3 ML 信号 (ml_signals.py)

**模型：** LightGBM 二分类（未来 20 日收益 > 中位数 = 正样本）

**PIT 特征：** 每月从 `data/store/features/YYYY-MM.parquet` 读取特征切片，训练/预测严格使用该月之前的数据

**训练流程：**
1. `scripts/build_features.py` — 批量构建月度 PIT 特征切片
2. `scripts/tune_model.py` — Optuna 超参搜索，输出到 `data/models/`
3. `scripts/weekly_retrain.py` — Cron 周六自动重训

**模型注册表：** `models/__init__.py` → `list_models()` / `load_model(name)` / `model_metadata(name)`

### 2.4 控制论自适应 (cybernetics/orchestrator.py)

**核心理念：** 不作为独立主选股策略，而是检测当前市场状态，据此调整策略参数、仓位上限和资产配置风险预算。

**Regime 检测：**
- **Bull:** 价格 > MA5 > MA20 > MA60（月度 K 线判断，避免日频噪声）
- **Bear:** 价格 < MA5 < MA20 < MA60
- **Sideways:** 其他情况

**自适应参数调整：**
- Bull → 提高仓位上限、放宽止损
- Bear → 降低仓位、收紧止损、增加现金比例
- Sideways → 默认参数

**市场广度：** 计算全市场 > MA20 的股票比例，作为辅助指标。

### 2.5 Market Regime 离线训练与晋级

Market Regime 生产公式保持确定性和可解释性，但不再只能靠人工拍权重。`research/regime_training.py` 和 `scripts/train_market_regime.py` 提供 champion/challenger 研究闭环：

- **Champion**：当前生产公式，作为所有候选规则的基准。
- **Challenger**：离线搜索出的可解释候选规则，包含权重、阈值、平滑窗口和最短持续期。
- **Walk-forward**：按时间滚动训练/验证，禁止随机切分和未来函数。
- **策略 A/B**：比较固定仓位、当前公式、trend-only、trend+breadth、best challenger 的风险收益表现。
- **晋级门槛**：只有 challenger 在预测区分、bear 风险识别、策略贡献、稳定性和复杂度惩罚后仍优于 champion，才生成 `recommended_config.yaml` 供人工审查。

第一版训练器只写 `reports/regime_training/` 研究报告，不自动改 `cybernetics/regime_scoring.py` 或 `config/settings.yaml`。

### 2.5.1 Market Regime 挣钱导向训练

`scripts/train_market_regime_profit.py` 是收益导向离线训练器，目标从“公式是否更稳定、更能解释未来标签”升级为“公式是否能作为全局 risk-on/risk-off 风险预算信号提高可交易资产的样本外收益/回撤比”。

- **信号定义**：`risk_on` 表示提高市场 beta 暴露；`neutral` 表示中等暴露；`risk_off` 表示降低权益暴露并转向现金/债券等防御代理。
- **验证对象**：使用本地指数、ETF、现金、债券代理等可交易或近似可交易资产；不把当前未成熟选股策略、模拟账户 PnL 或个股组合收益作为真值来源。
- **强基线**：必须比较 buy-and-hold、固定仓位、均线择时、trend-only、trend+breadth 和当前 champion。
- **样本外优先**：候选公式通过 walk-forward 训练/验证选择；没有有效验证窗口时只能输出 `insufficient_data`。
- **同标准诊断**：当前 champion 也进入候选池并接受 gate 诊断，`keep_champion` 不再被解释为“当前公式天然最优”。
- **V3 最优选择**：报告同时输出 `best_unconstrained_id` 和 `best_validated_id`；最终建议只来自通过验证门槛的最优公式。
- **反过拟合门槛**：拒绝永久防守、永久进攻、单一 regime 占比过高、输给简单基线或只在样本内好看的候选；换手采用相对 champion 的约束，避免 champion 自己被绝对阈值豁免。

报告写入 `reports/regime_profit_training/`，`recommended_profit_config.yaml` 仍然只是人工审查建议，第一阶段不自动替换生产公式。

### 2.6 策略研究治理 (research/strategy_governance.py)

四个内置策略的默认分层：

| 策略 | 层级 | 主要用途 |
|------|------|----------|
| buffett | quality_filter | 过滤财务质量和估值陷阱 |
| multifactor | primary_alpha | 主 Alpha 打分和横截面排序 |
| ml_lgbm | auxiliary_alpha | 辅助 Alpha 和非线性关系捕捉 |
| cybernetic | risk_overlay | 市场状态、仓位、风险预算和资产配置 |

晋级到 paper / production 前需要通过 `evaluate_promotion()` 门槛：OOS 月数、交易次数、Sharpe、最大回撤、换手、IC、ICIR。ML 当前默认为 `paper` 状态，除非 OOS 和 IC 证据达标，否则不标记 production。

### 2.7 因子 DSL (expression.py + dsl_parser.py)

**表达式引擎：** 声明式因子定义，支持组合模式。

```python
# 示例: 20日动量因子
Mom20 = Delta(Close(), 20) / Close()

# 示例: RSI
RSI14 = SMA(Max(Delta(Close(), 1), 0), 14) / SMA(Abs(Delta(Close(), 1)), 14) * 100
```

**运算符支持：** `+`, `-`, `*`, `/`, `**`, `>`, `<`, `>=`, `<=`, `==`, `!=`, `&`, `|`

**内置因子：** `Close`, `Open`, `High`, `Low`, `Volume`, `SMA(expr, window)`, `EMA(expr, window)`, `Delta(expr, window)`, `Max(expr, window)`, `Min(expr, window)`, `Rank(expr, window)`, `Std(expr, window)`, `Corr(expr1, expr2, window)`, `TsRank(expr, window)`, `Delay(expr, d)`

**LLM 因子发现：** `dsl_parser.py` 解析 LLM 生成的公式文本 → 计算因子值 → IC 检验 → 报告结果。`scripts/factor_hypothesis.py` 批量运行因子假设检验。

### 2.8 因子研究诊断 (signals/factor_research.py)

因子上线前至少检查：

- `rank_ic_by_period()`：按期横截面 Spearman IC。
- `factor_diagnostics()`：mean IC、ICIR、正 IC 占比、分组收益 spread、单调性。
- `factor_correlation_clusters()`：识别高度相关因子，避免重复暴露。

### 2.9 横截面排名 (selection.py)

**输入：** 各策略的原始评分 DataFrame（symbol × score）
**输出：** 交易信号 `{symbol, strategy, signal (buy/sell/hold), score, rank}`

**规则：**
- Top-N 排名 → buy（N 按策略配置）
- 跌出 Top-N → sell
- 在 Top-N 内但已在持仓 → hold
- 停牌/ST 股票自动过滤

## 3. 数据流

```
Market Data (DataHub)
       │
       ▼
┌──────────────────┐
│  策略评分计算      │
│  buffett / multi  │
│  factor / ml      │
└──────┬───────────┘
       │ raw scores
       ▼
┌──────────────────┐
│  selection.py     │
│  横截面排名        │
│  buy/sell/hold    │
└──────┬───────────┘
       │ signals
       ▼
  data/store/signals/{strategy}.parquet
       │
       ├──→ backtest/run_all_strategies.py
       └──→ broker/PaperBroker (模拟执行)
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 巴菲特作为约束层 | 不是独立信号，叠加在多因子/ML 之上 | 价值原则是硬约束；技术面/量化是执行手段 |
| 金融板块特殊处理 | 护城河指标差异（毛利率→净利率） | 银行/保险的高杠杆天然导致毛利率失效 |
| Regime 用月度 K 线 | 月线判断，避免日频噪声 | 日线太多假突破，月线更稳定 |
| ML 月度重训 | 每周六 Cron 自动重训 | 市场风格漂移（regime shift）需要模型跟进 |
| 因子 DSL | 自研表达式引擎 | Backtrader 不支持声明式因子组合 |

## 5. 接口合约

### 策略评分接口

```python
# 所有策略遵循统一接口
def compute_signals(pool: list[str], date: str) -> pd.DataFrame:
    """返回 DataFrame: symbol, score, signal, details"""
    ...

# 巴菲特
from signals.buffett import BuffettFilter
bf = BuffettFilter()
result: BuffettScore = bf.evaluate(symbol, financials, price_data)

# 多因子
from signals.multifactor import MultiFactorScorer
scorer = MultiFactorScorer(regime="bull")
score = scorer.score(factors_dict)

# ML
from signals.ml_signals import generate_ml_signals
signals = generate_ml_signals(pool, date, model_name="lgbm_20260501")
```

### 因子 DSL 接口

```python
from signals.expression import Close, SMA, Delta, parse_formula

# 声明式
mom = Delta(Close(), 20) / Close()
val = mom.compute(df, idx=100)

# LLM 公式解析
from signals.dsl_parser import parse_and_compute
parse_and_compute("SMA(Delta(close, 1), 20)", df)
```

## 6. 错误处理

- **数据不足：** 评分返回 0 或 NaN，selection 阶段自动过滤
- **模型文件缺失：** `load_model()` 返回 None，上层回退到等权打分
- **因子公式非法：** `dsl_parser` 返回错误信息（不抛异常），含行号和期望 token
- **IC 检验样本不足：** 跳过该因子，记录 insufficient_data 日志

## 7. 测试策略

- **合约测试：** 每种策略的 `compute_signals()` 返回 DataFrame schema 不变（columns: symbol, score, signal）
- **公式测试：** RSI/MACD/MA 计算结果与 ta-lib 对比（误差 < 1e-6）
- **边界测试：** 空股票池、全 NaN 数据、单只股票排名
- **回归测试：** 固定日期+固定股票池，评分结果哈希不变

## 8. 已知限制 & 未来方向

- **DCF 模型简化：** 当前用简化 DCF（固定增长率），未来可用分析师一致预期
- **ML 特征有限：** 目前 ~50 维特征，可加入 NLP 情绪（新闻/研报）和另类数据
- **因子发现依赖 LLM：** IC 检验只能筛选，不能保证因子逻辑正确
- **未来：** 支持用户自定义策略插件（`strategy_plugins.py` 已预留接口）
