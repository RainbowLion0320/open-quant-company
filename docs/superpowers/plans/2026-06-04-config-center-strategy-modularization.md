# Config Center Strategy Modularization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the Web Config Center from a flat section list into an extensible grouped model, with strategy-related settings managed under one top-level domain and second-level strategy blocks.

**Architecture:** Backend schema ownership moves from a single `settings_schema.py` list to `web/api/config_schema/`, which assembles static sections, dynamic strategy sections, and group summaries. Frontend Config Center consumes `groups + sections`, switches only top-level groups, and renders second-level sections vertically in one page.

**Tech Stack:** FastAPI settings schema, Vue 3 Composition API, YAML dotted-section PATCH, pytest contract tests, Vite build.

---

### Task 1: Backend Schema Model

**Files:**
- Create: `web/api/config_schema/fields.py`
- Create: `web/api/config_schema/groups.py`
- Create: `web/api/config_schema/sections.py`
- Create: `web/api/config_schema/strategy_sections.py`
- Create: `web/api/config_schema/schema.py`
- Modify: `web/api/settings_schema.py`

- [x] Split field helpers, top-level groups, static sections, dynamic strategy sections, and schema assembly into separate modules.
- [x] Return `groups`, `sections`, `total_groups`, `total_sections`, and `total_fields` from `GET /api/settings/schema`.
- [x] Add bool/select validation for strategy enablement and lifecycle fields.

### Task 2: Strategy Configuration Contract

**Files:**
- Modify: `research/strategy_catalog.py`
- Modify: `web/api/schemas/strategy.py`
- Modify: `web/frontend/src/api/types/strategy.ts`

- [x] Add `config_key` to Strategy Catalog response so Strategy Lab and Config Center share the same config-location contract.
- [x] Generate editable `strategies.<name>` lifecycle sections from `config/settings.yaml`.
- [x] Generate editable `signal_selection.strategies.<name>` threshold sections from current strategy overrides.

### Task 3: Config Center UI

**Files:**
- Modify: `web/frontend/src/view-models/useConfigCenter.ts`
- Modify: `web/frontend/src/views/ConfigCenter.vue`
- Modify: `web/frontend/src/styles/views/config-center.css`
- Modify: `web/frontend/src/i18n/messages/{zh-CN,en-US}/configCenter.ts`
- Modify: `web/frontend/src/api/modules/settings.ts`

- [x] Replace flat `activeSection` navigation with top-level `activeGroup`.
- [x] Render second-level subgroups and section panels vertically inside the selected group.
- [x] Keep saves scoped to individual dotted sections with per-section dirty detection.
- [x] Add controls for float/int/string/bool/select fields.

### Task 4: Contracts And Documentation

**Files:**
- Modify: `tests/test_settings_schema_contracts.py`
- Modify: `tests/test_web_system_contracts.py`
- Modify: `docs/specs/02-signal-system.md`
- Modify: `docs/specs/05-web-platform.md`
- Modify: `docs/acceptance-matrix.md`
- Modify: `wiki/concepts/system-architecture.md`

- [x] Lock backend group/subgroup schema and strategy sections with pytest contracts.
- [x] Lock frontend grouped rendering with static UI contract tests.
- [x] Update specs, acceptance matrix, and wiki to describe the grouped config model.

### Task 5: Verification

**Files:**
- Read: test and build output

- [x] Run targeted Python contract tests.
- [x] Run frontend typecheck/build.
- [x] Run full pytest suite.
- [x] Verify `/system?tab=config` in browser.
- [x] Run `git diff --check`.

**Verification completed:**
- `PYTHONPATH=. .venv/bin/python -m pytest tests/test_settings_schema_contracts.py tests/test_web_system_contracts.py tests/test_strategy_catalog.py tests/test_modularization_contracts.py tests/test_documentation_contracts.py -q`
- `npm run typecheck`
- `npm run build`
- `PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main docs check --json`
- `PYTHONPATH=. .venv/bin/python -m pytest -q`
- Browser check: `/system?tab=config` rendered 6 groups, Strategy Management rendered 37 sections, console errors were empty.
- `git diff --check`
