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
  - Other LLM provider variables referenced by `config/settings.yaml: llm.providers.<provider>.api_key_env`
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
| `astroq agent autonomy step --session <session_id> --text "..." --json` | 运行一次 bounded autonomy：创建 CEO message，经 `agent_routing` 与 `agent_tool_planning` provider 生成固定工具计划，只执行本轮新增 read_only/dry_run 行动，审批/写入/交易行动只跳过并记录 |
| `astroq agent autonomy run --session <session_id> --text "..." --max-steps 2 --json` | 运行一个有上限的 bounded autonomy loop：每一步都沿用 step 的固定工具白名单和 read_only/dry_run 边界，遇到无安全动作、步骤未就绪或达到上限即停机 |
| `astroq agent program create --session <session_id> --goal "..." --max-steps 6 --json` | 把开放式 CEO 目标持久化为 autonomy program；安全项成为 fixed-registry read_only/dry_run 阶段，未知/写入/代码/交易项成为 blocker、审批项或工单 |
| `astroq agent programs --session <session_id> --json` | 查看本地 autonomy program ledger |
| `astroq agent program run <program_id> --dry-run --json` | 预览 program 待运行安全阶段，不写 action/run ledger |
| `astroq agent program run <program_id> --json` | 运行 program 中待执行的安全 fixed-registry 阶段；仍不会自动执行写入、代码、paper/live 交易或未知工具 |
| `astroq agent message --session <session_id> --desk reporting --text "..." --json` | 写入 CEO 消息并生成 LLM-first desk response；显式 `--desk` 只指定负责部门，工具选择仍由 `agent_tool_planning` provider 输出并由固定注册表校验 |
| `astroq agent plan --desk reporting --text "..." --json` | 只预览 LLM-first fixed-tool workflow plan，不写 ledger；provider 不可用或输出非法 schema 时直接阻断 |
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
| `astroq agent context status --session <session_id> --json` | 查看指定 CEO Office 会话的 prompt context 预算、阈值、最新 context pack 和压缩状态；不写 artifact |
| `astroq agent context compact --session <session_id> --dry-run --json` | 预览会话 context pack，不删除原始消息、不写 artifact |
| `astroq agent context compact --session <session_id> --json` | 生成可审计 context pack artifact 和 evidence；原始 message ledger 保持不变 |
| `astroq agent live readiness --json` | 检查 MiniQMT/QMT 实盘 readiness；默认关闭且不会回退到 PaperBroker |
| `astroq agent live environment --json` | 只读验证本机 MiniQMT/QMT SDK、账号、userdata、gateway 和终端查询能力；不下单、不回退 PaperBroker |
| `astroq agent live smoke --json` | 运行不下单 MiniQMT/QMT smoke test；live ready 时只调用只读 reconciliation 探测并写 smoke evidence |
| `astroq agent live preview --symbol 600000.SH --side buy --quantity 100 --limit-price 10 --evidence <evidence_id> --json` | 预览实盘限价单，不提交订单；输出 approval、扩展 risk gate、现金/持仓影响和 blocker |
| `astroq agent live propose --session <session_id> --symbol 600000.SH --side buy --quantity 100 --limit-price 10 --evidence <evidence_id> --json` | 生成实盘订单审批卡；默认 live disabled 时返回 blocked，不创建 action |
| `astroq agent live submit <action_id> --json` | 提交已批准的 live_order action；默认 MiniQMT/QMT adapter fail closed，不会回退到 PaperBroker |
| `astroq agent live reconcile --json` | 扫描已提交 live_order 对账证据，调用 live adapter reconciliation，并写 scheduled reconciliation artifact |
| `astroq agent live monitor --json` | 运行 cron-callable live monitor tick，汇总 readiness、kill switch 和 reconciliation，并写 monitor evidence artifact |
| `astroq agent live kill-switch activate --reason "..." --json` | 激活本地实盘 kill switch，取消 queued live_order actions，对已提交实盘证据请求 broker-side 撤单，并阻断后续 live preview/propose/submit |
| `astroq agent live kill-switch status --json` | 查看本地实盘 kill switch 状态 |
| `astroq agent handoffs --json` | 查看跨 desk 交接 ledger |
| `astroq agent handoff resolve <handoff_id> --json` | 标记跨 desk 交接事项已完成 |
| `astroq agent work-orders --session <session_id> --json` | 查看 Engineering Desk 创建的工程工单 |
| `astroq agent work-order create --session <session_id> --title "..." --summary "..." --impact "..." --file path --verify "pytest ..." --evidence <evidence_id> --json` | 创建带证据、影响范围、影响文件和建议验证命令的工程工单；Web runtime 不直接改仓库 |
| `astroq agent work-order update <work_order_id> --status resolved --resolution "..." --json` | 更新工程工单状态，`resolved/canceled` 会写终态审计时间 |
| `astroq agent memory export --json` | 导出本地透明 memory ledger 到 `var/artifacts/agent/memory/` |
| `astroq agent memory prune --dry-run --json` | 预览或清理已归档 session 的本地 agent memory |
| `astroq agent memory clear --confirm --json` | 显式确认后清空本地 agent memory ledger |
| `astroq agent desks --json` | 查看 Data / Research / Portfolio / Risk / Execution / Engineering / Reporting desk agents |
| `astroq agent policies --json` | 查看每个 risk level 的显式审批策略、默认决策和过期窗口 |
| `astroq config env --json` | 检查当前进程环境变量密钥状态（脱敏输出） |
| `astroq config validate --json` | 校验 settings 和策略注册表 |
| `astroq config llm-runtime --json` | 查看本机全局 LLM provider/model/reasoning profile 和可选项 |
| `astroq config llm-runtime reset --json` | 清除本机 LLM runtime override，恢复 `config/settings.yaml` 默认值 |
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
| `astroq strategy data-coverage --json` | 生成策略数据覆盖矩阵，检查每个策略声明数据族、必需缺口、可选补充和 observed evidence 状态 |
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
- When adding an OpenAI-compatible LLM provider, add it under `llm.providers.<provider>` with `protocol: openai_compatible`, `api_key_env`, `base_url`, `default_model`, optional `request.*`, optional provider-specific `reasoning_modes`, and provider-specific `pricing.models`. `llm.use_cases.*` remains the default routing shape; the active local provider/model/reasoning profile is managed through `GET/PATCH /api/system/llm-runtime` or `astroq config llm-runtime --json`.
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
- Agent Company OS has a foundation runtime for session metadata, messages, evidence/action refs, fixed tool registry dispatch, approval gates, context compression, and provider-backed CEO Office conversation. Web messages that omit `desk` must route through `agent_routing`; tool selection must route through `agent_tool_planning`; normal business wording must route through `agent_response`. Those use cases share one local LLM runtime profile for provider/model/reasoning, while preserving their own timeout/temperature/JSON call shape. Provider failures, invalid JSON, unknown desks, unknown tools, invalid parameters, and out-of-scope tools fail closed as blockers rather than falling back to keyword routing or templates. CEO Office remains the human-facing conversation, approval, and evidence surface; work orders, handoffs, approval policies, report rhythm, live readiness/monitoring, autonomy programs, provider planner controls, manual context compaction controls, and standalone action/evidence detail panels remain internal CLI/API or system surfaces rather than persistent CEO Office panels.
- LLM provider routing is fail-closed: unknown providers, disabled providers, missing `api_key_env`, missing `base_url`, missing model, or unsupported protocols must surface as blockers. Missing pricing may not block calls, but usage/cost views must mark the row as unpriced instead of borrowing another provider's price table.
- Formal strategy promotion depends on score panels, alpha evidence, data readiness, and execution assumptions. Missing data, missing source capability, missing score panels, and insufficient evidence must be reported as blocked/not_applicable states, not filled with placeholder values.
- The project is local-first. Network access, provider permissions, and data completeness must be explicit, observable, and never hidden behind fake defaults.

## Git Hygiene

- Run `git status --short` before editing and before final reporting.
- Do not stage `var/`, `reports/`, `data/cache/`, `.codegraph/`, local databases, model outputs, or caches.
- Keep commits scoped to the task. Documentation-only work should not include code churn.
- When asked to push, verify remote CI status after the push before reporting success.
