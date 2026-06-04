# Candidate Strategy Parameterization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move candidate strategy core windows, weights, thresholds, and regime blend rules from runner code into editable settings exposed by Config Center.

**Architecture:** Add a small candidate parameter catalog under `signals/candidates/` as the single source for defaults and editable field metadata. Each candidate runner reads merged defaults from `config/settings.yaml` at execution time, while the web config schema builds per-strategy parameter sections from the same catalog.

**Tech Stack:** Python, PyYAML settings loader, FastAPI config schema, Vue Config Center.

---

### Task 1: Parameter Contract Tests

**Files:**
- Modify: `tests/test_candidate_strategy_contracts.py`
- Modify: `tests/test_settings_schema_contracts.py`

- [ ] Add a runner test proving `trend_following` uses `strategies.trend_following.params.min_history_days`, MA windows, trend score levels, and score weights from settings.
- [ ] Add a schema test proving every candidate strategy has a `strategies.<name>.params` editable section with strategy-specific fields.
- [ ] Run focused tests and verify they fail before implementation.

### Task 2: Parameter Catalog

**Files:**
- Create: `signals/candidates/params.py`
- Modify: `config/settings.yaml`

- [ ] Define defaults and field metadata for all eight candidate strategies.
- [ ] Add matching `params:` blocks under each candidate strategy in canonical settings.
- [ ] Provide a deep-merge helper so missing user config falls back to code defaults.

### Task 3: Runner Refactor

**Files:**
- Modify: `signals/candidates/trend_following.py`
- Modify: `signals/candidates/donchian_breakout.py`
- Modify: `signals/candidates/rps_relative_strength.py`
- Modify: `signals/candidates/sector_rotation.py`
- Modify: `signals/candidates/quality_value.py`
- Modify: `signals/candidates/low_vol_defensive.py`
- Modify: `signals/candidates/volume_confirmation.py`
- Modify: `signals/candidates/regime_gated.py`

- [ ] Replace strategy-specific numeric windows, thresholds, score levels, and weights with `candidate_strategy_params(<name>)`.
- [ ] Keep output row contracts unchanged.
- [ ] Preserve production isolation and research runner behavior.

### Task 4: Config Center Schema

**Files:**
- Modify: `web/api/config_schema/strategy_sections.py`
- Modify: `web/frontend/src/view-models/useConfigCenter.ts`

- [ ] Build per-strategy parameter sections from the candidate parameter catalog.
- [ ] Keep registry, params, and selection gate sections grouped under each strategy in the secondary nav.
- [ ] Validate nested parameter fields through existing dotted-field validation.

### Task 5: Verification and Docs

**Files:**
- Modify: `docs/strategies/candidate-strategies.md`
- Modify: `docs/specs/02-signal-system.md`

- [ ] Update docs so candidate strategies are described as configurable research signals.
- [ ] Run focused pytest contracts, frontend typecheck/build, and `git diff --check`.
- [ ] Review git diff for unrelated changes before final report.
