# Market Regime Profit Trainer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train and validate a Market Regime formula whose direct purpose is to make money by controlling tradable market beta exposure, not merely describe market conditions or optimize around the current unfinished stock-picking strategies.

**Architecture:** Build on `research/regime_training.py` but change the objective function. The new trainer treats Market Regime as a global risk-on/risk-off timing signal over tradable assets: stock index exposure, defensive cash/bond/gold proxies when available, and fixed-allocation baselines. It trains interpretable formulas with walk-forward validation and only recommends production review when the candidate improves out-of-sample CAGR/Sharpe/Calmar while respecting drawdown, turnover, regime diversity, and anti-overfitting gates.

**Tech Stack:** Python, pandas, numpy, DuckDB/local parquet data, existing `research/regime_training.py`, existing `cybernetics.regime_scoring`, pytest, Markdown/YAML/CSV/Parquet reports.

---

## Why This Replaces The V1 Objective

The first trainer (`docs/plans/2026-05-25-market-regime-research-trainer.md`) created useful infrastructure:

- historical feature replay
- forward labels
- candidate policy search
- walk-forward comparison
- report generation

But its first objective was too much like a research harness. It could reward a candidate that mostly stayed defensive because the proxy A/B liked low drawdown. That is not enough.

This v2 plan changes the core question from:

```text
Can a regime formula look stable and reduce drawdown?
```

to:

```text
Can a regime formula decide when to hold more or less tradable risk exposure and improve long-term out-of-sample money-making metrics?
```

The system's purpose is to make money under controlled risk. Market Regime should therefore be evaluated as a global timing/risk-budget signal, independent of the current unfinished stock-selection strategies.

## Core Definition

Market Regime is a global risk exposure signal:

```text
risk_on    -> increase tradable equity/beta exposure
neutral    -> keep moderate exposure
risk_off   -> reduce equity/beta exposure and prefer cash/defensive assets
```

It is allowed to influence buying and selling. It should not answer "which stock should I buy", but it must answer:

```text
Should the system actively take market risk now?
How much market beta should the portfolio hold?
Should defensive assets or cash dominate?
```

## Non-Goals

- Do not optimize the formula against the current multifactor/Buffett/ML stock strategies. Those strategies are not mature enough to be the truth source.
- Do not accept a formula that wins only by being permanently defensive.
- Do not auto-apply a production formula in the first goal run.
- Do not use random train/test splits.
- Do not use future data in features.
- Do not make a black-box production model in v2. Interpretable rules may be trained; black-box models can be research baselines only.

## Target Files

- Modify: `research/regime_training.py`
  - Keep existing v1 APIs stable.
  - Add profit-oriented objective functions, tradable exposure simulation, anti-collapse gates, and richer baseline comparison.
- Create: `scripts/train_market_regime_profit.py`
  - CLI entrypoint for v2 profit-oriented night runs.
- Create: `tests/test_regime_profit_training.py`
  - Contract tests for profit objective, tradable exposure A/B, anti-permanent-defense gates, baseline rows, and report schema.
- Modify: `docs/specs/02-signal-system.md`
  - Clarify that Market Regime is a global risk-on/risk-off timing and risk-budget signal.
- Modify: `docs/strategies/cybernetic.md`
  - Add operator notes for profit-oriented regime reports.
- Modify: `docs/acceptance-matrix.md`
  - Add v2 acceptance row.

Generated runtime artifacts are not committed:

```text
reports/regime_profit_training/YYYYMMDD-HHMM/
  summary.json
  profit_champion_vs_challenger.md
  tradable_asset_panel.parquet
  regime_feature_history.parquet
  regime_label_history.parquet
  candidate_profit_search.csv
  walk_forward_profit_results.csv
  baseline_comparison.csv
  regime_exposure_ab_test.csv
  regime_distribution.csv
  event_study.csv
  recommended_profit_config.yaml
  run.log
```

## Tradable Universe

Use the best available local data, in this priority order:

### Risk-On Assets

- A-share broad index proxy: `sh000001` from local index cache.
- If locally available, add `sh000300`, `sh000905`, `sz399001`, `sz399006`.
- If ETF/fund daily data is available and clean, add broad ETFs as tradable proxies.

### Defensive Assets

- Cash return proxy: default 0 daily return.
- Bond proxy: local bond/treasury data if available; otherwise cash proxy.
- Gold proxy: local gold/commodity/futures data if available; otherwise omit and record `gold_unavailable`.

### Do Not Depend On

- Current stock-selection strategy signals.
- Paper broker PnL.
- Individual stock portfolio returns.

This keeps Market Regime independent from unfinished alpha modules.

## Labels And Objective

Build labels from tradable asset returns, not from current strategy returns.

Required labels:

```text
future_5d_equity_return
future_20d_equity_return
future_60d_equity_return
future_20d_equity_max_drawdown
future_60d_equity_max_drawdown
future_20d_equity_volatility
future_20d_cash_excess_return
future_20d_defensive_excess_return
risk_on_profitable_next_20d
risk_off_preferred_next_20d
```

The trainer should optimize for out-of-sample money-making metrics:

```text
primary:
  OOS Calmar
  OOS Sharpe
  OOS CAGR
  OOS max drawdown

secondary:
  turnover
  bull/risk_on participation
  risk_off usefulness
  year-by-year consistency
  complexity
```

## Exposure Policy

Each regime maps to tradable exposure:

```text
risk_on:
  equity_exposure = 0.80
  defensive_exposure = 0.20

neutral:
  equity_exposure = 0.40
  defensive_exposure = 0.60

risk_off:
  equity_exposure = 0.10
  defensive_exposure = 0.90
```

The trainer may search exposure levels, but first implementation should keep exposure mapping fixed so formula quality is not confused with allocation-level optimization.

## Candidate Formula Space

Train interpretable candidates only:

```text
score = w_trend * trend_raw
      + w_breadth * breadth_raw
      + w_risk * risk_raw
      + w_volume * volume_raw
      + optional w_cross_asset * cross_asset_raw
```

Search:

- weights
- risk_on threshold
- risk_off threshold
- trend confirmation
- breadth confirmation
- smoothing window
- min dwell
- hysteresis enter/exit thresholds

Do not make the production candidate a black-box model in this phase.

## Baselines

A candidate is not valuable unless it beats strong simple baselines.

Required baselines:

```text
buy_and_hold_equity
fixed_80_20
fixed_60_40
fixed_40_60
cash_only
ma_20_60_timing
ma_60_120_timing
trend_only_regime
trend_breadth_regime
current_champion_formula
```

## Promotion Gates

A challenger can only produce `recommend_challenger_for_review` if all gates pass:

```text
OOS Calmar > champion Calmar by meaningful margin
OOS Sharpe > champion Sharpe by meaningful margin
OOS CAGR not materially lower than champion
OOS MaxDD not worse than champion
beats buy_and_hold_equity on risk-adjusted basis
beats fixed_60_40 on risk-adjusted basis
beats simple MA timing baseline
walk-forward majority windows beat champion
turnover does not exceed configured ceiling
risk_on ratio is not collapsed below minimum
risk_off ratio is not collapsed above maximum
candidate is interpretable
production config remains advisory only
```

Default collapse gates:

```text
min_risk_on_ratio = 0.10
max_risk_off_ratio = 0.70
max_single_regime_ratio = 0.85
```

These gates specifically prevent "always defensive" formulas from being recommended.

## Task 1: Redefine Profit-Oriented Contracts

**Files:**
- Create: `tests/test_regime_profit_training.py`
- Modify: `research/regime_training.py`

- [ ] **Step 1: Add failing tests for profit objective**

Create tests that prove:

```text
build_profit_labels() creates future equity/cash/defensive excess labels without lookahead.
simulate_tradable_exposure() converts risk_on/neutral/risk_off into return series.
profit_score_candidate() rewards OOS Calmar/Sharpe/CAGR and penalizes turnover.
promotion gates reject permanent risk_off candidates.
baseline comparison includes all required baselines.
summary schema contains decision, best candidate, OOS metrics, and report files.
```

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_profit_training.py -q
```

Expected: fail before implementation.

## Task 2: Build Tradable Asset Panel

**Files:**
- Modify: `research/regime_training.py`
- Create or modify: `scripts/train_market_regime_profit.py`
- Test: `tests/test_regime_profit_training.py`

- [ ] **Step 1: Implement asset panel loader**

Add a function with this behavior:

```text
load_tradable_asset_panel(start, end)
```

It returns:

```text
date index
equity_close
equity_return
cash_return
defensive_return
asset_sources
```

Rules:

- Prefer local index cache for broad equity proxy.
- Use cash return = 0 if bond/gold data is unavailable.
- If defensive data is missing, record this in `notes`; do not fail the run.
- Do not fetch network data implicitly.

- [ ] **Step 2: Add tests**

Tests should use synthetic price series and verify:

```text
returns align to dates
cash fallback works
missing defensive assets do not crash
network fetch is not required
```

## Task 3: Profit Labels

**Files:**
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_profit_training.py`

- [ ] **Step 1: Implement labels**

Add:

```text
build_profit_labels(asset_panel, horizons=(5, 20, 60))
```

It must compute:

```text
future equity returns
future equity drawdowns
future equity volatility
future equity excess over cash
future equity excess over defensive
risk_on_profitable_next_20d
risk_off_preferred_next_20d
```

- [ ] **Step 2: No-lookahead test**

Use a synthetic series where row `t` has known `t+20` result and verify labels use only rows after `t`.

## Task 4: Profit-Oriented Candidate Scoring

**Files:**
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_profit_training.py`

- [ ] **Step 1: Implement tradable exposure simulator**

Add:

```text
simulate_tradable_exposure(asset_panel, regime_series, exposure_map)
```

It should output:

```text
daily_return
equity_curve
cagr
sharpe
max_drawdown
calmar
turnover_proxy
risk_on_ratio
neutral_ratio
risk_off_ratio
```

- [ ] **Step 2: Implement profit score**

Add:

```text
profit_score_candidate(metrics, baselines, regime_distribution)
```

The score should primarily reward:

```text
Calmar
Sharpe
CAGR
MaxDD control
beating baselines
```

And penalize:

```text
turnover
permanent defense
permanent risk-on
excess complexity
```

## Task 5: Strong Baselines

**Files:**
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_profit_training.py`

- [ ] **Step 1: Implement baseline policies**

The report must include:

```text
buy_and_hold_equity
fixed_80_20
fixed_60_40
fixed_40_60
cash_only
ma_20_60_timing
ma_60_120_timing
trend_only_regime
trend_breadth_regime
current_champion_formula
best_challenger
```

- [ ] **Step 2: Add baseline test**

Verify all rows exist in `baseline_comparison.csv` and `regime_exposure_ab_test.csv`.

## Task 6: Walk-Forward Profit Training

**Files:**
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_profit_training.py`

- [ ] **Step 1: Implement walk-forward selection**

For each window:

```text
train on past years
select best candidate by profit objective on train
evaluate selected candidate on next validation year
compare against champion and baselines
record winner
```

- [ ] **Step 2: Enforce OOS-first recommendation**

Recommendation must use validation windows, not full-sample ranking.

If no valid walk-forward windows exist, decision must be:

```text
insufficient_data
```

## Task 7: Anti-Overfitting And Anti-Collapse Gates

**Files:**
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_profit_training.py`

- [ ] **Step 1: Add hard gates**

Implement:

```text
min_risk_on_ratio = 0.10
max_risk_off_ratio = 0.70
max_single_regime_ratio = 0.85
max_turnover_proxy
min_validation_win_rate
min_baseline_beats
```

- [ ] **Step 2: Add tests**

Verify:

```text
always risk_off is rejected
always risk_on is rejected
single-year overfit is rejected
candidate that loses to MA baseline is rejected
```

## Task 8: CLI And Reports

**Files:**
- Create: `scripts/train_market_regime_profit.py`
- Modify: `research/regime_training.py`
- Test: `tests/test_regime_profit_training.py`

- [ ] **Step 1: Add CLI**

CLI:

```bash
PYTHONPATH=. .venv/bin/python scripts/train_market_regime_profit.py \
  --start 2016-01-01 \
  --end auto \
  --max-candidates 1000 \
  --output reports/regime_profit_training/YYYYMMDD-HHMM \
  --no-apply
```

- [ ] **Step 2: Write reports**

Required files:

```text
summary.json
profit_champion_vs_challenger.md
tradable_asset_panel.parquet
regime_feature_history.parquet
regime_label_history.parquet
candidate_profit_search.csv
walk_forward_profit_results.csv
baseline_comparison.csv
regime_exposure_ab_test.csv
regime_distribution.csv
event_study.csv
recommended_profit_config.yaml
run.log
```

## Task 9: Documentation

**Files:**
- Modify: `docs/specs/02-signal-system.md`
- Modify: `docs/strategies/cybernetic.md`
- Modify: `docs/acceptance-matrix.md`

- [ ] **Step 1: Update spec**

Document:

```text
Market Regime is a global tradable risk-on/risk-off signal.
Its direct validation target is OOS tradable risk exposure performance.
Current stock strategies are not used as the truth source.
```

- [ ] **Step 2: Update cybernetic doc**

Document:

```text
reports/regime_profit_training/ is the profit-oriented report directory.
recommended_profit_config.yaml is advisory only.
Production formula is not replaced automatically.
```

- [ ] **Step 3: Update acceptance matrix**

Add a row for:

```text
Market Regime profit-oriented trainer
```

## Task 10: Verification And Commit

**Files:**
- All changed files.

- [ ] **Step 1: Run targeted tests**

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_regime_profit_training.py tests/test_regime_training.py tests/test_regime_scoring.py tests/test_market_regime_v2.py -q
```

- [ ] **Step 2: Run full backend tests**

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```

- [ ] **Step 3: Run short smoke job**

```bash
RUN_DIR="reports/regime_profit_training/smoke-$(date +%Y%m%d-%H%M)"
mkdir -p "$RUN_DIR"
PYTHONPATH=. .venv/bin/python scripts/train_market_regime_profit.py \
  --start 2022-01-01 \
  --end auto \
  --max-candidates 50 \
  --output "$RUN_DIR" \
  --no-apply \
  > "$RUN_DIR/run.log" 2>&1
cat "$RUN_DIR/summary.json"
```

- [ ] **Step 4: Run full night job**

```bash
RUN_DIR="reports/regime_profit_training/$(date +%Y%m%d-%H%M)"
mkdir -p "$RUN_DIR"
PYTHONPATH=. .venv/bin/python scripts/train_market_regime_profit.py \
  --start 2016-01-01 \
  --end auto \
  --max-candidates 1000 \
  --output "$RUN_DIR" \
  --no-apply \
  > "$RUN_DIR/run.log" 2>&1
```

After completion, inspect only:

```bash
cat "$RUN_DIR/summary.json"
sed -n '1,220p' "$RUN_DIR/profit_champion_vs_challenger.md"
head -n 21 "$RUN_DIR/candidate_profit_search.csv"
head -n 21 "$RUN_DIR/walk_forward_profit_results.csv"
head -n 21 "$RUN_DIR/baseline_comparison.csv"
tail -n 100 "$RUN_DIR/run.log"
```

- [ ] **Step 5: Diff checks**

```bash
git diff --check
git status --short
```

- [ ] **Step 6: Commit**

```bash
git add research/regime_training.py scripts/train_market_regime_profit.py tests/test_regime_profit_training.py docs/specs/02-signal-system.md docs/strategies/cybernetic.md docs/acceptance-matrix.md
git commit -m "codex: add profit-oriented regime trainer"
```

## Expected Interpretation

Possible final decisions:

```text
keep_champion
recommend_challenger_for_review
insufficient_data
```

`recommend_challenger_for_review` means:

```text
The candidate improved tradable risk exposure results out-of-sample and passed anti-overfitting gates.
It is not automatically applied.
```

It does not mean:

```text
The system has found a permanent best formula.
```

## Agent Handoff Prompt

Use this prompt for the next goal run:

```text
进入目标模式：执行 Market Regime Profit Trainer。

请按 docs/plans/2026-05-26-market-regime-profit-trainer.md 执行：
1. 把 Market Regime 作为全局 risk-on/risk-off 挣钱信号训练，不要依赖当前未成熟选股策略。
2. 用可交易资产/指数/现金或防御资产代理做收益、回撤、Calmar、Sharpe、CAGR 的样本外评估。
3. 当前公式作为 champion，候选公式作为 challenger。
4. 必须包含 buy-and-hold、固定仓位、均线择时、trend-only、trend+breadth、当前公式等强 baseline。
5. 严格避免未来函数和随机切分，使用 walk-forward。
6. 拦截永久防守、永久进攻、单一年份过拟合、输给简单 baseline 的候选。
7. 第一晚默认不直接替换生产公式，只生成 reports/regime_profit_training/ 下的报告和 recommended_profit_config.yaml。
8. 补测试和文档，跑定向/全量/烟测/完整跑批，完成后提交 git，commit 前缀 codex。
```
