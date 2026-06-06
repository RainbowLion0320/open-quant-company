# As-Of PIT Feature View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade ML feature usage from month-only PIT slices to as-of-date PIT views so daily/fast-moving features can update at daily granularity while low-frequency features remain PIT-safe.

**Architecture:** Keep existing monthly files readable for compatibility, but add date-keyed feature slices with explicit `as_of_date` and `feature_month`. `data.feature_store` becomes the single resolver: latest feature <= as_of date, load panel with normalized columns, and training split keys based on `as_of_date` when present. ML backtest and production signal paths use the resolver instead of directly assuming a month stem.

**Tech Stack:** Python, pandas, Parquet via DataHub, LightGBM runtime wrappers, pytest.

---

### Task 1: Feature Store Date Resolver

**Files:**
- Modify: `data/feature_store.py`
- Test: `tests/test_asof_pit_feature_view.py`

- [ ] **Step 1: Write failing tests**

```python
def test_feature_store_selects_latest_slice_on_or_before_as_of(tmp_path):
    from data.feature_store import latest_feature_file, write_feature_slice
    write_feature_slice(pd.DataFrame({"symbol": ["000001"], "as_of_date": ["2026-05-07"]}), "2026-05-07", directory=tmp_path)
    write_feature_slice(pd.DataFrame({"symbol": ["000001"], "as_of_date": ["2026-05-10"]}), "2026-05-10", directory=tmp_path)
    assert latest_feature_file(tmp_path, as_of="2026-05-08").name == "2026-05-07.parquet"
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_asof_pit_feature_view.py::test_feature_store_selects_latest_slice_on_or_before_as_of -q`
Expected: fail because `as_of` and `write_feature_slice` do not exist.

- [ ] **Step 3: Implement minimal resolver**

Add `feature_key_to_date()`, `write_feature_slice()`, `latest_feature_file(..., as_of=None)`, and normalize `as_of_date` in `_read_feature_file()`.

- [ ] **Step 4: Run green test**

Run: `.venv/bin/python -m pytest tests/test_asof_pit_feature_view.py -q`
Expected: pass.

### Task 2: As-Of Builder

**Files:**
- Modify: `scripts/build_features.py`
- Modify: `data/feature_store.py`
- Test: `tests/test_asof_pit_feature_view.py`

- [ ] **Step 1: Write failing tests**

```python
def test_build_asof_uses_exact_daily_price_not_month_end(monkeypatch, tmp_path):
    # price rows include 2026-05-08 and 2026-05-29; as_of=2026-05-08 must not use 2026-05-29.
    rows = build_asof("2026-05-08", ...)
    assert rows.loc[0, "as_of_date"] == "2026-05-08"
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_asof_pit_feature_view.py -q`
Expected: fail because `_build_asof` does not exist.

- [ ] **Step 3: Implement builder**

Extract common feature-row computation from `_build_month()` to `_build_asof(as_of_date, ...)`, write date-keyed slice, keep `_build_month()` as a wrapper using month-end for compatibility.

- [ ] **Step 4: Run green test**

Run: `.venv/bin/python -m pytest tests/test_asof_pit_feature_view.py -q`
Expected: pass.

### Task 3: ML Runtime Uses As-Of Date

**Files:**
- Modify: `backtest/strategies/ml_strategy.py`
- Modify: `signals/ml_signals.py`
- Test: `tests/test_ml_lgbm_closure.py`

- [ ] **Step 1: Write failing tests**

```python
def test_ml_strategy_prefers_asof_slice_over_prior_month():
    # two feature rows in the same month with different as_of_date;
    # backtest date 2026-05-10 must use 2026-05-08, not 2026-04.
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_ml_lgbm_closure.py::test_ml_strategy_prefers_asof_slice_over_prior_month -q`
Expected: fail because MLStrategy only indexes by `month`.

- [ ] **Step 3: Implement runtime path**

Normalize feature panels to include `as_of_date`, cache score maps by `(as_of_date, regime_key)`, choose latest feature date <= current trading date, and keep monthly files as fallback.

- [ ] **Step 4: Run green test**

Run: `.venv/bin/python -m pytest tests/test_ml_lgbm_closure.py -q`
Expected: pass.

### Task 4: Training Split Compatibility

**Files:**
- Modify: `data/feature_store.py`
- Modify: `scripts/tune_model.py`
- Modify: `scripts/train_regime_models.py`
- Test: `tests/test_asof_pit_feature_view.py`

- [ ] **Step 1: Write failing tests**

```python
def test_time_series_splitter_accepts_asof_dates():
    splitter = TimeSeriesSplitter(train_months=2, test_months=1, step_months=1)
    keys = ["2026-01-03", "2026-01-10", "2026-02-03", "2026-03-03"]
    assert splitter.split(keys)
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_asof_pit_feature_view.py::test_time_series_splitter_accepts_asof_dates -q`
Expected: fail or show ambiguous month-only semantics.

- [ ] **Step 3: Implement split key helpers**

Add `feature_time_key_column(df)` and `feature_period_key(series)`; training scripts use `as_of_date` when present, otherwise `month`.

- [ ] **Step 4: Run green test**

Run: `.venv/bin/python -m pytest tests/test_asof_pit_feature_view.py -q`
Expected: pass.

### Task 5: Docs and Verification

**Files:**
- Modify: `docs/specs/01-data-pipeline.md`
- Modify: `docs/specs/02-signal-system.md`
- Modify: `docs/specs/03-backtest-engine.md`
- Modify: `docs/strategies/ml_lgbm.md`
- Modify: `wiki/concepts/ml-pipeline.md`
- Modify: `wiki/concepts/system-architecture.md`
- Modify: `wiki/decisions/duckdb-migration.md`
- Modify: `docs/acceptance-matrix.md`

- [ ] **Step 1: Update docs**

Replace month-only descriptions with as-of-date PIT views. Mention monthly files remain compatible but are no longer the precision target.

- [ ] **Step 2: Verify**

Run:
- `.venv/bin/python -m pytest tests/test_asof_pit_feature_view.py tests/test_ml_lgbm_closure.py -q`
- `.venv/bin/python -m pytest -q`
- `.venv/bin/python backtest/run_all_strategies.py --strategy ml_lgbm`
- `npm run typecheck`
- `npm run build`
- `git diff --check`

Expected: all commands exit 0; ML backtest produces trades.
