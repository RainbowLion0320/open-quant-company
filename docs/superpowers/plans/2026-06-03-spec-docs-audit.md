# Spec Documentation Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align every document in `docs/specs/` with the current code, route structure, configuration ownership, tests, and wiki/acceptance contracts.

**Architecture:** Treat specs as current product contracts, not project history. Each spec is audited against source files, tests, and API/UI entry points; outdated implementation names are removed or rewritten to current stable boundaries.

**Tech Stack:** Markdown specs, Python pytest documentation contracts, FastAPI route files, Vue frontend route/components, local shell/rg inventory.

---

### Task 1: Inventory Current Spec Claims

**Files:**
- Read: `docs/specs/01-data-pipeline.md`
- Read: `docs/specs/02-signal-system.md`
- Read: `docs/specs/03-backtest-engine.md`
- Read: `docs/specs/04-execution-layer.md`
- Read: `docs/specs/05-web-platform.md`
- Read: `docs/specs/06-multi-asset.md`

- [x] List every code path, API route, CLI command, data path, and test reference in each spec.
- [x] Search for stale vocabulary: `legacy`, `deprecated`, old route names, removed script tests, stale DSL API, stale page counts, stale route counts, and old UI layout descriptions.
- [x] Record which claims require source-code confirmation before editing.

### Task 2: Cross-Check Against Current Source

**Files:**
- Read: `config/settings.yaml`
- Read: `data/data_registry.py`
- Read: `data/datahub.py`
- Read: `data/sector_pipeline/*.py`
- Read: `signals/*.py`
- Read: `signals/candidates/*.py`
- Read: `backtest/*.py`
- Read: `broker/*.py`
- Read: `web/api/routes/*.py`
- Read: `web/api/schemas/*.py`
- Read: `web/frontend/src/router/index.ts`
- Read: `astrolabe_cli/*.py`
- Read: `tests/test_*contracts.py`

- [x] Verify Data Pipeline spec paths and quality/freshness contracts.
- [x] Verify Signal System spec strategy lifecycle, DSL, candidate strategy, and selection contracts.
- [x] Verify Backtest Engine spec PIT, regime replay, benchmark, evidence, and script entry points.
- [x] Verify Execution Layer spec broker module split, PaperBroker persistence, risk controls, cron, and API routes.
- [x] Verify Web Platform spec routes, schemas, UI modules, i18n, Pipeline graph, Hindsight, and CLI control plane.
- [x] Verify Multi-Asset spec adapters, allocation, tournament, sector pipeline, and Web exposure.

### Task 3: Apply Spec Corrections

**Files:**
- Modify: affected files under `docs/specs/`
- Modify if needed: `docs/acceptance-matrix.md`
- Modify if needed: `wiki/**/*.md`

- [x] Replace obsolete API routes and module paths with current code paths.
- [x] Remove stale implementation promises that are not present in code.
- [x] Rewrite historical notes into current-state contracts when they still matter.
- [x] Keep specs concise; do not add dynamic performance results or fragile runtime numbers.

### Task 4: Add Or Tighten Documentation Contracts

**Files:**
- Modify: `tests/test_architecture_contracts.py`
- Modify: `tests/test_documentation_contracts.py`

- [x] Add regression tokens for stale spec phrases discovered during the audit.
- [x] Add positive checks for current spec tokens that should remain stable.
- [x] Keep tests focused on current specs and avoid blocking legitimate future wording changes unnecessarily.

### Task 5: Verify

**Files:**
- Read: git diff and test output

- [x] Run `rg` scans for all removed stale phrases.
- [x] Run `.venv/bin/python -m pytest tests/test_documentation_contracts.py tests/test_architecture_contracts.py tests/test_cli_ops_commands.py -q`.
- [x] Run `.venv/bin/python -m pytest -q` if source or broad doc contracts changed.
- [x] Run `git diff --check`.
- [x] Summarize changed specs, fixed stale claims, and remaining documented quality debt.

**Verification completed:**
- `PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main docs check --json`
- `PYTHONPATH=. .venv/bin/python -m pytest tests/test_documentation_contracts.py tests/test_architecture_contracts.py tests/test_cli_ops_commands.py -q`
- `PYTHONPATH=. .venv/bin/python -m pytest -q`
- `git diff --check`
