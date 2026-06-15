# Spec: Agent Company OS

> Version: 0.1
> Updated: 2026-06-16
> Status: phased implementation contract
> Related: [PRD](../product/prd.md), [Web Platform](05-web-platform.md), [Master Roadmap](../project/agent-company/00-master-roadmap.md)

## 1. Purpose

Agent Company OS is the planned local-first operating layer for Open Quant Company. It lets the human user act as CEO while desk agents coordinate data, research, risk, execution, engineering, and reporting work.

This spec defines behavior contracts for the Agent Company OS rollout. Foundation runtime pieces, the first CEO Office page, deterministic desk routing, bounded fixed-command dispatch, run event timelines, session snapshot SSE streaming, run event snapshot SSE streaming, active subprocess stdout/stderr chunk event recording, transparent memory governance, evidence-cited report artifacts with CEO Office template selection, fixed cross-artifact report context aggregation, deterministic semantic report synthesis, deterministic cross-session report trend synthesis, deterministic causal-chain report synthesis with recurring-chain escalation, explicit operating-rhythm report runs, cron-callable scheduled report rhythm ticks, env-only report notification triggers, paper order preview/proposal/approved-submit/cancel cards with inline paper reconciliation summaries, default-disabled live readiness probing, no-submit live broker environment validation and smoke tests, live order preview risk gating, approval-gated live submit/reconciliation contracts, runtime project-ledger snapshot wiring for live reconciliation, scheduled live reconciliation scans, cron-callable live monitor evidence ticks, live kill-switch queued-action cancellation plus broker-side cancellation requests for submitted live evidence, explicit MiniQMT/QMT SDK gateway bridge with config-based factory loading, desk-declared fixed tool registry coverage, deterministic intent-to-tool routing, deterministic multi-intent workflow planning, artifact-aware deterministic priority planning from local evidence, bounded session-backlog adaptive planning, bounded artifact-plus-session adaptive planning, deterministic open-ended company-wide diagnostic planning, opt-in semantic planner draft filtering, Data Desk repair dry-run plus approval workflow, Research strategy-blocker cross-desk diagnosis, Engineering Desk code/bug work-order triage, daily-brief cross-desk orchestration, and portfolio review cross-desk orchestration are implemented first; autonomous unbounded cross-tool planning beyond fixed-registry deterministic modes remains planned until its phase lands.

## 2. Product Contract

Agent Company OS must provide:

- A CEO Office Web page as the default `/` route.
- A local Agent Runtime for sessions, messages, actions, approvals, runs, memory, and evidence.
- Desk agents with explicit mandates and tool permissions.
- Approval-gated state-changing actions.
- Evidence references for agent claims.
- Transparent local memory that can be inspected, exported, pruned, and cleared.
- MiniQMT/QMT live execution as a default-disabled, approval-gated capability; the current foundation includes readiness, no-submit smoke tests, non-submitting order preview, live proposal cards, a fail-closed approved-submit/reconciliation contract, and an explicit SDK gateway bridge that only runs when injected/configured through `execution.live.sdk_gateway_factory`. SDK submission remains disabled by default and requires explicit live enablement, installed xtquant modules, account configuration, and a valid userdata path.

## 3. API Surface

All endpoints are planned under `/api/agent/*`.

| Method | Endpoint | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/agent/sessions` | List agent sessions. | Implemented |
| `POST` | `/api/agent/sessions` | Create a new session. | Implemented |
| `GET` | `/api/agent/sessions/{session_id}` | Read a session with messages and linked actions. | Implemented |
| `GET` | `/api/agent/sessions/{session_id}/stream` | Stream session snapshot changes over Server-Sent Events with a one-shot mode for tests and clients that need a bounded read. | Implemented |
| `PATCH` | `/api/agent/sessions/{session_id}` | Rename, archive, tag, or update session metadata. | Implemented |
| `POST` | `/api/agent/sessions/{session_id}/run-readonly` | Dispatch proposed safe `read_only` / `dry_run` actions for one session and skip approval-required, write, and trading actions. | Implemented |
| `POST` | `/api/agent/sessions/{session_id}/messages` | Add a CEO message, create a deterministic desk response, and link evidence/actions/handoffs. | Implemented |
| `POST` | `/api/agent/plans` | Preview a deterministic desk workflow plan, action status previews, approvals, handoffs, reasoning rows, and work orders without writing the ledger. | Implemented |
| `GET` | `/api/agent/actions` | List actions with `session_id`, `status`, `desk`, and `risk_level` filters. | Implemented |
| `GET` | `/api/agent/handoffs` | List cross-desk handoff ledger rows, optionally scoped to a session. | Implemented |
| `POST` | `/api/agent/handoffs/{handoff_id}/resolve` | Mark a cross-desk handoff as resolved and write `resolved_at`. | Implemented |
| `GET` | `/api/agent/work-orders` | List Engineering Desk work orders, optionally scoped to a session. | Implemented |
| `POST` | `/api/agent/work-orders` | Create an Engineering Desk work order with impact, affected files, suggested verification, and evidence refs. | Implemented |
| `PATCH` | `/api/agent/work-orders/{work_order_id}` | Update Engineering Desk work order status and resolution audit text. | Implemented |
| `GET` | `/api/agent/actions/{action_id}` | Read an action and approval state. | Implemented |
| `POST` | `/api/agent/actions/{action_id}/approve` | Approve a pending action. | Implemented |
| `POST` | `/api/agent/actions/{action_id}/reject` | Reject a pending action with reason. | Implemented |
| `POST` | `/api/agent/actions/{action_id}/run` | Dispatch a safe or approved fixed-registry action and write a run ledger row plus run event timeline. | Implemented for bounded fixed commands |
| `POST` | `/api/agent/actions/{action_id}/cancel` | Cancel a proposed, approval-pending, or approved action before dispatch reaches a terminal status. | Implemented |
| `GET` | `/api/agent/runs/{run_id}` | Read a tool or workflow run with ordered run events. | Implemented |
| `GET` | `/api/agent/runs/{run_id}/stream` | Stream run event snapshot changes over Server-Sent Events with a one-shot mode for tests and auth-aware Web clients. | Implemented |
| `GET` | `/api/agent/evidence/{evidence_id}` | Resolve an evidence reference. | Implemented |
| `GET` | `/api/agent/desks` | List desk agents, health, allowed tools, and current blockers. | Implemented |
| `GET` | `/api/agent/policies` | List explicit approval policies for every risk level. | Implemented |
| `POST` | `/api/agent/paper/proposals` | Preview and propose a PaperBroker order as an approval-required action without submitting it. | Implemented proposal gate |
| `POST` | `/api/agent/paper/actions/{action_id}/submit` | Submit an approved PaperBroker order action after re-running preview/risk gates and writing reconciliation evidence. | Implemented approved submit gate |
| `POST` | `/api/agent/paper/actions/{action_id}/cancel` | Cancel a queued paper approval request or a submitted PaperBroker order when broker state still permits cancellation. | Implemented cancellation gate |
| `GET` | `/api/agent/live/readiness` | Report MiniQMT/QMT live readiness without submitting orders. | Implemented readiness probe |
| `GET` | `/api/agent/live/environment` | Validate local MiniQMT/QMT SDK, account, userdata path, gateway, and read-only terminal query path without submitting orders. | Implemented environment validation |
| `POST` | `/api/agent/live/smoke` | Run a no-submit MiniQMT/QMT live smoke test that records readiness and, when live-ready, a read-only reconciliation probe. | Implemented smoke probe |
| `POST` | `/api/agent/live/preview` | Preview a MiniQMT/QMT live order with readiness, extended risk gate, broker impact, and `submitted=false`. | Implemented preview gate |
| `POST` | `/api/agent/live/proposals` | Create an approval-required live order action only after live preview passes. | Implemented proposal gate |
| `POST` | `/api/agent/live/actions/{action_id}/submit` | Submit an approved live order action through the live broker adapter and write reconciliation evidence; default MiniQMT adapter fails closed unless an explicit SDK gateway is injected/configured. | Implemented contract and gateway bridge |
| `POST` | `/api/agent/live/reconciliation` | Scan submitted live order evidence, call live adapter reconciliation, and write a scheduled reconciliation artifact. | Implemented scheduled scan |
| `POST` | `/api/agent/live/monitor` | Run a cron-callable live monitor tick that aggregates readiness, kill-switch state, and submitted-order reconciliation into one evidence artifact. | Implemented monitor tick |
| `GET` | `/api/agent/live/kill-switch` | Read the local live kill switch state. | Implemented |
| `POST` | `/api/agent/live/kill-switch/activate` | Activate the local live kill switch, cancel queued live actions, request broker-side cancellations for submitted live evidence when supported, and block future live paths before broker calls. | Implemented |
| `POST` | `/api/agent/live/kill-switch/deactivate` | Deactivate the local live kill switch for future live previews/proposals/submits. | Implemented |
| `GET` | `/api/agent/reports` | List generated CEO reports, optionally scoped to a session. | Implemented |
| `POST` | `/api/agent/reports` | Generate a CEO report artifact and register report evidence. | Implemented |
| `POST` | `/api/agent/reports/{report_id}/notify` | Send or dry-run a report notification through env-configured channels and write notification audit evidence. | Implemented |
| `POST` | `/api/agent/reports/rhythm` | Run due report templates for a session and write a rhythm audit artifact. | Implemented |
| `POST` | `/api/agent/reports/rhythm/scheduled` | Scan active sessions, run due report rhythm, and write a scheduled audit artifact. | Implemented scheduled tick |
| `GET` | `/api/agent/memory` | Inspect transparent memory summaries and local ledger records. | Implemented |
| `POST` | `/api/agent/memory/export` | Export memory and evidence references to `var/artifacts/agent/memory/`. | Implemented |
| `POST` | `/api/agent/memory/prune` | Prune archived-session memory by explicit policy with dry-run support. | Implemented |
| `POST` | `/api/agent/memory/clear` | Clear memory after explicit confirmation. | Implemented |

## 4. CLI Surface

All commands must support `--json`.

| Command | Purpose | Status |
| --- | --- | --- |
| `astroq agent sessions --json` | List sessions. | Implemented |
| `astroq agent session create --title TITLE --json` | Create a session. | Implemented |
| `astroq agent session show SESSION_ID --json` | Show session details. | Implemented |
| `astroq agent session update SESSION_ID --title TITLE --status active\|archived\|blocked --tag TAG --json` | Rename, archive, or retag a session. | Implemented |
| `astroq agent session run-readonly SESSION_ID --json` | Dispatch proposed safe `read_only` / `dry_run` actions for one session and skip approval-required, write, and trading actions. | Implemented |
| `astroq agent message --session SESSION_ID --desk DESK --text TEXT --json` | Add a CEO message and return the deterministic desk response. | Implemented |
| `astroq agent plan --desk DESK --text TEXT --json` | Preview a side-effect-free deterministic desk workflow before creating messages, evidence, actions, handoffs, or work orders. | Implemented |
| `astroq agent actions --session SESSION_ID --status STATUS --desk DESK --risk-level RISK --json` | List actions filtered by session, status, desk, and risk level. | Implemented |
| `astroq agent handoffs --session SESSION_ID --json` | List cross-desk handoffs. | Implemented |
| `astroq agent handoff resolve HANDOFF_ID --json` | Mark a cross-desk handoff as resolved. | Implemented |
| `astroq agent work-orders --session SESSION_ID --json` | List Engineering Desk work orders. | Implemented |
| `astroq agent work-order create --session SESSION_ID --title TITLE --summary SUMMARY --impact IMPACT --file PATH --verify COMMAND --evidence EVIDENCE_ID --json` | Create an auditable Engineering Desk work order without editing repository files from the Web runtime. | Implemented |
| `astroq agent work-order update WORK_ORDER_ID --status open\|in_progress\|resolved\|canceled --resolution TEXT --json` | Update Engineering Desk work order lifecycle state. | Implemented |
| `astroq agent action show ACTION_ID --json` | Show action details. | Implemented |
| `astroq agent run ACTION_ID --json` | Dispatch a safe or approved action through the fixed tool registry. | Implemented for bounded fixed commands |
| `astroq agent approve ACTION_ID --json` | Approve an action. | Implemented |
| `astroq agent reject ACTION_ID --reason REASON --json` | Reject an action. | Implemented |
| `astroq agent cancel ACTION_ID --reason REASON --json` | Cancel a proposed, approval-pending, or approved action before terminal completion. | Implemented |
| `astroq agent expire --session SESSION_ID --json` | Mark expired queued actions. | Implemented |
| `astroq agent reports --session SESSION_ID --json` | List generated CEO reports. | Implemented |
| `astroq agent report daily --session SESSION_ID --json` | Generate an evidence-cited daily CEO brief. | Implemented |
| `astroq agent report data_quality\|risk\|execution\|engineering\|release --session SESSION_ID --json` | Generate dedicated operating-rhythm reports for data, risk, execution, engineering, and release review. | Implemented |
| `astroq agent notify report REPORT_ID --channel telegram --dry-run --json` | Send or dry-run an evidence-cited report notification and write audit evidence. | Implemented |
| `astroq agent rhythm --session SESSION_ID --json` | Generate due operating-rhythm reports and write a rhythm audit artifact. | Implemented |
| `astroq agent rhythm --all-active --json` | Scan active sessions, generate due operating-rhythm reports, and write a scheduled audit artifact for cron usage. | Implemented scheduled tick |
| `astroq agent paper propose --session SESSION_ID --symbol SYMBOL --side buy\|sell --quantity N --limit-price PRICE --evidence EVIDENCE_ID --json` | Preview and propose a PaperBroker order approval card without submitting it. | Implemented proposal gate |
| `astroq agent paper submit ACTION_ID --json` | Submit an approved PaperBroker order action after re-running preview/risk gates and writing reconciliation evidence. | Implemented approved submit gate |
| `astroq agent paper cancel ACTION_ID --reason REASON --json` | Cancel a queued paper approval request or a submitted PaperBroker order when broker state still permits cancellation. | Implemented cancellation gate |
| `astroq agent live readiness --json` | Report MiniQMT/QMT live readiness and blockers without PaperBroker fallback. | Implemented readiness probe |
| `astroq agent live environment --json` | Validate local MiniQMT/QMT SDK, account, userdata path, gateway, and read-only terminal query path without submitting orders. | Implemented environment validation |
| `astroq agent live smoke --json` | Run a no-submit MiniQMT/QMT smoke test; live-ready brokers only receive a read-only reconciliation probe and evidence artifact. | Implemented smoke probe |
| `astroq agent live preview --symbol SYMBOL --side buy\|sell --quantity N --limit-price PRICE --evidence EVIDENCE_ID --json` | Preview a live limit order without submission, including approval requirement, readiness blockers, extended risk gate, and estimated broker impact. | Implemented preview gate |
| `astroq agent live propose --session SESSION_ID --symbol SYMBOL --side buy\|sell --quantity N --limit-price PRICE --evidence EVIDENCE_ID --json` | Create an approval-required live order proposal when live preview passes. | Implemented proposal gate |
| `astroq agent live submit ACTION_ID --json` | Submit an approved live order action through the live adapter, re-running preview/risk gates and writing reconciliation evidence. | Implemented contract and gateway bridge |
| `astroq agent live reconcile --session SESSION_ID --json` | Scan submitted live order evidence and write scheduled reconciliation evidence. | Implemented scheduled scan |
| `astroq agent live monitor --session SESSION_ID --json` | Run a cron-callable monitor tick that writes readiness, kill-switch, and reconciliation evidence. | Implemented monitor tick |
| `astroq agent live kill-switch status --json` | Read the local live kill switch state. | Implemented |
| `astroq agent live kill-switch activate --reason REASON --json` | Activate the local live kill switch, cancel queued live actions, and request broker-side cancellations for submitted live evidence when supported. | Implemented |
| `astroq agent live kill-switch deactivate --reason REASON --json` | Deactivate the local live kill switch. | Implemented |
| `astroq agent evidence EVIDENCE_ID --json` | Resolve evidence. | Implemented |
| `astroq agent desks --json` | List desk registry and health. | Implemented |
| `astroq agent policies --json` | List explicit approval policies for every risk level. | Implemented |
| `astroq agent memory show --json` | Inspect local transparent memory. | Implemented |
| `astroq agent memory export --json` | Export local transparent memory. | Implemented |
| `astroq agent memory prune --dry-run --json` | Preview or prune archived session memory. | Implemented |
| `astroq agent memory clear --confirm --json` | Clear local memory after explicit confirmation. | Implemented |

`POST /api/agent/sessions/{session_id}/messages` and
`astroq agent message ... --json` return:

```json
{
  "message": {"role": "ceo"},
  "desk_response": {
    "message": {"role": "desk_agent"},
    "answer": "Reporting Desk 已记录 CEO 问题。",
    "evidence_refs": ["ev_..."],
    "proposed_actions": ["act_..."],
    "blockers": [],
    "handoffs": []
  }
}
```

The first implementation is deterministic: it does not call an LLM. It creates
safe local evidence references, proposes only desk-scoped fixed-registry actions,
and records any required cross-desk handoffs in the ledger.

## 5. Data Model

### 5.1 AgentSession

```json
{
  "session_id": "agt_sess_...",
  "title": "Daily CEO Brief",
  "status": "active",
  "created_by": "human",
  "default_desk": "reporting",
  "tags": ["daily"],
  "created_at": "2026-06-14T09:00:00+08:00",
  "updated_at": "2026-06-14T09:05:00+08:00"
}
```

Allowed statuses:

- `active`
- `archived`
- `blocked`

### 5.2 AgentMessage

```json
{
  "message_id": "agt_msg_...",
  "session_id": "agt_sess_...",
  "role": "desk_agent",
  "desk": "data",
  "content": "stock_limit_list blocks only strategies that depend on market event data.",
  "evidence_refs": ["ev_..."],
  "action_refs": ["act_..."],
  "created_at": "2026-06-14T09:06:00+08:00"
}
```

Allowed roles:

- `ceo`
- `desk_agent`
- `system`
- `tool`

### 5.3 AgentAction

```json
{
  "action_id": "act_...",
  "session_id": "agt_sess_...",
  "desk": "data",
  "action_type": "data_repair",
  "risk_level": "write_data",
  "status": "approval_required",
  "summary": "Repair missing stock_limit_list for one trading day.",
  "parameters": {"dimension": "stock_limit_list"},
  "expected_effect": "Writes one daily market-event partition into DataHub if provider succeeds.",
  "evidence_refs": ["ev_..."],
  "approval_required": true,
  "approval_decision": null,
  "expires_at": "2026-06-14T09:23:00+08:00",
  "created_at": "2026-06-14T09:08:00+08:00",
  "updated_at": "2026-06-14T09:08:00+08:00"
}
```

Allowed statuses:

- `proposed`
- `approval_required`
- `approved`
- `rejected`
- `running`
- `succeeded`
- `failed`
- `blocked`
- `expired`
- `canceled`

### 5.4 AgentWorkOrder

```json
{
  "work_order_id": "wo_...",
  "session_id": "agt_sess_...",
  "desk": "engineering",
  "title": "Investigate CodeGraph architecture finding",
  "summary": "The Engineering Desk found a likely coupling issue.",
  "impact": "May block future agent workflow extension.",
  "affected_files": ["agent_os/runtime.py"],
  "suggested_verification": [".venv/bin/python -m pytest tests/test_agent_os_contracts.py -q"],
  "evidence_refs": ["ev_..."],
  "status": "open",
  "resolution": "",
  "resolved_at": null,
  "created_by": "engineering_desk",
  "created_at": "2026-06-15T09:08:00+08:00",
  "updated_at": "2026-06-15T09:08:00+08:00"
}
```

Engineering work orders are the only Web-runtime path for code/design
follow-up. The Web UI may create and display them, but repository edits remain
outside the Web runtime and must be handled by Codex, Claude, or a human
maintainer.

Allowed statuses:

- `open`
- `in_progress`
- `resolved`
- `canceled`

`resolved` and `canceled` are terminal states and must write `resolved_at`.
`open` and `in_progress` keep `resolved_at=null`.

### 5.5 AgentRun

```json
{
  "run_id": "run_...",
  "action_id": "act_...",
  "tool_name": "astroq.data.repair",
  "command": [".venv/bin/astroq", "data", "repair", "stock_limit_list", "--json"],
  "started_at": "2026-06-14T09:10:00+08:00",
  "finished_at": "2026-06-14T09:11:00+08:00",
  "status": "succeeded",
  "return_code": 0,
  "stdout_summary": "1 partition repaired.",
  "stderr_summary": "",
  "artifact_refs": ["ev_..."]
}
```

### 5.6 EvidenceRef

```json
{
  "evidence_id": "ev_...",
  "kind": "artifact",
  "label": "Lifecycle readiness latest artifact",
  "uri": "var/artifacts/lifecycle/latest.json",
  "snapshot_uri": "var/artifacts/agent/evidence/ev_.../latest.json",
  "summary": "Data readiness blocked by macro_gdp source_not_updated.",
  "generated_at": "2026-06-14T09:00:00+08:00",
  "hash": "sha256:...",
  "freshness_status": "fresh"
}
```

Allowed kinds:

- `web_route`
- `api_endpoint`
- `cli_command`
- `artifact`
- `file`
- `code`
- `report`
- `ledger`

For file-backed evidence kinds (`artifact`, `file`, `code`, `report`, `ledger`),
the runtime copies the source file into `var/artifacts/agent/evidence/{evidence_id}/`.
The ledger stores the original `hash` and `snapshot_uri`. Resolving evidence
returns:

- `fresh` when the source still exists and matches the stored hash.
- `source_changed` when the source exists but no longer matches the stored hash.
- `source_missing` when the source is gone but the snapshot remains available.
- `missing_evidence` only when no ledger row exists, or an old file-backed row has
  neither source nor snapshot.

`web_route` evidence resolves only safe local routes that start with `/` and do
not use protocol-relative or backslash paths. Repository-local `file` and `code`
evidence resolves to safe navigation metadata for the CodeGraph file view;
`code` URIs may use `path:line`. Existing files outside the repository may be
snapshotted and hashed, but they do not produce CEO Office navigation links.
`api_endpoint` evidence resolves only local `/api/...` GET endpoints.
`cli_command` evidence resolves only inert `astroq` or `.venv/bin/astroq`
command metadata; shell syntax, pipes, redirects, external executable paths, and
non-astroq commands do not produce runnable navigation.

### 5.6 AgentReport

```json
{
  "report_id": "rep_...",
  "session_id": "agt_sess_...",
  "kind": "daily_brief",
  "title": "Daily CEO Brief",
  "summary": "3 recent messages, 1 active action, 0 open handoffs, 2 evidence references.",
  "path": "var/artifacts/agent/reports/daily_brief-...json",
  "markdown_path": "var/artifacts/agent/reports/daily_brief-...md",
  "evidence_id": "ev_...",
  "evidence_refs": ["ev_..."],
  "missing_evidence": [],
  "artifact_context": {
    "available_count": 5,
    "missing_count": 1,
    "invalid_count": 0,
    "items": [
      {
        "key": "lifecycle",
        "status": "available",
        "relative_path": "lifecycle/latest.json",
        "summary": {"blocked": 2}
      }
    ],
    "causal_chain_synthesis": {
      "status": "blocked",
      "chain_count": 1,
      "recurring_chain_count": 1,
      "chains": [
        {
          "chain_id": "data_readiness_to_strategy_block",
          "nodes": ["data_source_gap", "lifecycle_blocker", "strategy_evidence_blocked"],
          "owner_desks": ["data", "research", "risk"],
          "escalation": "recurring_blocker",
          "history": {
            "recurring": true,
            "recurring_causes": ["lifecycle_blocker", "strategy_evidence_blocked"],
            "max_total_count": 3
          }
        }
      ]
    },
    "domain_scorecard": {
      "overall_status": "blocked",
      "desks": [
        {
          "desk": "risk",
          "status": "blocked",
          "root_causes": ["lifecycle_blocker"],
          "recommended_command": "astroq lifecycle check --json"
        }
      ]
    },
    "source_narratives": {
      "overall_status": "blocked",
      "items": [
        {
          "key": "lifecycle",
          "owner_desk": "risk",
          "status": "blocked",
          "headline": "Lifecycle evidence has blockers, so Risk and Execution should stay gated.",
          "recommended_command": "astroq lifecycle check --json"
        }
      ]
    },
    "artifact_timeline_synthesis": {
      "status": "changed",
      "history_report_count": 1,
      "changed_count": 2,
      "items": [
        {
          "key": "lifecycle",
          "changed": true,
          "summary_changed": true,
          "previous_finding_count": 1,
          "current_finding_count": 0
        }
      ]
    }
  },
  "sections": [
    {"section_id": "session_summary", "title": "Session Summary", "evidence_refs": ["ev_..."]}
  ],
  "generated_at": "2026-06-14T09:30:00Z"
}
```

Report artifacts must:

- live under `var/artifacts/agent/reports/`;
- be available as both JSON and Markdown;
- cite `EvidenceRef` ids used by the session, actions, runs, and handoffs;
- record missing evidence ids explicitly in `missing_evidence`;
- include a fixed allowlist `artifact_context` for lifecycle, data-sources, strategy competition, AST intelligence, test design intelligence, and CodeGraph readiness;
- include `artifact_readiness` and `artifact_findings` sections derived from that local artifact context;
- include a deterministic `semantic_synthesis` section that turns local artifact summaries/findings into root causes, impacts, and next actions without calling an LLM;
- include a deterministic `domain_scorecard` section that maps evidence-backed root causes to Data, Research, Risk, Execution, Engineering, and Reporting desk status plus recommended `astroq` commands;
- include a deterministic `source_narratives` section that turns each fixed local artifact source into a desk-owned status, headline, evidence summary, and recommended command;
- include a deterministic `artifact_timelines` section that compares current fixed-source artifact status, summary, and finding count with the latest prior local report;
- include a deterministic `trend_synthesis` section that compares current root causes with prior local report artifacts and surfaces repeated blockers;
- include a deterministic `causal_chain_synthesis` section that connects current root causes into owner-specific chains such as data source gaps -> lifecycle blockers -> strategy evidence blockers, plus engineering/test-design risks -> release confidence risk;
- mark causal chains as recurring when their root causes also appear in prior local report artifacts, record `recurring_chain_count`, and escalate repeated blocker chains to standing owner review instead of repeating report-only observations;
- register the JSON file as `kind=report` evidence so it can be resolved and snapshotted.

### 5.7 AgentReportNotification

```json
{
  "notification_id": "notif_...",
  "report_id": "rep_...",
  "status": "sent",
  "dry_run": false,
  "channels": [
    {"channel": "telegram", "status": "sent", "missing_env": []}
  ],
  "path": "var/artifacts/agent/reports/notifications/...",
  "evidence": {"kind": "ledger"}
}
```

Notification rules:

- notification secrets are read only from process environment variables;
- supported channels are Telegram, WeChat Work, and Feishu;
- missing channel secrets produce `missing_secret` / `blocked`, not fake success;
- `--dry-run` and API `dry_run=true` write the same audit artifact without contacting providers;
- notification audit artifacts must not include raw token, chat id, or webhook values.

### 5.8 ApprovalPolicy

```json
{
  "policy_id": "policy_live_order",
  "risk_level": "live_order",
  "default_decision": "approval_required",
  "required_role": "ceo",
  "expires_after_seconds": 900,
  "reason": "Live broker orders require explicit CEO approval.",
  "approval_required": true
}
```

`GET /api/agent/policies`, `astroq agent policies --json`, and CEO Office
render the same policy rows. `read_only` and `dry_run` default to `auto_run`.
`write_data`, `write_config`, `run_backtest`, `paper_order`, and `live_order`
default to `approval_required`. `code_change` defaults to
`work_order_required`, because the Web runtime may create engineering work
orders but must not edit the repository directly.

Every action has an `expires_at` timestamp. `astroq agent expire`,
`POST /api/agent/actions/expire`, approval, and dispatch all enforce expiry:
expired actions are marked `expired`, cannot be approved, and dispatch records a
blocked run without calling the tool runner.

### 5.9 DeskAgent

```json
{
  "desk_id": "risk",
  "display_name": "Risk Desk",
  "mandate": "Review lifecycle, exposure, and execution safety.",
  "allowed_tools": ["astroq.lifecycle.check", "astroq.execution.dry_run"],
  "forbidden_actions": ["code_change"],
  "handoff_targets": ["execution", "research", "data"],
  "status": "available"
}
```

### 5.10 AgentHandoff

```json
{
  "handoff_id": "handoff_...",
  "session_id": "agt_sess_...",
  "source_message_id": "agt_msg_...",
  "source_desk": "research",
  "target_desk": "data",
  "reason": "Confirm data coverage before strategy evidence review.",
  "status": "open",
  "evidence_refs": ["ev_..."],
  "created_at": "2026-06-14T09:12:00+08:00",
  "resolved_at": ""
}
```

### 5.11 DeskResponse

```json
{
  "message": {"message_id": "agt_msg_..."},
  "answer": "Strategy evidence is blocked until Data Desk confirms coverage.",
  "confidence": 0.74,
  "evidence_refs": ["ev_..."],
  "proposed_actions": ["act_..."],
  "blockers": ["missing_score_panel"],
  "handoffs": [{"handoff_id": "handoff_...", "target_desk": "data"}],
  "reasoning": [
    {"kind": "intent_match", "planning_mode": "dynamic_multi_intent"},
    {"kind": "tool_plan", "tool_count": 4, "desk_count": 4},
    {"kind": "safety", "approval_required_count": 0},
    {"kind": "session_context", "active_action_count": 2}
  ]
}
```

### 5.12 LiveBrokerHealth

```json
{
  "broker": "miniqmt",
  "mode": "live_disabled",
  "enabled": false,
  "sdk_available": false,
  "logged_in": false,
  "account_id_masked": "",
  "permissions": [],
  "kill_switch": true,
  "paper_fallback": false,
  "sdk_gateway_configured": false,
  "sdk_gateway_error": "",
  "last_probe_at": "2026-06-14T09:40:00Z",
  "blockers": ["live_disabled"]
}
```

Readiness mode semantics:

- `live_disabled`: live mode is explicitly off or absent from config.
- `blocked`: live mode is enabled but SDK, login, permission, or kill-switch checks fail.
- `live_ready`: all readiness checks pass. This does not bypass order preview, risk gate, or CEO approval.
- `execution.live.sdk_gateway_factory` may point to `module:callable` or `module.callable`. When configured, the factory is called with `config`, `account_id`, and `broker`. Load failures, missing `submit_order`, or missing `reconcile` become `sdk_gateway_load_failed` readiness blockers.

`paper_fallback` must remain `false`; a blocked live path must never submit through PaperBroker.

### 5.13 LiveEnvironmentValidation

`GET /api/agent/live/environment` and `astroq agent live environment --json`
return a no-submit environment validation object. It is stricter than readiness:
it checks SDK module availability, account/login flags, required permissions,
kill-switch state, gateway load state, userdata-path configuration, and whether
the configured gateway can perform read-only terminal queries.

```json
{
  "status": "blocked",
  "broker": "miniqmt",
  "mode": "live_disabled",
  "enabled": false,
  "paper_fallback": false,
  "account_id_masked": "",
  "blockers": ["live_disabled", "sdk_gateway_not_configured"],
  "checks": {
    "enabled": {"status": "blocked", "blocker": "live_disabled"},
    "sdk_modules": {"status": "blocked", "blocker": "missing_sdk"},
    "account": {"status": "blocked", "blocker": "not_logged_in"},
    "permissions": {"status": "blocked", "blocker": "missing_permission"},
    "gateway": {"status": "blocked", "blocker": "sdk_gateway_not_configured"},
    "terminal_session": {"status": "blocked", "blocker": "sdk_gateway_not_configured"}
  },
  "terminal_probe": {}
}
```

When `broker.live.xtquant_gateway` is configured and the local xtquant
environment is available, `terminal_session` calls only connection and query
methods (`connect`, `subscribe`, asset, position, order, and trade queries).
It never calls `order_stock()` and never submits an order. A gateway that lacks
`validate_environment()` returns `gateway_validation_not_supported` instead of
pretending the terminal was validated.

### 5.14 LiveOrderPreview

`POST /api/agent/live/preview` and `astroq agent live preview ... --json`
return a preview object. The preview is never an order submission.

```json
{
  "status": "blocked",
  "broker": "miniqmt",
  "intent": {
    "symbol": "600000.SH",
    "side": "buy",
    "quantity": 100,
    "order_type": "limit",
    "limit_price": 10.0,
    "strategy": "manual",
    "reason": "CEO preview only",
    "evidence_refs": ["ev_demo"],
    "risk_snapshot": {}
  },
  "approval_required": true,
  "paper_fallback": false,
  "submitted": false,
  "risk_gate": {
    "passed": false,
    "blockers": ["live_disabled"],
    "checks": [
      {"name": "live_readiness", "passed": false},
      {"name": "cash", "passed": false},
      {"name": "position_concentration", "passed": false},
      {"name": "total_exposure", "passed": false},
      {"name": "daily_order_count", "passed": false},
      {"name": "tradability", "passed": false},
      {"name": "data_freshness", "passed": false},
      {"name": "broker_account_consistency", "passed": false}
    ]
  },
  "estimated_cash_effect": -1005.0,
  "estimated_position_effect": {"symbol": "600000.SH", "quantity_delta": 100}
}
```

Current preview rules:

- Live readiness blockers become preview blockers.
- Buy orders require account cash to cover notional plus estimated fees.
- `risk_snapshot` drives extended preview checks: single-position concentration, total exposure, daily order count, tradability, data freshness, broker account consistency, drawdown state, portfolio VaR/CVaR, sector concentration, and intraday limit-state.
- When live readiness is `live_ready`, missing or failing extended risk snapshot fields block preview instead of allowing an order to proceed with fake assumptions.
- Missing symbol, side, positive quantity, limit price, or evidence reference blocks preview.
- The response must always keep `approval_required=true`, `submitted=false`, and `paper_fallback=false`.

### 5.15 LiveOrderProposal and Submission

`POST /api/agent/live/proposals` and
`astroq agent live propose ... --json` create approval cards only after a
non-submitting live preview passes.

`POST /api/agent/live/actions/{action_id}/submit` and
`astroq agent live submit ACTION_ID --json`:

- require `action_type=live_order` and `risk_level=live_order`;
- block before touching the live broker adapter unless the action is approved;
- block before touching the live broker adapter when the live kill switch is active;
- re-run `MiniQmtLiveBroker.preview_order()` or the injected live adapter preview against current broker/risk state before submission;
- never fall back to `PaperBroker`;
- write `AgentRun.tool_name=live.live_order.submit`;
- write reconciliation evidence under `var/artifacts/agent/live_reconciliation/`;
- mark the action `succeeded` only when the adapter returns a submitted broker order id.

The default `MiniQmtLiveBroker.submit_order()` intentionally returns
`live_submission_not_integrated`. Production live orders can only succeed when
an explicit SDK gateway is injected/configured, readiness and risk gates pass,
and the gateway returns a broker order id. Gateway responses are masked and
hashed before they are recorded so account identifiers and secrets do not leak
into evidence artifacts.

### 5.16 LiveKillSwitch

`GET /api/agent/live/kill-switch` and
`astroq agent live kill-switch status --json` return the local kill switch
state stored under `var/artifacts/agent/live_kill_switch/state.json`.

`POST /api/agent/live/kill-switch/activate` and
`astroq agent live kill-switch activate --reason REASON --json`:

- set the local kill switch to active;
- cancel all non-terminal `live_order` actions in `proposed`,
  `approval_required`, or `approved` state;
- scan submitted live-order reconciliation evidence and call the configured
  live adapter `cancel_order()` when an already-submitted broker order id is
  known;
- record `broker_canceled_count`, `broker_cancel_failed_count`, and
  `broker_cancellations[]` in the event artifact;
- record `broker_cancel_not_supported` or adapter error details when the
  configured broker cannot perform a cancellation; unsupported cancellation
  must be blocked evidence, not fake success;
- keep historical submitted action status intact; the cancellation request is
  a separate kill-switch event, not a rewrite of the original submit ledger;
- write an event artifact under `var/artifacts/agent/live_kill_switch/events/`;
- create `EvidenceRef.label="Live kill switch"`;
- make live readiness report `mode=blocked` with
  `live_kill_switch_active`;
- make live preview, live proposal, and live submit return blocked before
  calling the live broker adapter.
- treat an unreadable or malformed kill switch state file as fail-closed
  (`status=invalid`, `active=true`) until the operator explicitly resets it.

`POST /api/agent/live/kill-switch/deactivate` and
`astroq agent live kill-switch deactivate --reason REASON --json` clear the
local block for future live paths. Deactivation does not resurrect canceled
or blocked actions; users must create a fresh approval card after the incident.

### 5.17 LiveBrokerSmoke

`POST /api/agent/live/smoke` and `astroq agent live smoke --json` run an
operator-triggered, no-submit live broker smoke test.

The smoke test:

- calls the live broker readiness probe first;
- returns `status=blocked` when readiness is not `live_ready`;
- never calls `submit_order()`;
- never falls back to PaperBroker;
- when readiness is `live_ready`, calls only
  `reconcile({"smoke_test": true, "broker_order_id": ""})` on the live adapter;
- treats `not_integrated`, `blocked`, `failed`, or `error` reconciliation
  statuses as blocked smoke results;
- writes a JSON artifact under `var/artifacts/agent/live_smoke/`;
- registers `EvidenceRef.label="Live broker smoke test"`.

A `needs_review` reconciliation result may still produce a `ready` smoke result
because it proves the configured live broker read path responded without
submitting an order. It does not prove production reconciliation is matched;
use `astroq agent live environment --json` to validate the local terminal and
account query path explicitly.

### 5.18 LiveScheduledReconciliation

`POST /api/agent/live/reconciliation` and
`astroq agent live reconcile --json` scan local `live_order` actions and write
a scheduled reconciliation artifact under
`var/artifacts/agent/live_reconciliation/scheduled/`.

The scan:

- only attempts broker reconciliation for actions with prior submitted live
  reconciliation evidence and a broker order id;
- skips approval cards or blocked actions without a submitted broker order with
  `reason=no_submitted_live_order`;
- calls the live adapter `reconcile()` method for submitted live orders;
- writes `EvidenceRef.label="Live scheduled reconciliation"`;
- always keeps `paper_fallback=false`;
- returns `ready` when all attempted reconciliations are matched or skipped,
  and `partial` when a broker reconciliation is blocked or failed.

The default MiniQMT/QMT adapter still returns `not_integrated` for real account
reconciliation unless an explicit SDK gateway is injected/configured. The
gateway reconciliation path must return structured positions/cash/open
orders/fills/mismatches and keeps `paper_fallback=false`.

The default xtquant gateway supports an optional `project_snapshot` on the
live ack or gateway config. `AgentRuntime` now attaches a preview-derived
`project_snapshot` to live submit and scheduled reconciliation ack payloads
before calling the live adapter. The snapshot includes cash after the previewed
cash effect, symbol position after the previewed quantity delta when current
quantity is available, and the submitted broker order id. Missing pieces are
listed in `project_snapshot.missing`; incomplete or absent snapshots must remain
`needs_review` instead of fabricating a matched state.

#### 5.18.1 LiveMonitor

`POST /api/agent/live/monitor` and
`astroq agent live monitor --json` run a cron-callable monitor tick. The monitor
does not submit orders. It aggregates:

- current live readiness from the configured live adapter;
- local kill-switch state;
- the scheduled reconciliation scan described above.

Each tick writes a JSON artifact under `var/artifacts/agent/live_monitor/`,
registers `EvidenceRef.label="Live monitor tick"`, and returns:

- `ready` when readiness is `live_ready` and reconciliation is ready;
- `partial` when reconciliation is partial;
- `blocked` when live readiness is blocked, disabled, or the local kill switch
  is active;
- `failed` only when the monitor itself cannot produce structured evidence.

`paper_fallback` must remain `false` in the monitor payload and nested live
payloads.

### 5.19 PaperOrderProposal and Submission

`POST /api/agent/paper/proposals` and
`astroq agent paper propose ... --json` create approval cards only after a
non-mutating PaperBroker preview passes.

```json
{
  "status": "approval_required",
  "preview": {
    "status": "preview_ready",
    "broker": "paper",
    "submitted": false,
    "approval_required": true,
    "risk_gate": {"passed": true, "blockers": []}
  },
  "action": {
    "action_type": "paper_order",
    "risk_level": "paper_order",
    "status": "approval_required",
    "parameters": {
      "paper_order_intent": {"symbol": "000001", "side": "buy"},
      "paper_order_preview": {"submitted": false}
    }
  }
}
```

Paper proposal rules:

- Preview uses the current PaperBroker state and must not call `submit_order()`.
- Blocked previews do not create approval actions.
- Passing previews create Execution Desk `paper_order` actions with preview artifact evidence.
- Dispatch before approval must record a blocked run.

`POST /api/agent/paper/actions/{action_id}/submit` and
`astroq agent paper submit ACTION_ID --json` are the only approved PaperBroker
submit path exposed by Agent Runtime.

Paper submit rules:

- The action must be `approved`, `action_type=paper_order`, and `risk_level=paper_order`.
- Runtime must re-run `PaperBroker.preview_order()` against current broker state before `submit_order()`.
- A stale preview blocks submission and writes a blocked run plus reconciliation evidence.
- A successful submit must return a `PAPER_*` order id, write `AgentRun.tool_name=paper.paper_order.submit`, register reconciliation evidence under `var/artifacts/agent/paper_reconciliation/`, and mark the action `succeeded`.
- The default PaperBroker submit path persists state, trade, and NAV rows under the active `ASTROLABE_VAR` runtime root.

`POST /api/agent/paper/actions/{action_id}/cancel` and
`astroq agent paper cancel ACTION_ID --json` are the dedicated paper-order
cancellation paths.

Paper cancel rules:

- `proposed`, `approval_required`, and `approved` paper actions are canceled as queued approval requests, write `AgentRun.tool_name=paper.paper_order.cancel`, and register reconciliation evidence with `status=queued_action_canceled`.
- Submitted paper actions keep the original action `succeeded`; cancellation is recorded as a new run and reconciliation evidence instead of rewriting the historical submission.
- Submitted paper orders only cancel when `PaperBroker.cancel_order(order_id)` succeeds; filled, missing, expired, rejected, or otherwise non-cancelable orders return `blocked` with structured reconciliation evidence.
- Paper cancellation never falls back to generic action dispatch and never pretends a broker order was canceled when the broker rejects the state transition.

## 6. Risk Levels and Default Policies

| Risk level | Examples | Default policy |
| --- | --- | --- |
| `read_only` | Health check, data status, source diff, strategy catalog. | Auto-run. |
| `dry_run` | Repair dry-run, execution dry-run, backtest dry-run. | Auto-run if bounded and non-mutating. |
| `write_data` | Backfill, repair, artifact regeneration that updates official evidence. | Approval required. |
| `write_config` | Settings updates, strategy parameter changes. | Approval required with diff evidence. |
| `run_backtest` | Full strategy competition or official evidence generation. | Approval required when long-running or official. |
| `paper_order` | PaperBroker order submission. | Approval required with risk gate pass. |
| `live_order` | MiniQMT/QMT order submission. | Approval required, live enabled, broker ready, risk gate pass, kill switch available. |
| `code_change` | Repository edits, dependency updates, migrations. | Web runtime cannot execute directly; create engineering work order. |

## 7. Evidence Rules

Agent responses about system state must include evidence for:

- Data availability, freshness, schema, and provider capability
- Strategy quality, OOS, IC/ICIR, score panels, and promotion state
- Risk readiness and blocker state
- Execution readiness, broker mode, order previews, and reconciliation
- Code architecture, duplicate implementation, and test design diagnostics
- Report conclusions

Evidence resolution must fail explicitly:

| Failure | Required status |
| --- | --- |
| Artifact path missing | `missing_evidence` |
| Artifact stale | `stale_evidence` |
| Permission missing | `missing_capability` or `no_permission` |
| Source not updated | `source_not_updated` |
| SDK missing | `not_integrated` or `missing_sdk` |
| Sample insufficient | `insufficient_samples` |

For `web_route` evidence, the resolver returns a `navigation` object only when `uri` is a safe local route such as `/system?tab=lifecycle`. External URLs and protocol-relative URLs must not become CEO Office navigation links.

## 8. Memory Contract

Memory is local, inspectable, and limited to operational records:

- Sessions
- Messages
- Action proposals
- Approval decisions
- Tool runs
- Evidence references
- Decisions and rationale
- Work orders

Memory must not store:

- API tokens
- Broker passwords
- Raw private account identifiers
- Hidden model chain-of-thought
- Unmasked provider secrets

## 9. Tool Execution Rules

- Tools must be invoked through fixed command arrays or internal callables.
- User-provided text must not become shell command text.
- Tool outputs must be summarized and linked as `AgentRun` and `EvidenceRef`.
- Long-running tools must report status through ordered run events attached to run ledger rows.
- Failed tools must produce `failed` or `blocked` actions, not disappear from the session.

## 10. Desk Routing Rules

Default routing:

| User intent | Primary desk |
| --- | --- |
| Data freshness, provider permission, source coverage | Data |
| Strategy quality, factor evidence, backtest, OOS/IC/ICIR | Research |
| Exposure, drawdown, readiness, blocked actions | Risk |
| Paper/live order, broker state, reconciliation | Execution |
| Code/design/test issue, duplicate implementation | Engineering |
| Daily/weekly summary, executive brief | Reporting |

Multi-desk requests should use explicit handoff records.

## 11. Web Contract

Long-term route changes:

| Route | Contract |
| --- | --- |
| `/` | CEO Office. |
| `/market` | Current market overview. |
| `/system?tab=lifecycle` | Lifecycle readiness detail view. |
| `/system?tab=codegraph` | CodeGraph architecture diagnostics. |
| `/system?tab=ast` | AST duplicate implementation diagnostics. |
| `/system?tab=tests` | Test design intelligence. |
| `/datahub?tab=sources` | Data source capability matrix. |
| `/strategy-lab?tab=evidence` | Strategy evidence detail. |

The CEO Office may summarize these views but must deep-link into them rather than duplicating all detail.

## 12. Live Execution Boundary

MiniQMT/QMT live execution must satisfy:

- Live mode is disabled by default.
- Missing SDK blocks live readiness.
- Missing account login blocks live readiness.
- Missing account permission blocks live readiness.
- Missing raw execution price blocks order preview.
- Risk gate failure blocks submission.
- CEO approval is required.
- No live path falls back to PaperBroker.
- Kill switch is visible and effective.
- Kill switch requests broker-side cancellation for submitted live evidence
  when the adapter supports it, and records blocked evidence otherwise.
- Submission and reconciliation write ledger entries.

## 13. Storage Paths

Planned paths:

| Path | Purpose |
| --- | --- |
| `var/db/agent_os.sqlite` | Sessions, messages, actions, approvals, runs, run events, and desk registry snapshots. |
| `var/artifacts/agent/runs/` | Run outputs. |
| `var/artifacts/agent/evidence/` | Evidence snapshots. |
| `var/artifacts/agent/memory/` | Transparent memory exports. |
| `var/artifacts/agent/reports/` | CEO briefs and audit packs. |
| `var/artifacts/agent/reports/notifications/` | Report notification audit artifacts. |

These are runtime outputs and must not be committed.

## 14. Testing Requirements

Implementation must include:

- Schema contract tests for all core objects.
- API contract tests for `/api/agent/*`.
- CLI JSON contract tests for `astroq agent *`.
- Approval policy tests for every risk level.
- Evidence resolver tests for missing, stale, fresh, and malformed evidence.
- Tool registry tests proving fixed command arrays and no arbitrary shell execution.
- Desk permission tests.
- Web tests for CEO Office states.
- Live boundary tests using fake MiniQMT/QMT adapter and SDK-missing cases.

## 15. Current Status

As of 2026-06-15:

- Foundation runtime is partially implemented in `agent_os/`.
- The local SQLite ledger stores sessions, messages, actions, evidence, run table schema, open/resolved cross-desk handoffs, and Engineering Desk work orders under `var/db/agent_os.sqlite`.
- `astroq agent sessions/session create/session show/session update/session run-readonly/message/actions/handoffs/handoff resolve/work-orders/work-order create/work-order update/action show/run/approve/reject/cancel/expire/reports/report/notify report/rhythm (--session or --all-active)/paper propose/paper submit/paper cancel/live readiness/live environment/live smoke/live preview/live propose/live submit/live reconcile/live monitor/live kill-switch status/live kill-switch activate/live kill-switch deactivate/evidence/desks/policies/memory show/memory export/memory prune/memory clear --json` is available.
- `/api/agent/sessions`, `/api/agent/sessions/{session_id}` `GET/PATCH`, `/api/agent/sessions/{session_id}/stream`, `/api/agent/sessions/{session_id}/run-readonly`, `/api/agent/actions`, `/api/agent/actions/expire`, `/api/agent/handoffs`, `/api/agent/handoffs/{handoff_id}/resolve`, `/api/agent/work-orders`, `/api/agent/work-orders/{work_order_id}`, `/api/agent/actions/{action_id}/run`, `/api/agent/actions/{action_id}/cancel`, `/api/agent/runs/{run_id}`, `/api/agent/runs/{run_id}/stream`, `/api/agent/evidence/{evidence_id}`, `/api/agent/desks`, `/api/agent/policies`, `/api/agent/paper/proposals`, `/api/agent/paper/actions/{action_id}/submit`, `/api/agent/paper/actions/{action_id}/cancel`, `/api/agent/live/readiness`, `/api/agent/live/environment`, `/api/agent/live/smoke`, `/api/agent/live/preview`, `/api/agent/live/proposals`, `/api/agent/live/actions/{action_id}/submit`, `/api/agent/live/reconciliation`, `/api/agent/live/monitor`, `/api/agent/live/kill-switch`, `/api/agent/live/kill-switch/activate`, `/api/agent/live/kill-switch/deactivate`, `/api/agent/reports`, `/api/agent/reports/{report_id}/notify`, `/api/agent/reports/rhythm`, `/api/agent/reports/rhythm/scheduled`, `/api/agent/memory`, `/api/agent/memory/export`, `/api/agent/memory/prune`, and `/api/agent/memory/clear` are available.
- Action dispatch is intentionally bounded to fixed `AgentToolRegistry` command arrays. Read-only actions can run; approval-required actions are blocked until approved; approved fixed-registry templated commands bind only tool-declared safe parameters.
- Fixed command dispatch records ordered run events for queued/running/stdout/stderr/terminal state. Real subprocess dispatch records stdout/stderr line chunks as they arrive and then writes the terminal event. `/api/agent/runs/{run_id}`, `/api/agent/runs/{run_id}/stream`, and scoped action detail expose the event timeline, while session summaries keep runs compact.
- Fixed registry tools are checked against desk policy at both action proposal and dispatch time. A stale or externally inserted action with a tool outside the desk scope is marked `blocked` and does not call the runner.
- The fixed registry covers all desk-declared tools, including lifecycle checks, data status, data source capability listing and registry diff, data repair dry-run/approved repair, strategy catalog, strategy competition evidence, backtest dry-run, execution dry-run, AST diagnostics, test design intelligence, docs check, and report generation.
- Deterministic desk workflows route common CEO intents to specific safe tools, including data source registry diff, Data Desk repair dry-run plus approval-required write action, 12-strategy competition evidence, Research strategy-blocker diagnosis across DataHub health and lifecycle gates, Engineering Desk code/bug requests into work orders plus AST/test-design diagnostics, backtest dry-run, test design intelligence, and documentation hygiene checks. Reporting daily-brief intent performs a bounded cross-desk orchestration step by proposing separate Data, Research, and Risk read-only actions with distinct evidence references. Reporting portfolio-review intent proposes Research strategy competition evidence, Risk lifecycle readiness, and Execution dry-run actions. Reporting mixed CEO review requests can produce deterministic `dynamic_multi_intent` plans that combine Data source registry diff, Research strategy competition, Risk lifecycle, Execution dry-run, and Engineering test/AST diagnostics while preserving fixed tool ids and handoffs. Broad CEO priority requests can produce `artifact_aware` plans from fixed local artifact context, mapping root causes such as data source gaps, lifecycle blockers, strategy evidence blockers, AST risks, and test design risks into owner-desk safe actions. CEO follow-up requests such as "next step" or "continue" can produce `adaptive_session` plans from current session backlog, turning approval-required actions, open handoffs, and open Engineering work orders into safe re-check actions and owner-desk handoffs without auto-approving writes or trades. Requests that combine follow-up language with current evidence/priority language can produce `adaptive_artifact` plans that fuse session backlog with local artifact root causes, dedupe overlapping safe actions, and expose both `session_backlog` and `artifact_context` reasoning. Open-ended company-wide CEO operating requests can produce `open_ended_adaptive` diagnostic plans across Data, Research, Risk, Execution, and Engineering fixed-registry tools; these plans only propose read-only/dry-run actions and report `open_ended_plan_is_diagnostic_only` as a blocker for direct writes or trades. Workflow previews and desk responses include deterministic reasoning rows for intent match, tool plan, safety, evidence plan, artifact context, session backlog, context fusion, open goal decomposition, and current session context. Session-level safe workflow runners can dispatch proposed `read_only` and `dry_run` actions while skipping approval-required write/trading actions.
- Desk responses can persist structured `answer/confidence/evidence_refs/proposed_actions/blockers/handoffs/reasoning`; invalid handoff targets are rejected by runtime desk policy; open handoffs can be resolved with an audit timestamp.
- Web-route evidence resolves to safe local navigation metadata, repository-local file/code evidence resolves to CodeGraph file navigation with optional line numbers, local API evidence resolves only `/api/...` GET endpoints, and CLI evidence resolves only inert `astroq`/`.venv/bin/astroq` command metadata. Existing external files can be snapshotted and hashed, but they do not produce CEO Office navigation links.
- CEO reports can be generated as JSON/Markdown artifacts, registered as report evidence, listed through CLI/API, and shown as CEO Office report cards. Dedicated templates cover daily, weekly, audit, data quality, risk, execution reconciliation, engineering digest, and release audit reports; each report includes fixed allowlist artifact context for lifecycle, data-sources, strategy competition, AST intelligence, test design intelligence, and CodeGraph readiness. Reports include deterministic semantic synthesis that maps artifact findings into root causes, impacts, and next actions, deterministic desk-level domain scorecards with recommended `astroq` commands, deterministic source narratives that turn each fixed artifact into a desk-owned status/headline/evidence summary, deterministic artifact-specific timeline synthesis comparing current artifacts with the latest prior report, deterministic trend synthesis that compares current root causes with prior local report artifacts and surfaces repeated blockers, and deterministic causal-chain synthesis that links related root causes into owner desks and next actions. Repeated causal chains are marked with history metadata, counted in `recurring_chain_count`, and escalated to standing owner review. CEO Office can generate a selected template, run due templates through the explicit operating-rhythm runner, trigger the scheduled active-session rhythm tick, or send/dry-run report notifications. Scheduled ticks write audit artifacts under `var/artifacts/agent/reports/scheduled/`; notifications write audit artifacts under `var/artifacts/agent/reports/notifications/` and read only system environment variables.
- PaperBroker order proposal, approved submission, and cancellation are available through CLI/API. Proposal writes preview artifact evidence and creates an approval-required `paper_order` action only when the non-mutating preview passes; submission requires approval, re-runs preview/risk gates, blocks stale previews, writes run/reconciliation evidence, persists default PaperBroker state on success, and exposes paper reconciliation summaries on action detail. Cancellation writes dedicated `paper.paper_order.cancel` runs and reconciliation evidence for queued approval requests or broker-confirmed active order cancellations.
- MiniQMT/QMT readiness probing is available and defaults to `live_disabled`; missing SDK, login, permission, or disabled kill switch returns `blocked`, and `paper_fallback` is always false.
- MiniQMT/QMT live no-submit environment validation and smoke tests, order preview, proposal, approved-submit contract, scheduled reconciliation scan, cron-callable live monitor tick, explicit SDK gateway bridge, config-based gateway factory loading, xtquant project snapshot comparison, and local kill switch operations are available through CLI/API. The path never falls back to PaperBroker, always requires approval for submit, re-runs preview/risk gates before submit, writes live smoke/reconciliation/monitor evidence, blocks before broker calls when kill switch is active, and defaults to `live_submission_not_integrated` / `not_integrated` unless a gateway is explicitly injected/configured. Kill-switch activation cancels queued live actions, scans submitted live evidence, requests broker-side cancellation when the configured adapter supports `cancel_order()`, and records unsupported or failed broker cancellation as blocked evidence rather than fake success. Preview risk gates now include cash, position concentration, total exposure, daily order count, tradability, data freshness, broker account consistency, drawdown, VaR, CVaR, sector concentration, and intraday limit-state checks.
- Runtime live submit and scheduled reconciliation attach preview-derived project ledger snapshots to ack payloads before adapter reconciliation. Missing cash, position quantity, position delta, symbol, or broker order id is preserved as structured `project_snapshot.missing`, and the xtquant gateway treats incomplete snapshots as `needs_review`.
- Existing Web System pages already provide CodeGraph, AST diagnostics, test design intelligence, lifecycle readiness, and data source capability evidence.
- Existing CLI commands already provide many deterministic tools that future desk agents can call.
- CEO Office is implemented as the default `/` route with session creation, target desk selection for CEO messages, message entry, session safe workflow runner, desk status, desk drill-down for mandates/tools/evidence requirements/related work, explicit approval policy display, approval queue display, action detail, and run event timeline display; `/market` carries the market overview.
- An opt-in semantic planner adapter can draft ambiguous CEO plans, but its output is filtered to known `read_only` / `dry_run` fixed-registry tools, scoped to allowed desks, and marked for manual review; autonomous unbounded desk reasoning beyond fixed-registry safety boundaries is not yet implemented.
