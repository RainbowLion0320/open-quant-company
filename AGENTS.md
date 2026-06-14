# Agent Operating Guide

This file is the working entry point for Codex, Claude, cron jobs, and other automation agents. Human-facing project context belongs in `README.md`; implementation contracts belong in `docs/specs/`; long-form concepts and decisions belong in `wiki/`.

## Read Order

1. `AGENTS.md` for operational rules.
2. `README.md` or `README.en.md` for the human-facing project overview.
3. `docs/product/prd.md` for product scope and boundaries.
4. `docs/specs/` for current module behavior.
5. `docs/product/acceptance-matrix.md` for requirement-code-test traceability.
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

| 命令 | 用途 |
|------|------|
| `astroq health --json` | 检查项目版本、DataHub 路径和本地健康状态 |
| `astroq agent sessions --json` | 查看本地 Agent Company OS 会话 ledger |
| `astroq agent session create --title "Daily CEO Brief" --json` | 创建 CEO Office / desk agent 会话 |
| `astroq agent session update <session_id> --title "..." --tag daily --json` | 重命名、归档或更新本地 agent 会话标签 |
| `astroq agent run <action_id> --json` | Dispatch 安全或已批准 agent action 并写入 run ledger |
| `astroq agent cancel <action_id> --reason "..." --json` | 取消尚未完成的 agent action |
| `astroq agent handoffs --json` | 查看跨 desk 交接 ledger |
| `astroq agent handoff resolve <handoff_id> --json` | 标记跨 desk 交接事项已完成 |
| `astroq agent memory export --json` | 导出本地透明 memory ledger 到 `var/artifacts/agent/memory/` |
| `astroq agent memory prune --dry-run --json` | 预览或清理已归档 session 的本地 agent memory |
| `astroq agent memory clear --confirm --json` | 显式确认后清空本地 agent memory ledger |
| `astroq agent desks --json` | 查看 Data / Research / Risk / Execution / Engineering / Reporting desk agents |
| `astroq config env --json` | 检查当前进程环境变量密钥状态（脱敏输出） |
| `astroq config validate --json` | 校验 settings 和策略注册表 |
| `astroq data status --json` | 扫描本地数据健康 |
| `astroq data repair stock_valuation --dry-run --json` | 演练单表修复 |
| `astroq data sources --json` | 查看外部数据源能力目录最近一次审计摘要 |
| `astroq data sources audit --source all --discovery-depth catalog --json` | 生成 AKShare/Tushare/候选源能力治理产物，不访问候选源网络接口 |
| `astroq data sources audit --source all --discovery-depth sample --json` | 只对白名单候选接口做极小样本探测并记录元数据 |
| `astroq data sources audit --source all --discovery-depth full-sample --resume --json` | 对所有已发现能力生成样本探测或阻断原因闭环，不写入真实数据仓 |
| `astroq data sources audit --source all --discovery-depth full-sample --dry-run --json` | 只输出全量样本探测计划，不调用 provider |
| `astroq data sources diff-registry --json` | 对比 source capability registry 与项目 data_registry |
| `astroq data tushare-audit --json` | 审计 Tushare 权限和本地覆盖率 |
| `astroq data tushare-backfill --scope missing --resume --json` | 按缺口补齐 Tushare 数据 |
| `astroq strategy catalog --json` | 查看 production / paper / candidate 策略目录 |
| `astroq strategy run all --mode production --json` | 运行生产策略扫描 |
| `astroq strategy run trend_following --mode research --dry-run --json` | 候选策略研究扫描演练 |
| `astroq strategy compete --json` | 生成 12 策略统一 OOS 公平竞赛报告 |
| `astroq lifecycle check --json` | 生成全运行周期证据链 readiness 产物 |
| `astroq regime status --json` | 查看当前 market regime |
| `astroq regime train-profit --dry-run --json` | 演练利润导向 regime 训练入口 |
| `astroq backtest run --strategy multifactor --dry-run --json` | 回测入口演练 |
| `astroq backtest check --json` | 运行回测质量检查 |
| `astroq execution dry-run --json` | 模拟执行链路演练 |
| `astroq pipeline list --json` | 查看流程图列表 |
| `astroq architecture ast --json` | 生成 AST 重复实现诊断 |
| `astroq test design --json` | 生成测试设计诊断 |
| `astroq test check --suite quick --json` | 运行快速测试 gate 并记录产物 |
| `astroq docs check --json` | 扫描已知陈旧文档短语 |
| `astroq web build --json` | 构建前端资源 |
| `astroq web serve --host 0.0.0.0 --port 8501` | 启动本地 Web API 和静态资源服务 |

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
- Put maintainer decision rules in `docs/project/governance.md`.
- Put security reporting in `SECURITY.md`.
- Update specs, wiki, acceptance matrix, and tests when behavior changes.
- When adding an external data source, fetcher, provider adapter, or new data dimension, update the Source Capability Registry and verify `astroq data sources diff-registry --json`.
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
astroq lifecycle check --json
```

## Current Architecture Notes

- Data access is organized under `data.storage`, `data.ingestion`, `data.market`, `data.features`, `data.quality`, `data.ops`, `data.llm`, `data.rates`, `data.strategy`, and `data.reference`.
- External provider capabilities are governed separately from project dimensions: Source Capability Registry describes what sources can provide, `data_registry` describes what the project uses, and DataHub coverage describes what exists locally. Capability discovery is layered as `discovered`, `sample_probed`, `contracted`, and `project_integrated`; never treat a discovered candidate endpoint as production-ready without a contract and registry mapping.
- Production backtests use `backtest/pipeline_runner.py` plus shared modules under `pipeline/`.
- Strategy state is owned by Strategy Catalog and separated into production, paper, and candidate layers.
- Web System visualizations include CodeGraph, AST diagnostics, architecture diagnostics, test design intelligence, and lifecycle readiness.
- Agent Company OS has a foundation runtime for session metadata, messages, deterministic desk responses, desk-scoped actions, approvals, runs, evidence, desk registry, fixed-registry tool permission checks, open/resolved cross-desk handoffs, and transparent memory inspect/export/prune/clear. Advanced desk reasoning, streaming reports, broad workflow orchestration, and live execution are still phased work; do not present them as complete.
- Formal strategy promotion depends on score panels, alpha evidence, data readiness, and execution assumptions. Missing data, missing source capability, missing score panels, and insufficient evidence must be reported as blocked/not_applicable states, not filled with placeholder values.
- The project is local-first. Network access, provider permissions, and data completeness must be explicit, observable, and never hidden behind fake defaults.

## Git Hygiene

- Run `git status --short` before editing and before final reporting.
- Do not stage `var/`, `reports/`, `data/cache/`, `.codegraph/`, local databases, model outputs, or caches.
- Keep commits scoped to the task. Documentation-only work should not include code churn.
- When asked to push, verify remote CI status after the push before reporting success.
