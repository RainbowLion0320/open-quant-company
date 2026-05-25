# Market Regime Research Trainer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline champion/challenger training and promotion workflow for Market Regime so the production formula is evaluated and improved from historical evidence instead of fixed by intuition.

**Architecture:** Keep production regime calculation unchanged in the first implementation. Add a research-only trainer that replays historical features, builds forward labels, searches interpretable challenger policies, runs walk-forward validation, compares strategy impact, and writes reports under `reports/regime_training/`. A challenger only becomes a recommended config when it beats the current champion across prediction quality, risk detection, stability, strategy A/B, and complexity gates.

**Tech Stack:** Python, pandas, numpy, existing `cybernetics.regime_scoring`, existing market data access helpers, pytest, Markdown/YAML/CSV/Parquet reports.

---

## Scope

This is a night-run, low-token goal. The local process may run for hours, but the agent should not continuously inspect logs. It should start the job, let it write structured reports, then inspect only the summary files and the last log lines.

First implementation must not auto-replace `cybernetics/regime_scoring.py` or `config/settings.yaml`. It may generate `recommended_config.yaml` and a clear promotion recommendation.

## Current Champion

Current production scoring is documented by `cybernetics/regime_scoring.py`:

```text
score = 35% trend_raw + 35% breadth_raw + 20% risk_raw + 10% volume_raw

bull if:
  score >= 65
  trend_raw >= 0.55
  advance_ratio >= 0.55

bear if:
  score <= 35
  or trend_raw <= 0.40 and breadth_raw <= 0.40

otherwise:
  sideways
```

The trainer treats this as `champion_current_formula`.

## Target Files

- Create: `research/regime_training.py`
  - Owns feature replay contracts, forward label construction, challenger policy evaluation, walk-forward splits, ranking, and report payloads.
- Create: `scripts/train_market_regime.py`
  - CLI entrypoint for night runs. It loads historical data, calls `research.regime_training`, and writes reports.
- Create: `tests/test_regime_training.py`
  - Contract tests for no-lookahead labels, candidate policy behavior, walk-forward split ordering, ranking gates, and report schema.
- Modify: `docs/specs/02-signal-system.md`
  - Document that Market Regime has a research trainer and champion/challenger promotion flow.
- Modify: `docs/strategies/cybernetic.md`
  - Document how to interpret `reports/regime_training/` output and why production formula is not replaced automatically.
- Modify: `docs/acceptance-matrix.md`
  - Add an acceptance row for regime research training.

Generated runtime artifacts are not committed:

```text
reports/regime_training/YYYYMMDD-HHMM/
  summary.json
  champion_vs_challenger.md
  regime_feature_history.parquet
  regime_label_history.parquet
  candidate_search.csv
  walk_forward_results.csv
  component_ablation.csv
  strategy_ab_test.csv
  stability_stats.csv
  event_study.csv
  recommended_config.yaml
  run.log
```

## Success Criteria

- The current champion is fully evaluated, not merely reprinted.
- At least `trend_only`, `trend_breadth`, and weighted four-component challenger policies are compared.
- Walk-forward validation is used; random train/test splits are not used.
- Forward labels are built strictly from future returns after the feature date and are never joined back into feature generation.
- Candidate ranking penalizes unstable regime flipping and unnecessary complexity.
- Strategy A/B includes at least:
  - `no_regime_fixed_allocation`
  - `champion_current_formula`
  - `trend_only_baseline`
  - `trend_breadth_baseline`
  - `best_challenger`
- The final summary says one of:
  - `keep_champion`
  - `recommend_challenger_for_review`
  - `insufficient_data`
- Production formula is unchanged unless a separate user-approved implementation step applies the recommended config.

## Night Run Command

Use this shape for the long run:

```bash
RUN_DIR="reports/regime_training/$(date +%Y%m%d-%H%M)"
mkdir -p "$RUN_DIR"
PYTHONPATH=. .venv/bin/python scripts/train_market_regime.py \
  --start 2016-01-01 \
  --end auto \
  --max-candidates 500 \
  --output "$RUN_DIR" \
  --no-apply \
  > "$RUN_DIR/run.log" 2>&1
```

After the run, inspect only:

```bash
cat "$RUN_DIR/summary.json"
sed -n '1,220p' "$RUN_DIR/champion_vs_challenger.md"
head -n 21 "$RUN_DIR/candidate_search.csv"
head -n 21 "$RUN_DIR/walk_forward_results.csv"
head -n 21 "$RUN_DIR/strategy_ab_test.csv"
tail -n 100 "$RUN_DIR/run.log"
```

## Task 1: Research Contracts And Failing Tests

**Files:**
- Create: `tests/test_regime_training.py`
- Create: `research/regime_training.py`

- [ ] **Step 1: Add tests for policy contracts**

Create `tests/test_regime_training.py` with tests covering:

```python
import pandas as pd


def test_forward_labels_use_future_rows_only():
    from research.regime_training import build_forward_labels

    dates = pd.date_range("2026-01-01", periods=8, freq="D")
    close = pd.Series([100, 101, 102, 99, 98, 103, 106, 104], index=dates, name="close")

    labels = build_forward_labels(close, horizons=(2,))

    assert labels.loc[dates[0], "future_2d_return"] == 0.02
    assert labels.loc[dates[0], "future_2d_max_drawdown"] == 0.0
    assert labels.loc[dates[2], "future_2d_return"] == (98 / 102 - 1)
    assert pd.isna(labels.loc[dates[-1], "future_2d_return"])


def test_candidate_policy_classifies_with_hysteresis_and_min_dwell():
    from research.regime_training import RegimePolicy, apply_policy

    features = pd.DataFrame(
        {
            "trend_raw": [0.70, 0.69, 0.52, 0.68, 0.30, 0.28],
            "breadth_raw": [0.70, 0.68, 0.51, 0.66, 0.30, 0.28],
            "risk_raw": [0.80, 0.75, 0.50, 0.70, 0.20, 0.20],
            "volume_raw": [0.55, 0.55, 0.50, 0.55, 0.30, 0.30],
            "advance_ratio": [0.60, 0.59, 0.50, 0.58, 0.35, 0.34],
        },
        index=pd.date_range("2026-01-01", periods=6, freq="D"),
    )
    policy = RegimePolicy(
        candidate_id="test",
        weights={"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10},
        bull_threshold=65,
        bear_threshold=35,
        trend_confirm=0.55,
        breadth_confirm=0.55,
        bear_trend_breakdown=0.40,
        bear_breadth_breakdown=0.40,
        min_dwell=2,
    )

    result = apply_policy(features, policy)

    assert list(result["regime"]) == ["bull", "bull", "bull", "bull", "bear", "bear"]
    assert result["score"].iloc[0] > 65


def test_walk_forward_splits_are_time_ordered():
    from research.regime_training import walk_forward_splits

    dates = pd.date_range("2018-01-31", "2023-12-31", freq="ME")
    splits = list(walk_forward_splits(dates, train_years=3, validate_years=1))

    assert splits
    for train_idx, validate_idx in splits:
        assert max(train_idx) < min(validate_idx)
        assert len(validate_idx) >= 10


def test_challenger_must_clear_promotion_gates():
    from research.regime_training import PromotionGateResult, decide_promotion

    result = decide_promotion(
        champion_score=70.0,
        challenger_score=73.0,
        challenger_maxdd_delta=0.0,
        challenger_turnover_delta=0.03,
        beats_baselines=True,
        valid_year_win_rate=0.70,
    )

    assert result == PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_training.py -q
```

Expected: fail because `research.regime_training` does not exist yet.

## Task 2: Core Regime Training Module

**Files:**
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_training.py`

- [ ] **Step 1: Implement core dataclasses and no-lookahead labels**

Implement:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

import numpy as np
import pandas as pd


class PromotionGateResult(StrEnum):
    KEEP_CHAMPION = "keep_champion"
    RECOMMEND_CHALLENGER_FOR_REVIEW = "recommend_challenger_for_review"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class RegimePolicy:
    candidate_id: str
    weights: dict[str, float]
    bull_threshold: float = 65.0
    bear_threshold: float = 35.0
    trend_confirm: float = 0.55
    breadth_confirm: float = 0.55
    bear_trend_breakdown: float = 0.40
    bear_breadth_breakdown: float = 0.40
    min_dwell: int = 1
    smoothing_window: int = 1
    complexity: int = 1


def build_forward_labels(close: pd.Series, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    close = close.sort_index().astype(float)
    out = pd.DataFrame(index=close.index)
    for horizon in horizons:
        future = close.shift(-horizon)
        out[f"future_{horizon}d_return"] = future / close - 1.0
        drawdowns = []
        volatilities = []
        for pos in range(len(close)):
            window = close.iloc[pos + 1 : pos + horizon + 1]
            if len(window) < horizon:
                drawdowns.append(np.nan)
                volatilities.append(np.nan)
                continue
            start = close.iloc[pos]
            path = window / start - 1.0
            drawdowns.append(float(path.min()))
            volatilities.append(float(window.pct_change().dropna().std() * np.sqrt(252)))
        out[f"future_{horizon}d_max_drawdown"] = drawdowns
        out[f"future_{horizon}d_volatility"] = volatilities
    if "future_20d_max_drawdown" in out:
        out["bear_event_next_20d"] = out["future_20d_max_drawdown"] <= -0.08
    if "future_20d_return" in out:
        out["bull_continuation_next_20d"] = out["future_20d_return"] >= 0.03
    return out
```

- [ ] **Step 2: Implement policy application**

Implement `apply_policy(features, policy)`:

```python
def _smooth(series: pd.Series, window: int) -> pd.Series:
    if window <= 1:
        return series
    return series.rolling(window, min_periods=1).mean()


def apply_policy(features: pd.DataFrame, policy: RegimePolicy) -> pd.DataFrame:
    data = features.sort_index().copy()
    trend = _smooth(data["trend_raw"].astype(float), policy.smoothing_window)
    breadth = _smooth(data["breadth_raw"].astype(float), policy.smoothing_window)
    risk = _smooth(data["risk_raw"].astype(float), policy.smoothing_window)
    volume = _smooth(data["volume_raw"].astype(float), policy.smoothing_window)
    score = (
        trend * policy.weights.get("trend", 0.0)
        + breadth * policy.weights.get("breadth", 0.0)
        + risk * policy.weights.get("risk", 0.0)
        + volume * policy.weights.get("volume", 0.0)
    ) * 100.0

    raw = []
    for idx, value in score.items():
        row = data.loc[idx]
        if (
            value >= policy.bull_threshold
            and trend.loc[idx] >= policy.trend_confirm
            and row.get("advance_ratio", breadth.loc[idx]) >= policy.breadth_confirm
        ):
            raw.append("bull")
        elif (
            value <= policy.bear_threshold
            or (trend.loc[idx] <= policy.bear_trend_breakdown and breadth.loc[idx] <= policy.bear_breadth_breakdown)
        ):
            raw.append("bear")
        else:
            raw.append("sideways")

    regimes = _enforce_min_dwell(raw, policy.min_dwell)
    return pd.DataFrame({"score": score.round(2), "regime": regimes}, index=data.index)
```

Implement `_enforce_min_dwell()` so a new regime must persist for `min_dwell` observations before replacing the current regime.

- [ ] **Step 3: Run targeted tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_training.py -q
```

Expected: tests from Task 1 pass.

## Task 3: Candidate Search, Stability, And Ranking

**Files:**
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_training.py`

- [ ] **Step 1: Add candidate generation**

Implement deterministic candidate generation:

```python
def generate_candidate_policies(max_candidates: int = 500) -> list[RegimePolicy]:
    weight_sets = [
        {"trend": 1.0, "breadth": 0.0, "risk": 0.0, "volume": 0.0},
        {"trend": 0.55, "breadth": 0.45, "risk": 0.0, "volume": 0.0},
        {"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10},
        {"trend": 0.30, "breadth": 0.40, "risk": 0.20, "volume": 0.10},
        {"trend": 0.30, "breadth": 0.30, "risk": 0.30, "volume": 0.10},
    ]
    bull_thresholds = [60.0, 65.0, 70.0]
    bear_thresholds = [30.0, 35.0, 40.0]
    smoothing_windows = [1, 3, 5, 10]
    min_dwells = [1, 3, 5, 20]
    policies = []
    for weights in weight_sets:
        for bull in bull_thresholds:
            for bear in bear_thresholds:
                for smoothing in smoothing_windows:
                    for dwell in min_dwells:
                        candidate_id = f"w{len(policies):04d}"
                        policies.append(
                            RegimePolicy(
                                candidate_id=candidate_id,
                                weights=weights,
                                bull_threshold=bull,
                                bear_threshold=bear,
                                smoothing_window=smoothing,
                                min_dwell=dwell,
                                complexity=(1 if smoothing == 1 else 2) + (1 if dwell == 1 else 2),
                            )
                        )
                        if len(policies) >= max_candidates:
                            return policies
    return policies
```

- [ ] **Step 2: Add evaluation metrics**

Implement:

```python
def stability_stats(regimes: pd.Series) -> dict[str, float]:
    changes = regimes.ne(regimes.shift()).sum() - 1
    counts = regimes.value_counts(normalize=True)
    runs = regimes.groupby(regimes.ne(regimes.shift()).cumsum()).size()
    return {
        "turnovers": float(max(changes, 0)),
        "avg_dwell": float(runs.mean()) if len(runs) else 0.0,
        "bull_ratio": float(counts.get("bull", 0.0)),
        "bear_ratio": float(counts.get("bear", 0.0)),
        "sideways_ratio": float(counts.get("sideways", 0.0)),
    }
```

Add a candidate score that rewards:
- bull future return > sideways > bear
- bear future drawdown worse than non-bear and recognized earlier
- low excessive turnover
- broad yearly consistency
- lower complexity

- [ ] **Step 3: Add tests for ranking**

Add a test where a stable challenger beats a noisy challenger:

```python
def test_candidate_ranking_penalizes_excessive_flipping():
    from research.regime_training import rank_candidate_rows

    rows = [
        {"candidate_id": "stable", "predictive_score": 70, "strategy_score": 65, "turnovers": 8, "complexity": 2},
        {"candidate_id": "noisy", "predictive_score": 72, "strategy_score": 66, "turnovers": 80, "complexity": 4},
    ]

    ranked = rank_candidate_rows(rows)

    assert ranked[0]["candidate_id"] == "stable"
```

- [ ] **Step 4: Run targeted tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_training.py -q
```

Expected: pass.

## Task 4: Walk-Forward And Champion/Challenger Gates

**Files:**
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_training.py`

- [ ] **Step 1: Implement walk-forward splits**

Implement year-based rolling splits:

```python
def walk_forward_splits(index: pd.DatetimeIndex, train_years: int = 4, validate_years: int = 1):
    years = sorted(set(index.year))
    for start in range(0, len(years) - train_years - validate_years + 1):
        train = set(years[start : start + train_years])
        validate = set(years[start + train_years : start + train_years + validate_years])
        train_idx = index[index.year.isin(train)]
        validate_idx = index[index.year.isin(validate)]
        if len(train_idx) and len(validate_idx):
            yield train_idx, validate_idx
```

- [ ] **Step 2: Implement promotion decision**

Implement `decide_promotion()` with explicit gates:

```python
def decide_promotion(
    *,
    champion_score: float,
    challenger_score: float,
    challenger_maxdd_delta: float,
    challenger_turnover_delta: float,
    beats_baselines: bool,
    valid_year_win_rate: float,
) -> PromotionGateResult:
    if champion_score <= 0 or challenger_score <= 0:
        return PromotionGateResult.INSUFFICIENT_DATA
    if challenger_score < champion_score + 2.0:
        return PromotionGateResult.KEEP_CHAMPION
    if challenger_maxdd_delta < -0.02:
        return PromotionGateResult.KEEP_CHAMPION
    if challenger_turnover_delta > 0.20:
        return PromotionGateResult.KEEP_CHAMPION
    if valid_year_win_rate < 0.60:
        return PromotionGateResult.KEEP_CHAMPION
    if not beats_baselines:
        return PromotionGateResult.KEEP_CHAMPION
    return PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW
```

- [ ] **Step 3: Run tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_training.py -q
```

Expected: pass.

## Task 5: Night-Run CLI And Report Writer

**Files:**
- Create: `scripts/train_market_regime.py`
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_training.py`

- [ ] **Step 1: Add CLI arguments**

The script must accept:

```text
--start YYYY-MM-DD
--end YYYY-MM-DD|auto
--max-candidates INT
--output reports/regime_training/YYYYMMDD-HHMM
--no-apply
```

- [ ] **Step 2: Add report writer**

Implement `write_regime_training_report(output_dir, result)` that writes:

```text
summary.json
champion_vs_challenger.md
candidate_search.csv
walk_forward_results.csv
component_ablation.csv
strategy_ab_test.csv
stability_stats.csv
event_study.csv
recommended_config.yaml
```

`summary.json` must contain:

```json
{
  "status": "ok",
  "decision": "keep_champion",
  "champion_score": 0.0,
  "best_challenger_score": 0.0,
  "best_challenger_id": "",
  "report_files": [],
  "notes": []
}
```

The exact numeric values come from the run; the keys must always exist.

- [ ] **Step 3: Add smoke test for report schema**

Add:

```python
def test_report_summary_schema_is_stable(tmp_path):
    from research.regime_training import write_regime_training_report

    result = {
        "decision": "keep_champion",
        "champion_score": 50.0,
        "best_challenger_score": 51.0,
        "best_challenger_id": "w0001",
        "candidate_rows": [],
        "walk_forward_rows": [],
        "strategy_rows": [],
        "stability_rows": [],
        "notes": ["schema smoke"],
    }

    summary = write_regime_training_report(tmp_path, result)

    assert summary["decision"] == "keep_champion"
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "champion_vs_challenger.md").exists()
```

- [ ] **Step 4: Run targeted tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_training.py -q
```

Expected: pass.

## Task 6: Strategy A/B Hook

**Files:**
- Modify: `research/regime_training.py`
- Modify: `scripts/train_market_regime.py`
- Test: `tests/test_regime_training.py`

- [ ] **Step 1: Add minimal allocation A/B simulator**

Implement a lightweight benchmark simulator before integrating deep strategy backtests:

```text
no_regime_fixed_allocation:
  stock_exposure = 0.35

champion_current_formula / challenger:
  bull stock_exposure = 0.60
  sideways stock_exposure = 0.35
  bear stock_exposure = 0.10
```

Apply exposure to benchmark daily returns and compute:

```text
cagr
sharpe
max_drawdown
calmar
turnover_proxy
```

- [ ] **Step 2: Compare baselines**

The run must include these rows:

```text
no_regime_fixed_allocation
champion_current_formula
trend_only_baseline
trend_breadth_baseline
best_challenger
```

- [ ] **Step 3: Run tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_training.py -q
```

Expected: pass.

## Task 7: Documentation And Acceptance Matrix

**Files:**
- Modify: `docs/specs/02-signal-system.md`
- Modify: `docs/strategies/cybernetic.md`
- Modify: `docs/acceptance-matrix.md`

- [ ] **Step 1: Update signal system spec**

Add a section named `Market Regime 离线训练与晋级` explaining:

```text
Market Regime uses a champion/challenger research loop.
Production formula remains deterministic and explainable.
Offline trainer searches interpretable alternatives.
Walk-forward and strategy A/B are required before replacement.
```

- [ ] **Step 2: Update cybernetic strategy doc**

Add an operator note:

```text
Run reports are stored under reports/regime_training/.
summary.json is the first file to inspect.
recommended_config.yaml is advisory only until manually applied.
```

- [ ] **Step 3: Update acceptance matrix**

Add one row:

```text
Market Regime 离线训练与晋级 | research/regime_training.py + scripts/train_market_regime.py | tests/test_regime_training.py | reports/regime_training summary | champion/challenger, walk-forward, A/B, no auto-apply | planned/OK after implementation
```

## Task 8: Verification And Commit

**Files:**
- All files changed by Tasks 1-7.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_training.py tests/test_regime_scoring.py tests/test_market_regime_v2.py -q
```

Expected: pass.

- [ ] **Step 2: Run full backend tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```

Expected: pass.

- [ ] **Step 3: Run a short smoke training job**

Run:

```bash
RUN_DIR="reports/regime_training/smoke-$(date +%Y%m%d-%H%M)"
mkdir -p "$RUN_DIR"
PYTHONPATH=. .venv/bin/python scripts/train_market_regime.py \
  --start 2022-01-01 \
  --end auto \
  --max-candidates 25 \
  --output "$RUN_DIR" \
  --no-apply \
  > "$RUN_DIR/run.log" 2>&1
cat "$RUN_DIR/summary.json"
```

Expected: `summary.json` exists and contains `decision`.

- [ ] **Step 4: Run diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files changed.

- [ ] **Step 5: Commit**

Run:

```bash
git add research/regime_training.py scripts/train_market_regime.py tests/test_regime_training.py docs/specs/02-signal-system.md docs/strategies/cybernetic.md docs/acceptance-matrix.md
git commit -m "codex: add market regime research trainer"
```

Expected: commit succeeds.

## First Night Operating Rules

- Do not inspect logs continuously.
- Do not apply `recommended_config.yaml` automatically.
- If the long run fails, inspect only `run.log` last 100 lines and classify the failure.
- If data is insufficient, return `insufficient_data` and write which dataset is missing.
- If the best challenger beats champion by only one metric but worsens drawdown, keep champion.
- If challenger is better but more complex, recommend review rather than auto-apply.

## Agent Handoff Prompt

Use this prompt to start the night goal:

```text
进入目标模式：执行 Market Regime Research Trainer。

请按 docs/plans/2026-05-25-market-regime-research-trainer.md 执行：
1. 构建 market regime 离线训练与晋级系统。
2. 当前公式作为 champion，自动搜索 challenger。
3. 做历史回放、未来标签、walk-forward、组件消融、策略 A/B。
4. 严格避免未来函数。
5. 夜间长跑不要持续分析日志，只写 reports/regime_training 下的报告。
6. 结束后读取 summary 和关键表，给我结论。
7. 第一晚默认不直接替换生产公式。
8. 补测试和文档，完成后提交 git，commit 前缀 codex。
```
