# Spec: 信号系统 (Signal System)

> 版本: 1.0 | 日期: 2026-05-21 | 关联: [[PRD.md]] [[01-data-pipeline.md]] [[03-backtest-engine.md]]

## 1. 概述

信号系统是量化策略的核心——从原始数据生成交易信号（买/卖/持有）。四种策略并行运行，每日输出信号到 `data/store/signals/{strategy}.parquet`，供回测引擎和执行层消费。

**设计原则：**
- **策略独立性** — 每种策略可独立运行、独立回测、独立对比（锦标赛模式）
- **可解释性** — 巴菲特策略输出自然语言判定理由，ML 策略输出特征重要性
- **因子复用** — DSL 表达式引擎使因子可声明式组合，LLM 可发现新因子

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
│ 三重过滤     │ │ 四维加权     │ │ LightGBM    │ │ 控制论自适应  │
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

**四维加权模型：**

| 维度 | 权重 | 因子 |
|------|------|------|
| 质量 (Quality) | 40% | 巴菲特综合评分 + 5Y ROE + ROE 趋势 |
| 估值 (Valuation) | 30% | 安全边际 + PE/PB 分位数 |
| 技术 (Technical) | 15% | 1M/3M 动量 + 波动率 |
| 市场 (Market) | 15% | 市值 + 换手率 + 资金流向 |

**regime 自适应：** 牛市中质量权重提高 10%，熊市中估值权重提高 10%，波动市中技术权重降低 5%。

**输出：** `MultiFactorScorer.score_components()` → `{quality, valuation, technical, market, total}`，每维度 0-100 分。

### 2.3 ML 信号 (ml_signals.py)

**模型：** LightGBM 二分类（未来 20 日收益 > 中位数 = 正样本）

**PIT 特征：** 每月从 `data/store/features/YYYY-MM.parquet` 读取特征切片，训练/预测严格使用该月之前的数据

**训练流程：**
1. `scripts/build_features.py` — 批量构建月度 PIT 特征切片
2. `scripts/tune_model.py` — Optuna 超参搜索，输出到 `data/models/`
3. `scripts/weekly_retrain.py` — Cron 周六自动重训

**模型注册表：** `models/__init__.py` → `list_models()` / `load_model(name)` / `model_metadata(name)`

### 2.4 控制论自适应 (cybernetics/orchestrator.py)

**核心理念：** 不预测市场方向，而是检测当前市场状态，据此调整策略参数。

**Regime 检测：**
- **Bull:** 价格 > MA5 > MA20 > MA60（月度 K 线判断，避免日频噪声）
- **Bear:** 价格 < MA5 < MA20 < MA60
- **Sideways:** 其他情况

**自适应参数调整：**
- Bull → 提高仓位上限、放宽止损
- Bear → 降低仓位、收紧止损、增加现金比例
- Sideways → 默认参数

**市场广度：** 计算全市场 > MA20 的股票比例，作为辅助指标。

### 2.5 因子 DSL (expression.py + dsl_parser.py)

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

### 2.6 横截面排名 (selection.py)

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
