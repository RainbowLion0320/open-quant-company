# Agent Operating Guide

This file is the working entry point for Codex, Claude, cron jobs, and other automation agents. Human-facing project context belongs in `README.md`; implementation contracts belong in `docs/specs/`; long-form concepts and decisions belong in `wiki/`.

## Read Order

1. `AGENTS.md` for operational rules.
2. `README.md` or `README.en.md` for the human-facing project overview.
3. `docs/PRD.md` for product scope and boundaries.
4. `docs/specs/` for current module behavior.
5. `docs/acceptance-matrix.md` for requirement-code-test traceability.
6. `wiki/index.md` for deeper concepts and architecture decisions.

Use current code, specs, tests, and generated artifacts as the source of truth. Do not rely on historical plans or old progress notes unless the user explicitly asks for archaeology.

## Runtime Boundaries

- `data/` is a Python source package. Do not put runtime data, caches, databases, model outputs, or reports there.
- `var/` is the local runtime root and is not committed. It contains store/cache/artifacts/db/logs.
- `reports/`, `.codegraph/`, local screenshots, test artifacts, and generated SBOM files are runtime outputs unless explicitly tracked by the repository.
- If an untracked path such as `data/cache/` appears, treat it as local runtime residue. Do not stage it and do not document it as a canonical path.
- Commit only source, docs, config templates, tests, static reference data, and intentional assets.

## Secrets and Configuration

- API tokens and keys are read only from process environment variables.
- Do not read or create `.env` files for runtime secrets.
- Do not write secrets into `config/settings.yaml`, docs, screenshots, logs, or generated artifacts.
- Canonical environment variables include:
  - `TUSHARE_TOKEN`
  - `DEEPSEEK_API_KEY`
  - `ASTROLABE_API_KEY`
  - `ASTROLABE_VAR`
  - notification variables such as `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WECHAT_WEBHOOK_URL`, and `FEISHU_WEBHOOK_URL`
- Check secret presence with masked output:

```bash
astroq config env --json
```

## Canonical Entrypoints

Use `astroq` for automation and JSON-readable operations:

```bash
astroq health --json
astroq config validate --json
astroq data status --json
astroq data tushare-audit --json
astroq data tushare-backfill --scope missing --resume --json
astroq strategy catalog --json
astroq strategy run all --mode production --json
astroq backtest check --json
astroq execution dry-run --json
astroq architecture ast --json
astroq test design --json
astroq test check --suite quick --json
astroq docs check --json
astroq web build --json
astroq web serve --host 0.0.0.0 --port 8501
```

For Python module execution, prefer:

```bash
.venv/bin/python -m astrolabe_cli.main ...
```

For the Web UI during development:

```bash
uvicorn web.api.app:create_app --factory --host 0.0.0.0 --port 8501 --reload
cd web/frontend && npm run dev
```

## Change Discipline

- Keep `README.md` focused on first-time human readers. Do not add long maintenance rules, full command catalogs, directory inventories, CI policy, or agent-specific instructions there.
- Put agent and automation rules in `AGENTS.md`.
- Put contribution process in `CONTRIBUTING.md`.
- Put maintainer decision rules in `GOVERNANCE.md`.
- Put security reporting in `SECURITY.md`.
- Update specs, wiki, acceptance matrix, and tests when behavior changes.
- Do not preserve deprecated compatibility paths unless the current design explicitly requires them.
- Do not revert user changes. If the worktree is dirty, inspect changes and stage only files that belong to the task.

## Verification Gates

For documentation-only changes, run:

```bash
git diff --check
astroq docs check --json
.venv/bin/pre-commit run --files <changed-doc-files>
```

For Python or CLI changes, add:

```bash
.venv/bin/ruff check astrolabe_cli backtest broker core cybernetics data models notify pipeline research scripts signals tests web/api --select E9,F63,F7,F82
.venv/bin/python -m compileall -q astrolabe_cli backtest broker cybernetics data models pipeline research scripts signals tests web/api
.venv/bin/python -m pytest -q
```

For frontend changes, add:

```bash
cd web/frontend
npm run typecheck
npm run build
```

For system-intelligence changes, regenerate the relevant artifact and validate the API/UI path:

```bash
astroq architecture ast --json
astroq test design --json
```

## Current Architecture Notes

- Data access is organized under `data.storage`, `data.ingestion`, `data.market`, `data.features`, `data.quality`, `data.ops`, `data.llm`, `data.rates`, `data.strategy`, and `data.reference`.
- Production backtests use `backtest/pipeline_runner.py` plus shared modules under `pipeline/`.
- Strategy state is owned by Strategy Catalog and separated into production, paper, and candidate layers.
- Web System visualizations include CodeGraph, AST diagnostics, architecture diagnostics, and test design intelligence.
- The project is local-first. Network access, provider permissions, and data completeness must be explicit, observable, and never hidden behind fake defaults.

## Git Hygiene

- Run `git status --short` before editing and before final reporting.
- Do not stage `var/`, `reports/`, `data/cache/`, `.codegraph/`, local databases, model outputs, or caches.
- Keep commits scoped to the task. Documentation-only work should not include code churn.
- When asked to push, verify remote CI status after the push before reporting success.
