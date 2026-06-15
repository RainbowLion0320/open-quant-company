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
| `astroq agent session run-readonly <session_id> --json` | 批量运行该会话中 proposed/read_only desk actions，跳过写入和交易行动 |
| `astroq agent run <action_id> --json` | Dispatch 安全或已批准 agent action 并写入 run ledger |
| `astroq agent cancel <action_id> --reason "..." --json` | 取消尚未完成的 agent action |
| `astroq agent expire --session <session_id> --json` | 标记已过期的 queued agent action，防止继续审批或执行 |
| `astroq agent report daily --session <session_id> --json` | 生成带 evidence 引用的 CEO brief 报告 artifact |
| `astroq agent report data_quality|risk|execution|engineering|release --session <session_id> --json` | 生成 Data/Risk/Execution/Engineering/Release 专用 operating-rhythm 报告 |
| `astroq agent rhythm --session <session_id> --json` | 显式运行到期 operating-rhythm 报告模板并写审计 artifact |
| `astroq agent rhythm --all-active --json` | 扫描所有 active sessions，运行到期报告节奏并写 scheduled audit artifact，适合 cron 调用 |
| `astroq agent reports --session <session_id> --json` | 查看本地已生成的 agent reports |
| `astroq agent notify report <report_id> --dry-run --json` | 对已生成报告做通知演练；去掉 `--dry-run` 后只通过系统环境变量配置的渠道发送并写通知审计 artifact |
| `astroq agent paper propose --session <session_id> --symbol 000001 --side buy --quantity 100 --limit-price 10 --evidence <evidence_id> --json` | 生成 PaperBroker 订单预览和审批卡，不提交订单 |
| `astroq agent paper submit <action_id> --json` | 提交已批准的 PaperBroker order action；提交前重新预览/风控，写 run 与 reconciliation evidence |
| `astroq agent paper cancel <action_id> --reason "..." --json` | 取消 queued paper approval request，或记录 broker-confirmed active paper order 撤单 |
| `astroq agent live readiness --json` | 检查 MiniQMT/QMT 实盘 readiness；默认关闭且不会回退到 PaperBroker |
| `astroq agent live preview --symbol 600000.SH --side buy --quantity 100 --limit-price 10 --evidence <evidence_id> --json` | 预览实盘限价单，不提交订单；输出 approval、扩展 risk gate、现金/持仓影响和 blocker |
| `astroq agent live propose --session <session_id> --symbol 600000.SH --side buy --quantity 100 --limit-price 10 --evidence <evidence_id> --json` | 生成实盘订单审批卡；默认 live disabled 时返回 blocked，不创建 action |
| `astroq agent live submit <action_id> --json` | 提交已批准的 live_order action；默认 MiniQMT/QMT adapter fail closed，不会回退到 PaperBroker |
| `astroq agent live reconcile --json` | 扫描已提交 live_order 对账证据，调用 live adapter reconciliation，并写 scheduled reconciliation artifact |
| `astroq agent live kill-switch activate --reason "..." --json` | 激活本地实盘 kill switch，取消 queued live_order actions，并阻断后续 live preview/propose/submit |
| `astroq agent live kill-switch status --json` | 查看本地实盘 kill switch 状态 |
| `astroq agent handoffs --json` | 查看跨 desk 交接 ledger |
| `astroq agent handoff resolve <handoff_id> --json` | 标记跨 desk 交接事项已完成 |
| `astroq agent work-orders --session <session_id> --json` | 查看 Engineering Desk 创建的工程工单 |
| `astroq agent work-order create --session <session_id> --title "..." --summary "..." --impact "..." --file path --verify "pytest ..." --evidence <evidence_id> --json` | 创建带证据、影响范围、影响文件和建议验证命令的工程工单；Web runtime 不直接改仓库 |
| `astroq agent memory export --json` | 导出本地透明 memory ledger 到 `var/artifacts/agent/memory/` |
| `astroq agent memory prune --dry-run --json` | 预览或清理已归档 session 的本地 agent memory |
| `astroq agent memory clear --confirm --json` | 显式确认后清空本地 agent memory ledger |
| `astroq agent desks --json` | 查看 Data / Research / Risk / Execution / Engineering / Reporting desk agents |
| `astroq agent policies --json` | 查看每个 risk level 的显式审批策略、默认决策和过期窗口 |
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
- Agent Company OS has a foundation runtime for session metadata, messages, deterministic desk responses, CEO Office target-desk message selection, CEO Office desk drill-down for mandates/tools/evidence requirements/related work, desk-scoped actions, explicit approval policy rows, approvals, action expiry, runs, ordered run event timelines, evidence resolution/snapshots, desk registry, fixed-registry tool permission checks, desk-declared fixed tool coverage, intent-aware deterministic routing to safe tools, daily-brief cross-desk read-only orchestration, session-level read-only workflow runner, open/resolved cross-desk handoffs, Engineering Desk work-order creation/listing, CEO Office work-order display, transparent memory inspect/export/prune/clear, evidence-cited CEO report artifacts, fixed local artifact-context aggregation for reports, explicit operating-rhythm report runs, cron-callable scheduled report rhythm ticks, report notification triggers with env-only Telegram/WeChat/Feishu channels and notification audit artifacts, non-mutating PaperBroker order proposal cards, approved PaperBroker submit with re-preview/re-risk and reconciliation evidence, dedicated PaperBroker cancellation runs for queued approval requests and broker-cancelable active orders, inline paper reconciliation summaries, default-disabled MiniQMT/QMT readiness probing, non-submitting live order preview with extended risk checks, approval-gated live submit/reconciliation contracts with no PaperBroker fallback, scheduled live reconciliation artifact scans, and local live kill switch operations that cancel queued live actions and block live paths before broker calls. Advanced desk reasoning, realtime Web streaming, advanced semantic report synthesis, broad workflow orchestration beyond bounded deterministic paths, and real MiniQMT/QMT SDK submit/reconcile are still phased work; do not present them as complete.
- Formal strategy promotion depends on score panels, alpha evidence, data readiness, and execution assumptions. Missing data, missing source capability, missing score panels, and insufficient evidence must be reported as blocked/not_applicable states, not filled with placeholder values.
- The project is local-first. Network access, provider permissions, and data completeness must be explicit, observable, and never hidden behind fake defaults.

## Git Hygiene

- Run `git status --short` before editing and before final reporting.
- Do not stage `var/`, `reports/`, `data/cache/`, `.codegraph/`, local databases, model outputs, or caches.
- Keep commits scoped to the task. Documentation-only work should not include code churn.
- When asked to push, verify remote CI status after the push before reporting success.
