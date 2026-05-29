# Market Regime 系统终极改造计划：从规则评分到概率状态空间模型

> 目标：将现有基于线性加权评分的 regime 检测系统，改造为基于 Student-t HMM 的概率状态推断系统，同时保留全部下游工程资产（champion/challenger 框架、adaptive_params、allocator、信号集成）。

## 0. 核心设计决策

### 为什么选 Student-t HMM 而不是 GaussianHMM？

| 考量 | GaussianHMM | Student-t HMM | Bayesian HMM |
|------|-------------|---------------|--------------|
| 肥尾处理 | ❌ 假设高斯 | ✅ 自由度参数控制尾部 | ✅ 但实现复杂 |
| 计算速度 | 快 | 中等 | 慢（MCMC） |
| 状态数选择 | 手动 | 手动 | 自动 |
| 实现难度 | 低 | 中 | 高 |
| A股日频适配 | 差（收益肥尾） | 好 | 好但过慢 |

**决策：用 Student-t HMM 作为生产模型**。A 股日收益率显著肥尾（峰度 > 3），GaussianHMM 会低估极端事件概率。Student-t HMM 增加一个自由度参数 ν，当 ν→∞ 时退化为高斯。

### 为什么不完全替换？

HMM 有几个真实局限需要正视：
1. **马尔可夫假设**：假设明天只取决于今天，但市场有长记忆
2. **初始化敏感**：不同随机种子可能给出不同状态标签
3. **状态漂移**：训练集的"Bear"和验证集的"Bear"可能不是同一个东西

**解决方案：混合架构**——HMM 做状态推断，但保留规则评分作为 fallback 和可解释性锚点。

### 改造范围：什么变，什么不变

```
┌─ 变 ─────────────────────────────────────────────────┐
│  Layer 1: 特征工程                                     │
│    旧: 4维手写 (trend/breadth/risk/volume)            │
│    新: 12维增强特征 + 可选 Signature 特征              │
│                                                        │
│  Layer 2: 状态推断                                     │
│    旧: 线性加权 → 硬阈值 → 硬分类                      │
│    新: Student-t HMM → 概率向量 P(bull/bear/sideways)  │
│                                                        │
│  Layer 2.5: 状态平滑                                   │
│    旧: min_dwell 硬编码状态机                           │
│    新: HMM 转移矩阵自带平滑 + 可选 dwell overlay       │
├─ 不变 ────────────────────────────────────────────────┤
│  Layer 3: 决策引擎                                     │
│    adaptive_params() — 输入从硬 regime 变为概率加权     │
│    allocator — 同上                                    │
│                                                        │
│  Champion/Challenger 框架                              │
│    walk_forward_splits / decide_promotion              │
│    新增 HMM 作为候选类型                                │
│                                                        │
│  下游信号集成                                          │
│    scoring.py / ml_signals.py / multifactor.py         │
│    regime_gated.py / allocator.py                      │
│    接口兼容：regime 字符串保留，新增概率字段             │
│                                                        │
│  数据层                                                │
│    fetcher / datahub / feature_store                   │
│    全市场广度扫描（DuckDB）                             │
└────────────────────────────────────────────────────────┘
```

---

## 1. 新特征工程：从 4 维到 12 维

### 1.1 当前特征（保留但降权）

| 特征 | 来源 | 保留理由 |
|------|------|---------|
| `trend_raw` | MA20/60/120 对齐 + 动量 | 可解释性强 |
| `breadth_raw` | 全市场涨跌比 + MA 站上率 | A 股独有优势 |
| `risk_raw` | 波动率 + 回撤 | 基础风险度量 |
| `volume_raw` | 量比 + 涨跌量比 | 量价配合 |

### 1.2 新增特征（HMM 观测变量）

| 特征 | 计算方式 | 为什么需要 |
|------|---------|-----------|
| `return_1d` | 日收益率 | HMM 的基本输入 |
| `realized_vol_20d` | 20日收益率标准差 × √252 | 波动率聚类 |
| `skewness_20d` | 20日收益率偏度 | 捕捉下跌偏斜 |
| `kurtosis_20d` | 20日收益率峰度 | 肥尾程度 |
| `correlation_stock_bond` | 60日股债收益相关性 | 危机信号（股债同跌） |
| `drawdown_from_peak` | 当前价格 / 60日最高 - 1 | 回撤深度 |
| `volume_surprise` | (今日量 - 20日均量) / 20日标准差 | 异常放量 |
| `breadth_momentum` | breadth_raw 的 5日变化率 | 广度趋势 |

**设计原则**：所有特征都是 PIT（Point-in-Time）安全的，只用到当天及之前的数据。

### 1.3 特征标准化

HMM 对输入尺度敏感。每个特征在滚动窗口内做 z-score 标准化：

```python
def rolling_zscore(series: pd.Series, window: int = 252) -> pd.Series:
    mu = series.rolling(window, min_periods=60).mean()
    sigma = series.rolling(window, min_periods=60).std().replace(0, 1)
    return (series - mu) / sigma
```

使用 252 日（一年）滚动窗口，最少 60 日。

### 1.4 新模块：`cybernetics/features.py`

```python
@dataclass
class RegimeFeatureSet:
    """HMM 观测特征集"""
    date: str
    # 保留的原始 4 维（用于可解释性）
    trend_raw: float
    breadth_raw: float
    risk_raw: float
    volume_raw: float
    # HMM 观测向量（8 维，标准化后）
    obs_return_1d: float
    obs_realized_vol_20d: float
    obs_skewness_20d: float
    obs_kurtosis_20d: float
    obs_correlation_stock_bond: float
    obs_drawdown_from_peak: float
    obs_volume_surprise: float
    obs_breadth_momentum: float

def build_regime_features(
    index_frames: dict[str, pd.DataFrame],
    breadth: MarketBreadth,
    market_volume: MarketVolume,
    bond_returns: pd.Series | None = None,
) -> list[RegimeFeatureSet]:
    """从原始数据构建 12 维特征集"""
    ...

def build_observation_matrix(
    features: list[RegimeFeatureSet],
) -> np.ndarray:
    """提取 8 维 HMM 观测矩阵 (n_samples, 8)"""
    ...
```

---

## 2. Student-t HMM 状态推断引擎

### 2.1 模型定义

Student-t HMM 的发射分布：

```
p(x_t | z_t = k) = StudentT(x_t; μ_k, Σ_k, ν_k)
```

其中：
- `z_t ∈ {0, 1, 2}` 对应 {bull, sideways, bear}
- `μ_k` 是状态 k 的均值向量（8 维）
- `Σ_k` 是状态 k 的协方差矩阵
- `ν_k` 是状态 k 的自由度参数（控制尾部厚度）

### 2.2 实现方案

由于 `hmmlearn` 不原生支持 Student-t 发射，有两个选择：

**方案 A：用 `hmmlearn` 的 GaussianHMM + 特征预处理**
- 对肥尾特征做 winsorize（截尾到 1%/99% 分位数）
- 简单但损失了尾部信息

**方案 B：自实现 Student-t EM 算法**
- E-step：用 Student-t 密度计算后验
- M-step：更新 μ, Σ, ν, 转移矩阵
- 更准确，实现复杂度可控

**决策：方案 B，自实现。** 核心算法约 200 行，放在 `cybernetics/hmm_engine.py`。

### 2.3 新模块：`cybernetics/hmm_engine.py`

```python
@dataclass(frozen=True)
class HMMConfig:
    n_states: int = 3           # bull, sideways, bear
    max_iter: int = 100         # EM 最大迭代
    tol: float = 1e-4           # 收敛阈值
    n_init: int = 5             # 多次随机初始化取最优
    min_df: float = 3.0         # Student-t 最小自由度
    max_df: float = 30.0        # Student-t 最大自由度
    random_seed: int = 42       # 可复现

@dataclass
class HMMResult:
    """HMM 推断结果"""
    # 状态概率（核心输出）
    state_probs: np.ndarray     # (n_samples, 3) — [P(bull), P(sideways), P(bear)]
    # 最可能状态序列（Viterbi 解码）
    viterbi_states: np.ndarray  # (n_samples,) — 0/1/2
    # 模型参数
    means: np.ndarray           # (3, 8) — 各状态均值
    covars: np.ndarray          # (3, 8, 8) — 各状态协方差
    df: np.ndarray              # (3,) — 各状态自由度
    transmat: np.ndarray        # (3, 3) — 转移矩阵
    startprob: np.ndarray       # (3,) — 初始状态概率
    # 训练信息
    log_likelihood: float       # 对数似然
    n_iter: int                 # 实际迭代次数
    aic: float                  # AIC 信息准则
    bic: float                  # BIC 信息准则

class StudentTHMM:
    """Student-t 隐马尔可夫模型"""

    def __init__(self, config: HMMConfig = HMMConfig()):
        self.config = config

    def fit(self, X: np.ndarray) -> HMMResult:
        """EM 算法拟合模型。X: (n_samples, n_features)"""
        ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """前向-后向算法计算状态后验概率。返回 (n_samples, 3)"""
        ...

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Viterbi 解码最可能状态序列。返回 (n_samples,)"""
        ...

    def score(self, X: np.ndarray) -> float:
        """对数似然。用于模型选择"""
        ...

    def sample(self, n_samples: int) -> tuple[np.ndarray, np.ndarray]:
        """生成样本。用于诊断和可视化"""
        ...

def _student_t_logprob(x: np.ndarray, mu: np.ndarray, sigma: np.ndarray, df: float) -> np.ndarray:
    """Student-t 对数密度函数"""
    ...

def _em_step(X: np.ndarray, params: HMMParams) -> HMMParams:
    """单步 EM 更新"""
    ...
```

### 2.4 状态对齐

HMM 的状态标签是任意的（状态 0 不一定是 bull）。需要后处理对齐：

```python
def align_states(result: HMMResult, reference_features: np.ndarray) -> HMMResult:
    """
    用先验知识对齐状态标签：
    - 均值最高的状态 → bull
    - 均值最低的状态 → bear
    - 中间的 → sideways

    对齐维度：return_1d 和 realized_vol_20d 的组合作为锚点
    """
    ...
```

对齐策略：
1. 计算每个状态的 `return_1d` 均值
2. 按均值降序排列：最高 → bull，最低 → bear，中间 → sideways
3. 重新排列所有状态相关的数组

### 2.5 模型持久化

```python
def save_hmm_model(result: HMMResult, path: Path) -> None:
    """保存模型参数到 parquet + numpy"""
    ...

def load_hmm_model(path: Path) -> HMMResult:
    """加载模型参数"""
    ...
```

存储位置：`data/models/regime_hmm/`
- `params.npz` — means, covars, df, transmat, startprob
- `config.json` — HMMConfig
- `training_meta.json` — log_likelihood, aic, bic, n_iter, training_date

---

## 3. 改造 Orchestrator：混合推断

### 3.1 新 `detect()` 流程

```
1. 获取数据（不变）
   - 5 指数日线
   - 全市场广度
   - 全市场量能

2. 构建特征（新）
   - build_regime_features() → 12 维特征集
   - build_observation_matrix() → 8 维 HMM 输入

3. HMM 状态推断（新）
   - 加载已训练模型（如果存在）
   - predict_proba() → P(bull), P(sideways), P(bear)
   - align_states() → 对齐标签

4. 规则评分（保留，作为 fallback 和可解释性）
   - _compute_regime_score_v2() → 0-100 分数
   - classify_regime_value() → 硬分类

5. 混合决策（新）
   - 如果 HMM 模型可用：用 HMM 概率
   - 如果 HMM 模型不可用：退化到规则评分
   - 概率 → regime 字符串（argmax）+ 保留概率向量

6. 概率加权参数（新）
   - adaptive_params() 改为概率加权版本
   - P(bull)*bull_params + P(sideways)*sideways_params + P(bear)*bear_params

7. 输出 MarketContext（扩展）
   - regime: MarketRegime（保持兼容）
   - regime_probs: dict[str, float]（新增）
   - detection_method: str（新增："hmm" 或 "rule_based"）
   - hmm_state_details: dict（新增：各状态的特征贡献）
```

### 3.2 改造 `MarketContext`

```python
@dataclass
class MarketContext:
    # === 原有字段（保持兼容） ===
    regime: MarketRegime           # confirmed regime (argmax of probs)
    raw_regime: MarketRegime       # hmm raw state (before any smoothing)
    regime_score: float            # 0-100 composite score (规则评分保留)
    index_ma_trend: str
    volume_trend: str
    breadth: float
    breadth_detail: Dict[str, Any]
    score_components: Dict[str, Any]
    regime_state: Dict[str, Any]
    date: str

    # === 新增字段 ===
    regime_probs: Dict[str, float] = field(default_factory=dict)
    # {"bull": 0.65, "sideways": 0.25, "bear": 0.10}

    detection_method: str = "rule_based"
    # "hmm" | "rule_based" | "hybrid"

    hmm_confidence: float = 0.0
    # max(regime_probs) — 状态确定性

    hmm_entropy: float = 0.0
    # -sum(p * log(p)) — 状态不确定性
```

### 3.3 改造 `adaptive_params()`

```python
def adaptive_params(regime: MarketRegime, probs: dict[str, float] | None = None) -> dict[str, float]:
    """
    如果提供 probs，做概率加权：
      position_size = P(bull)*0.30 + P(sideways)*0.15 + P(bear)*0.05
    否则退化到原有的硬分类逻辑。
    """
    if probs and sum(probs.values()) > 0.99:
        return _probability_weighted_params(probs)
    return _hard_regime_params(regime)

def _probability_weighted_params(probs: dict[str, float]) -> dict[str, float]:
    PARAMS_BY_REGIME = {
        "bull": {"position_size": 0.30, "stop_loss": -0.08, "confidence_threshold": 0.60, "max_positions": 8},
        "sideways": {"position_size": 0.15, "stop_loss": -0.05, "confidence_threshold": 0.75, "max_positions": 5},
        "bear": {"position_size": 0.05, "stop_loss": -0.03, "confidence_threshold": 0.85, "max_positions": 2},
    }
    result = {}
    for key in PARAMS_BY_REGIME["bull"]:
        result[key] = sum(probs.get(r, 0) * PARAMS_BY_REGIME[r][key] for r in PARAMS_BY_REGIME)
    result["max_positions"] = round(result["max_positions"])
    return result
```

---

## 4. 训练框架扩展

### 4.1 HMM 训练管线

新增训练脚本：`scripts/train_regime_hmm.py`

```python
"""
HMM Regime Model Training Pipeline

流程：
1. 加载历史数据（指数日线 + 全市场广度）
2. 构建特征矩阵
3. Walk-forward 训练：
   - 用 4 年数据训练 HMM
   - 用 1 年数据验证状态质量
   - 滚动前进
4. 最终模型：用全量数据训练
5. 保存模型 + 诊断报告
"""
```

训练流程：
1. `build_regime_features()` 从历史数据构建特征
2. `build_observation_matrix()` 提取 8 维观测
3. `StudentTHMM(config).fit(X)` 拟合模型
4. 用 `predict_proba()` 得到每个交易日的状态概率
5. 评估状态质量：
   - **收益分离度**：bull 状态的 20 日平均收益 vs bear 状态
   - **风险分离度**：bear 状态的 20 日最大回撤 vs non-bear
   - **状态驻留**：平均驻留天数
   - **信息准则**：AIC / BIC
6. 与当前 Champion（规则评分）做 A/B 对比

### 4.2 Champion/Challenger 框架扩展

在 `research/regime_training.py` 中新增 HMM 候选类型：

```python
@dataclass(frozen=True)
class HMMCandidatePolicy:
    """HMM 候选策略"""
    candidate_id: str
    config: HMMConfig
    feature_columns: list[str]  # 使用哪些特征
    complexity: int = 2         # HMM 比规则更复杂

def generate_hmm_candidates() -> list[HMMCandidatePolicy]:
    """生成 HMM 候选变体"""
    candidates = []
    for n_states in [2, 3, 4]:
        for n_init in [3, 5, 10]:
            for features_subset in [
                ["return_1d", "realized_vol_20d"],                    # 最小子集
                ["return_1d", "realized_vol_20d", "skewness_20d", "kurtosis_20d"],  # 统计特征
                list(OBSERVATION_COLUMNS),                            # 全部 8 维
            ]:
                candidates.append(HMMCandidatePolicy(
                    candidate_id=f"hmm_{n_states}s_{n_init}i_{len(features_subset)}f",
                    config=HMMConfig(n_states=n_states, n_init=n_init),
                    feature_columns=features_subset,
                ))
    return candidates
```

评估函数扩展：

```python
def evaluate_hmm_candidate(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    close: pd.Series,
    candidate: HMMCandidatePolicy,
) -> dict[str, float | str]:
    """
    评估 HMM 候选：
    1. 提取候选指定的特征列
    2. Walk-forward 训练 HMM
    3. 用 predict_proba 得到状态概率
    4. 概率 → 硬分类（argmax）
    5. 和规则评分用同样的 evaluate_policy 指标
    """
    ...
```

### 4.3 Walk-Forward 验证

HMM 的 walk-forward 和规则评分不同——每个窗口需要重新训练模型：

```python
def walk_forward_hmm(
    features: pd.DataFrame,
    close: pd.Series,
    candidate: HMMCandidatePolicy,
) -> list[dict]:
    """
    HMM 专用 walk-forward：
    - 训练窗口：拟合 HMM
    - 验证窗口：用训练好的 HMM 做 predict_proba
    - 每个窗口的模型是独立的（不跨窗口复用）
    """
    rows = []
    for train_idx, validate_idx in walk_forward_splits(features.index):
        train_X = build_observation_matrix(features.loc[train_idx], candidate.feature_columns)
        validate_X = build_observation_matrix(features.loc[validate_idx], candidate.feature_columns)

        # 训练
        hmm = StudentTHMM(candidate.config)
        result = hmm.fit(train_X)

        # 验证
        probs = hmm.predict_proba(validate_X)
        regimes = hmm.predict(validate_X)

        # 评估
        ...
    return rows
```

---

## 5. 下游改造

### 5.1 接口兼容策略

**原则：所有下游消费者只需要改一行代码。**

当前：
```python
snapshot = QuantOrchestrator().detect()
regime = snapshot.regime.value  # "bull" | "sideways" | "bear"
```

改造后：
```python
snapshot = QuantOrchestrator().detect()
regime = snapshot.regime.value           # 不变
probs = snapshot.regime_probs            # 新增可用
# 如果想用概率加权：
params = adaptive_params(snapshot.regime, snapshot.regime_probs)
```

### 5.2 逐文件改造清单

| 文件 | 改造内容 | 工作量 |
|------|---------|--------|
| `cybernetics/orchestrator.py` | detect() 集成 HMM，MarketContext 扩展 | 大 |
| `cybernetics/features.py` | **新建**：特征构建 | 大 |
| `cybernetics/hmm_engine.py` | **新建**：Student-t HMM 实现 | 大 |
| `cybernetics/regime.py` | 不变 | 无 |
| `cybernetics/regime_policy.py` | 不变（规则评分保留） | 无 |
| `cybernetics/regime_scoring.py` | 不变 | 无 |
| `cybernetics/regime_state.py` | 可选：改为概率平滑 | 小 |
| `signals/scoring.py` | 可选：用 probs 做软分类 | 小 |
| `signals/ml_signals.py` | 可选：用 probs 加载多模型 | 小 |
| `signals/multifactor.py` | 不变（regime 字符串兼容） | 无 |
| `signals/candidates/regime_gated.py` | 可选：概率混合策略 | 中 |
| `broker/allocator.py` | 可选：概率加权资产配置 | 小 |
| `web/api/services/market.py` | 扩展 regime_payload 新增概率字段 | 小 |
| `research/regime_training.py` | 新增 HMM 候选类型 | 中 |
| `scripts/train_regime_hmm.py` | **新建**：HMM 训练脚本 | 中 |
| `config/settings.yaml` | 新增 hmm 配置节 | 小 |

### 5.3 `signals/candidates/regime_gated.py` 概率混合版本

当前是硬切换：
```python
if regime == "bull":
    candidates = blend(trend_following(0.55), rps(0.45))
elif regime == "bear":
    candidates = low_vol_defensive()
else:
    candidates = blend(quality_value(0.55), low_vol(0.45))
```

改造为概率混合：
```python
probs = snapshot.regime_probs
# 每个策略在不同 regime 下的权重
STRATEGY_WEIGHTS = {
    "bull": {"trend_following": 0.55, "rps": 0.45, "quality_value": 0, "low_vol": 0},
    "sideways": {"trend_following": 0, "rps": 0, "quality_value": 0.55, "low_vol": 0.45},
    "bear": {"trend_following": 0, "rps": 0, "quality_value": 0, "low_vol": 1.0},
}
# 概率加权
final_weights = {}
for strategy in all_strategies:
    final_weights[strategy] = sum(
        probs.get(regime, 0) * STRATEGY_WEIGHTS[regime].get(strategy, 0)
        for regime in STRATEGY_WEIGHTS
    )
```

---

## 6. 配置扩展

### 6.1 `settings.yaml` 新增

```yaml
cybernetics:
  regime_engine: hmm          # "hmm" | "rule_based" | "hybrid"
  hmm:
    n_states: 3
    max_iter: 100
    tol: 1e-4
    n_init: 5
    min_df: 3.0
    max_df: 30.0
    feature_window: 252       # 滚动标准化窗口
    min_training_samples: 504 # 最少训练样本（2年）
    model_path: data/models/regime_hmm/
    fallback_to_rules: true   # HMM 失败时退化到规则
    # 特征选择
    observation_columns:
      - return_1d
      - realized_vol_20d
      - skewness_20d
      - kurtosis_20d
      - correlation_stock_bond
      - drawdown_from_peak
      - volume_surprise
      - breadth_momentum
```

---

## 7. 实施阶段

### Phase 0：基础设施（1-2 天）

**目标**：安装依赖，创建新模块骨架，跑通最小可运行版本。

- [ ] 安装 `hmmlearn`（作为参考实现和 fallback）
- [ ] 创建 `cybernetics/features.py` — 特征构建
- [ ] 创建 `cybernetics/hmm_engine.py` — Student-t HMM 骨架
- [ ] 用现有 `build_regime_feature_history()` 的数据跑通特征构建
- [ ] 用 `hmmlearn.GaussianHMM` 跑通端到端流程（先用高斯验证流程）

**验收**：能用历史数据训练 HMM 并输出状态概率。

### Phase 1：Student-t HMM 实现（3-5 天）

**目标**：实现完整的 Student-t EM 算法。

- [ ] 实现 `_student_t_logprob()` — Student-t 对数密度
- [ ] 实现 `_em_step()` — 单步 EM（E-step + M-step）
- [ ] 实现 `StudentTHMM.fit()` — 完整 EM 循环 + 多次初始化
- [ ] 实现 `StudentTHMM.predict_proba()` — 前向-后向算法
- [ ] 实现 `StudentTHMM.predict()` — Viterbi 解码
- [ ] 实现 `align_states()` — 状态标签对齐
- [ ] 单元测试：对比 `hmmlearn.GaussianHMM` 输出（当 df→∞ 时应一致）

**验收**：Student-t HMM 在历史数据上训练成功，状态分离度 > GaussianHMM。

### Phase 2：集成 Orchestrator（2-3 天）

**目标**：HMM 接入生产检测流程。

- [ ] 改造 `QuantOrchestrator.detect()` — 集成 HMM 推断
- [ ] 扩展 `MarketContext` — 新增 `regime_probs`, `detection_method`, `hmm_confidence`, `hmm_entropy`
- [ ] 改造 `adaptive_params()` — 支持概率加权
- [ ] 实现 fallback 逻辑 — HMM 不可用时退化到规则评分
- [ ] 更新 `settings.yaml` — 新增 hmm 配置节
- [ ] 端到端测试：用真实数据跑通 detect() → MarketContext → 下游

**验收**：`QuantOrchestrator().detect()` 返回包含概率的 MarketContext。

### Phase 3：训练管线（2-3 天）

**目标**：HMM 模型的离线训练和验证。

- [ ] 创建 `scripts/train_regime_hmm.py` — 训练脚本
- [ ] 实现 walk-forward HMM 训练
- [ ] 实现 HMM vs 规则评分的 A/B 对比
- [ ] 集成到 champion/challenger 框架
- [ ] 生成诊断报告（状态概率时序图、转移矩阵、特征重要性）

**验收**：walk-forward 验证报告生成，HMM 与 Champion 的 OOS 对比清晰。

### Phase 4：下游适配（1-2 天）

**目标**：所有下游消费者兼容新接口。

- [ ] 更新 `web/api/services/market.py` — regime_payload 新增概率字段
- [ ] 更新 `web/api/routes/market.py` — API 响应包含概率
- [ ] 可选：更新 `signals/candidates/regime_gated.py` — 概率混合策略
- [ ] 可选：更新 `broker/allocator.py` — 概率加权资产配置
- [ ] 可选：更新 `signals/scoring.py` — 概率加权行业偏好

**验收**：前端 regime API 显示概率，cron 信号计算正常。

### Phase 5：优化和长期演进（持续）

- [ ] 特征消融实验：哪些特征对状态分离贡献最大
- [ ] 状态数自适应：用 BIC 自动选择 2/3/4 状态
- [ ] 跨资产特征：加入债券收益率、信用利差
- [ ] Signature 特征：路径签名作为 HMM 输入的增强
- [ ] 在线学习：增量更新 HMM 参数（不全量重训）

---

## 8. 风险和降级策略

| 风险 | 概率 | 影响 | 降级方案 |
|------|------|------|---------|
| Student-t EM 不收敛 | 中 | 检测失败 | 退化到 GaussianHMM（hmmlearn） |
| HMM 状态标签错乱 | 中 | 错误信号 | align_states() + 人工审核 |
| 训练数据不足（<2年） | 低 | 模型不稳定 | 退化到规则评分 |
| HMM 推断延迟过高 | 低 | Cron 超时 | 预计算 + 缓存 |
| 状态数选择错误 | 中 | 混合状态 | BIC 自动选择 + 多模型投票 |

**核心降级原则**：`config.regime_engine = "hybrid"` 时，HMM 和规则评分并行运行，如果 HMM 的 entropy > 阈值（不确定性太高），自动切换到规则评分。

---

## 9. 成功指标

| 指标 | 当前 Champion（规则） | HMM 目标 | 度量方式 |
|------|---------------------|---------|---------|
| Bull 20d 平均收益 | 待测 | > Champion | Walk-forward |
| Bear 20d 平均回撤 | 待测 | < Champion | Walk-forward |
| 收益分离度 (bull-bear) | 待测 | > Champion + 2% | evaluate_policy |
| 策略 Sharpe | 待测 | > Champion | simulate_regime_allocation |
| 状态切换频率 | 待测 | ≤ Champion | stability_stats |
| 状态概率熵 | N/A | < 0.5 (平均) | 自身指标 |

---

## 10. 依赖清单

需要安装的包：

```
hmmlearn>=0.3.0    # GaussianHMM 作为参考和 fallback
scipy>=1.10.0      # Student-t 分布（已有）
numpy>=1.24.0      # 矩阵运算（已有）
```

不需要安装：
- ~~PyTorch~~ — 不需要深度学习
- ~~arch~~ — GARCH 可以后续再加
- ~~gudhi/ripser~~ — TDA 可以后续再加

---

## 附录 A：Student-t EM 算法要点

### E-step

对每个样本 i 和状态 k，计算后验概率（responsibility）：

```
γ(i,k) = π_k * StudentT(x_i; μ_k, Σ_k, ν_k) / Σ_j π_j * StudentT(x_i; μ_j, Σ_j, ν_j)
```

Student-t 密度可以用 scipy.stats.multivariate_t 或自实现。

### M-step

```
μ_k = Σ_i γ(i,k) * w(i,k) * x_i / Σ_i γ(i,k) * w(i,k)
Σ_k = Σ_i γ(i,k) * w(i,k) * (x_i - μ_k)(x_i - μ_k)^T / Σ_i γ(i,k) * w(i,k)
```

其中 `w(i,k) = (ν_k + d) / (ν_k + δ(i,k))` 是权重，`δ(i,k) = (x_i - μ_k)^T Σ_k^{-1} (x_i - μ_k)` 是 Mahalanobis 距离。

自由度 ν 通过数值优化更新（没有闭式解）。

### 收敛判断

`|log_likelihood(t) - log_likelihood(t-1)| < tol`

## 附录 B：文件清单

新建文件：
```
cybernetics/features.py           # 特征构建
cybernetics/hmm_engine.py         # Student-t HMM 实现
scripts/train_regime_hmm.py       # HMM 训练脚本
tests/test_hmm_engine.py          # HMM 单元测试
tests/test_features.py            # 特征构建测试
```

修改文件：
```
cybernetics/orchestrator.py       # detect() 集成 HMM
cybernetics/__init__.py           # 导出新符号
config/settings.yaml              # 新增 hmm 配置
web/api/services/market.py        # regime_payload 扩展
research/regime_training.py       # HMM 候选类型（可选）
signals/candidates/regime_gated.py # 概率混合（可选）
broker/allocator.py               # 概率加权（可选）
```

不修改文件：
```
cybernetics/regime.py             # MarketRegime 枚举不变
cybernetics/regime_policy.py      # 规则评分参数保留
cybernetics/regime_scoring.py     # 规则评分逻辑保留
cybernetics/regime_state.py       # 可选保留作为 overlay
signals/scoring.py                # 接口兼容
signals/ml_signals.py             # 接口兼容
signals/multifactor.py            # 接口兼容
```
