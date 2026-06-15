# Spec: Agent Company OS

> Version: 0.1
> Updated: 2026-06-14
> Status: phased implementation contract
> Related: [PRD](../product/prd.md), [Web Platform](05-web-platform.md), [Master Roadmap](../project/agent-company/00-master-roadmap.md)

## 1. Purpose

Agent Company OS is the planned local-first operating layer for Open Quant Company. It lets the human user act as CEO while desk agents coordinate data, research, risk, execution, engineering, and reporting work.

This spec defines behavior contracts for the Agent Company OS rollout. Foundation runtime pieces, the first CEO Office page, deterministic desk routing, bounded fixed-command dispatch, run event timelines, transparent memory governance, evidence-cited report artifacts with CEO Office template selection, fixed cross-artifact report context aggregation, explicit operating-rhythm report runs, cron-callable scheduled report rhythm ticks, env-only report notification triggers, paper order preview/proposal/approved-submit/cancel cards with inline paper reconciliation summaries, default-disabled live readiness probing, live order preview risk gating, approval-gated live submit/reconciliation contracts, desk-declared fixed tool registry coverage, deterministic intent-to-tool routing, Data Desk repair dry-run plus approval workflow, Research strategy-blocker cross-desk diagnosis, Engineering Desk code/bug work-order triage, daily-brief cross-desk orchestration, and portfolio review cross-desk orchestration are implemented first; realtime streaming, advanced semantic report synthesis, advanced desk reasoning, real MiniQMT/QMT SDK submission, and continuous live reconciliation remain planned until their phase lands.

## 2. Product Contract

Agent Company OS must provide:

- A CEO Office Web page as the default `/` route.
- A local Agent Runtime for sessions, messages, actions, approvals, runs, memory, and evidence.
- Desk agents with explicit mandates and tool permissions.
- Approval-gated state-changing actions.
- Evidence references for agent claims.
- Transparent local memory that can be inspected, exported, pruned, and cleared.
- MiniQMT/QMT live execution as a default-disabled, approval-gated capability; the current foundation includes readiness, non-submitting order preview, live proposal cards, and a fail-closed approved-submit/reconciliation contract. Real SDK submission remains not integrated by default.

## 3. API Surface

All endpoints are planned under `/api/agent/*`.

| Method | Endpoint | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/agent/sessions` | List agent sessions. | Implemented |
| `POST` | `/api/agent/sessions` | Create a new session. | Implemented |
| `GET` | `/api/agent/sessions/{session_id}` | Read a session with messages and linked actions. | Implemented |
| `PATCH` | `/api/agent/sessions/{session_id}` | Rename, archive, tag, or update session metadata. | Implemented |
| `POST` | `/api/agent/sessions/{session_id}/run-readonly` | Dispatch proposed safe `read_only` / `dry_run` actions for one session and skip approval-required, write, and trading actions. | Implemented |
| `POST` | `/api/agent/sessions/{session_id}/messages` | Add a CEO message, create a deterministic desk response, and link evidence/actions/handoffs. | Implemented |
| `GET` | `/api/agent/actions` | List actions with filters for session and future status/desk/risk filters. | Implemented |
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
| `GET` | `/api/agent/evidence/{evidence_id}` | Resolve an evidence reference. | Implemented |
| `GET` | `/api/agent/desks` | List desk agents, health, allowed tools, and current blockers. | Implemented |
| `GET` | `/api/agent/policies` | List explicit approval policies for every risk level. | Implemented |
| `POST` | `/api/agent/paper/proposals` | Preview and propose a PaperBroker order as an approval-required action without submitting it. | Implemented proposal gate |
| `POST` | `/api/agent/paper/actions/{action_id}/submit` | Submit an approved PaperBroker order action after re-running preview/risk gates and writing reconciliation evidence. | Implemented approved submit gate |
| `POST` | `/api/agent/paper/actions/{action_id}/cancel` | Cancel a queued paper approval request or a submitted PaperBroker order when broker state still permits cancellation. | Implemented cancellation gate |
| `GET` | `/api/agent/live/readiness` | Report MiniQMT/QMT live readiness without submitting orders. | Implemented readiness probe |
| `POST` | `/api/agent/live/preview` | Preview a MiniQMT/QMT live order with readiness, extended risk gate, broker impact, and `submitted=false`. | Implemented preview gate |
| `POST` | `/api/agent/live/proposals` | Create an approval-required live order action only after live preview passes. | Implemented proposal gate |
| `POST` | `/api/agent/live/actions/{action_id}/submit` | Submit an approved live order action through the live broker adapter and write reconciliation evidence; default MiniQMT adapter fails closed until real SDK submission is wired. | Implemented contract, real adapter pending |
| `POST` | `/api/agent/live/reconciliation` | Scan submitted live order evidence, call live adapter reconciliation, and write a scheduled reconciliation artifact. | Implemented scheduled scan |
| `GET` | `/api/agent/live/kill-switch` | Read the local live kill switch state. | Implemented |
| `POST` | `/api/agent/live/kill-switch/activate` | Activate the local live kill switch, cancel queued live actions, and block future live paths before broker calls. | Implemented |
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
| `astroq agent actions --session SESSION_ID --json` | List session actions. | Implemented |
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
| `astroq agent live preview --symbol SYMBOL --side buy\|sell --quantity N --limit-price PRICE --evidence EVIDENCE_ID --json` | Preview a live limit order without submission, including approval requirement, readiness blockers, extended risk gate, and estimated broker impact. | Implemented preview gate |
| `astroq agent live propose --session SESSION_ID --symbol SYMBOL --side buy\|sell --quantity N --limit-price PRICE --evidence EVIDENCE_ID --json` | Create an approval-required live order proposal when live preview passes. | Implemented proposal gate |
| `astroq agent live submit ACTION_ID --json` | Submit an approved live order action through the live adapter, re-running preview/risk gates and writing reconciliation evidence. | Implemented contract, real adapter pending |
| `astroq agent live reconcile --session SESSION_ID --json` | Scan submitted live order evidence and write scheduled reconciliation evidence. | Implemented scheduled scan |
| `astroq agent live kill-switch status --json` | Read the local live kill switch state. | Implemented |
| `astroq agent live kill-switch activate --reason REASON --json` | Activate the local live kill switch and cancel queued live actions. | Implemented |
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
    ]
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
  "handoffs": [{"handoff_id": "handoff_...", "target_desk": "data"}]
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
  "last_probe_at": "2026-06-14T09:40:00Z",
  "blockers": ["live_disabled"]
}
```

Readiness mode semantics:

- `live_disabled`: live mode is explicitly off or absent from config.
- `blocked`: live mode is enabled but SDK, login, permission, or kill-switch checks fail.
- `live_ready`: all readiness checks pass. This does not bypass order preview, risk gate, or CEO approval.

`paper_fallback` must remain `false`; a blocked live path must never submit through PaperBroker.

### 5.13 LiveOrderPreview

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
- `risk_snapshot` drives extended preview checks: single-position concentration, total exposure, daily order count, tradability, data freshness, and broker account consistency.
- When live readiness is `live_ready`, missing or failing extended risk snapshot fields block preview instead of allowing an order to proceed with fake assumptions.
- Missing symbol, side, positive quantity, limit price, or evidence reference blocks preview.
- The response must always keep `approval_required=true`, `submitted=false`, and `paper_fallback=false`.

### 5.14 LiveOrderProposal and Submission

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
`live_submission_not_integrated`; a real broker submitter must be explicitly
wired before production live orders can succeed.

### 5.15 LiveKillSwitch

`GET /api/agent/live/kill-switch` and
`astroq agent live kill-switch status --json` return the local kill switch
state stored under `var/artifacts/agent/live_kill_switch/state.json`.

`POST /api/agent/live/kill-switch/activate` and
`astroq agent live kill-switch activate --reason REASON --json`:

- set the local kill switch to active;
- cancel all non-terminal `live_order` actions in `proposed`,
  `approval_required`, or `approved` state;
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

### 5.16 LiveScheduledReconciliation

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
reconciliation until the actual SDK bridge is wired.

### 5.17 PaperOrderProposal and Submission

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
- `astroq agent sessions/session create/session show/session update/session run-readonly/message/actions/handoffs/handoff resolve/work-orders/work-order create/work-order update/action show/run/approve/reject/cancel/expire/reports/report/notify report/rhythm (--session or --all-active)/paper propose/paper submit/paper cancel/live readiness/live preview/live propose/live submit/live reconcile/live kill-switch status/live kill-switch activate/live kill-switch deactivate/evidence/desks/policies/memory show/memory export/memory prune/memory clear --json` is available.
- `/api/agent/sessions`, `/api/agent/sessions/{session_id}` `GET/PATCH`, `/api/agent/sessions/{session_id}/run-readonly`, `/api/agent/actions`, `/api/agent/actions/expire`, `/api/agent/handoffs`, `/api/agent/handoffs/{handoff_id}/resolve`, `/api/agent/work-orders`, `/api/agent/work-orders/{work_order_id}`, `/api/agent/actions/{action_id}/run`, `/api/agent/actions/{action_id}/cancel`, `/api/agent/runs/{run_id}`, `/api/agent/evidence/{evidence_id}`, `/api/agent/desks`, `/api/agent/policies`, `/api/agent/paper/proposals`, `/api/agent/paper/actions/{action_id}/submit`, `/api/agent/paper/actions/{action_id}/cancel`, `/api/agent/live/readiness`, `/api/agent/live/preview`, `/api/agent/live/proposals`, `/api/agent/live/actions/{action_id}/submit`, `/api/agent/live/reconciliation`, `/api/agent/live/kill-switch`, `/api/agent/live/kill-switch/activate`, `/api/agent/live/kill-switch/deactivate`, `/api/agent/reports`, `/api/agent/reports/{report_id}/notify`, `/api/agent/reports/rhythm`, `/api/agent/reports/rhythm/scheduled`, `/api/agent/memory`, `/api/agent/memory/export`, `/api/agent/memory/prune`, and `/api/agent/memory/clear` are available.
- Action dispatch is intentionally bounded to fixed `AgentToolRegistry` command arrays. Read-only actions can run; approval-required actions are blocked until approved; approved fixed-registry templated commands bind only tool-declared safe parameters.
- Fixed command dispatch records ordered run events for queued/running/stdout/stderr/terminal state. `/api/agent/runs/{run_id}` and scoped action detail include the event timeline, while session summaries keep runs compact.
- Fixed registry tools are checked against desk policy at both action proposal and dispatch time. A stale or externally inserted action with a tool outside the desk scope is marked `blocked` and does not call the runner.
- The fixed registry covers all desk-declared tools, including lifecycle checks, data status, data source capability listing and registry diff, data repair dry-run/approved repair, strategy catalog, strategy competition evidence, backtest dry-run, execution dry-run, AST diagnostics, test design intelligence, docs check, and report generation.
- Deterministic desk workflows route common CEO intents to specific safe tools, including data source registry diff, Data Desk repair dry-run plus approval-required write action, 12-strategy competition evidence, Research strategy-blocker diagnosis across DataHub health and lifecycle gates, Engineering Desk code/bug requests into work orders plus AST/test-design diagnostics, backtest dry-run, test design intelligence, and documentation hygiene checks. Reporting daily-brief intent performs a bounded cross-desk orchestration step by proposing separate Data, Research, and Risk read-only actions with distinct evidence references. Reporting portfolio-review intent proposes Research strategy competition evidence, Risk lifecycle readiness, and Execution dry-run actions. Session-level safe workflow runners can dispatch proposed `read_only` and `dry_run` actions while skipping approval-required write/trading actions.
- Desk responses can persist structured `answer/confidence/evidence_refs/proposed_actions/blockers/handoffs`; invalid handoff targets are rejected by runtime desk policy; open handoffs can be resolved with an audit timestamp.
- Web-route evidence resolves to safe local navigation metadata, repository-local file/code evidence resolves to CodeGraph file navigation with optional line numbers, local API evidence resolves only `/api/...` GET endpoints, and CLI evidence resolves only inert `astroq`/`.venv/bin/astroq` command metadata. Existing external files can be snapshotted and hashed, but they do not produce CEO Office navigation links.
- CEO reports can be generated as JSON/Markdown artifacts, registered as report evidence, listed through CLI/API, and shown as CEO Office report cards. Dedicated templates cover daily, weekly, audit, data quality, risk, execution reconciliation, engineering digest, and release audit reports; each report includes fixed allowlist artifact context for lifecycle, data-sources, strategy competition, AST intelligence, test design intelligence, and CodeGraph readiness. CEO Office can generate a selected template, run due templates through the explicit operating-rhythm runner, trigger the scheduled active-session rhythm tick, or send/dry-run report notifications. Scheduled ticks write audit artifacts under `var/artifacts/agent/reports/scheduled/`; notifications write audit artifacts under `var/artifacts/agent/reports/notifications/` and read only system environment variables.
- PaperBroker order proposal, approved submission, and cancellation are available through CLI/API. Proposal writes preview artifact evidence and creates an approval-required `paper_order` action only when the non-mutating preview passes; submission requires approval, re-runs preview/risk gates, blocks stale previews, writes run/reconciliation evidence, persists default PaperBroker state on success, and exposes paper reconciliation summaries on action detail. Cancellation writes dedicated `paper.paper_order.cancel` runs and reconciliation evidence for queued approval requests or broker-confirmed active order cancellations.
- MiniQMT/QMT readiness probing is available and defaults to `live_disabled`; missing SDK, login, permission, or disabled kill switch returns `blocked`, and `paper_fallback` is always false.
- MiniQMT/QMT live order preview, proposal, approved-submit contract, scheduled reconciliation scan, and local kill switch operations are available through CLI/API. The path never falls back to PaperBroker, always requires approval, re-runs preview/risk gates before submit, writes live reconciliation evidence, blocks before broker calls when kill switch is active, and defaults to `live_submission_not_integrated` / `not_integrated` until a real MiniQMT/QMT submit/reconcile adapter is wired.
- Existing Web System pages already provide CodeGraph, AST diagnostics, test design intelligence, lifecycle readiness, and data source capability evidence.
- Existing CLI commands already provide many deterministic tools that future desk agents can call.
- CEO Office is implemented as the default `/` route with session creation, target desk selection for CEO messages, message entry, session safe workflow runner, desk status, desk drill-down for mandates/tools/evidence requirements/related work, explicit approval policy display, approval queue display, action detail, and run event timeline display; `/market` carries the market overview.
- Actual advanced desk reasoning, dynamic cross-tool workflow planning beyond bounded deterministic paths, realtime Web streaming, advanced semantic report synthesis, and real MiniQMT/QMT SDK submission/reconciliation are not yet implemented.
