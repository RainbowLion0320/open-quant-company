# Spec: Agent Company OS

> Version: 0.1
> Updated: 2026-06-14
> Status: phased implementation contract
> Related: [PRD](../product/prd.md), [Web Platform](05-web-platform.md), [Master Roadmap](../project/agent-company/00-master-roadmap.md)

## 1. Purpose

Agent Company OS is the planned local-first operating layer for Open Quant Company. It lets the human user act as CEO while desk agents coordinate data, research, risk, execution, engineering, and reporting work.

This spec defines behavior contracts for the Agent Company OS rollout. Foundation runtime pieces, the first CEO Office page, deterministic desk routing, bounded fixed-command dispatch, transparent memory governance, evidence-cited report artifacts, default-disabled live readiness probing, and live order preview risk gating are implemented first; streaming, full operating-rhythm report cadence, advanced desk reasoning, and live order submission/reconciliation remain planned until their phase lands.

## 2. Product Contract

Agent Company OS must provide:

- A CEO Office Web page as the default `/` route.
- A local Agent Runtime for sessions, messages, actions, approvals, runs, memory, and evidence.
- Desk agents with explicit mandates and tool permissions.
- Approval-gated state-changing actions.
- Evidence references for agent claims.
- Transparent local memory that can be inspected, exported, pruned, and cleared.
- MiniQMT/QMT live execution as a default-disabled, approval-gated capability; the current foundation stops at readiness and non-submitting order preview.

## 3. API Surface

All endpoints are planned under `/api/agent/*`.

| Method | Endpoint | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/agent/sessions` | List agent sessions. | Implemented |
| `POST` | `/api/agent/sessions` | Create a new session. | Implemented |
| `GET` | `/api/agent/sessions/{session_id}` | Read a session with messages and linked actions. | Implemented |
| `PATCH` | `/api/agent/sessions/{session_id}` | Rename, archive, tag, or update session metadata. | Implemented |
| `POST` | `/api/agent/sessions/{session_id}/messages` | Add a CEO message, create a deterministic desk response, and link evidence/actions/handoffs. | Implemented |
| `GET` | `/api/agent/actions` | List actions with filters for session and future status/desk/risk filters. | Implemented |
| `GET` | `/api/agent/handoffs` | List cross-desk handoff ledger rows, optionally scoped to a session. | Implemented |
| `POST` | `/api/agent/handoffs/{handoff_id}/resolve` | Mark a cross-desk handoff as resolved and write `resolved_at`. | Implemented |
| `GET` | `/api/agent/actions/{action_id}` | Read an action and approval state. | Implemented |
| `POST` | `/api/agent/actions/{action_id}/approve` | Approve a pending action. | Implemented |
| `POST` | `/api/agent/actions/{action_id}/reject` | Reject a pending action with reason. | Implemented |
| `POST` | `/api/agent/actions/{action_id}/run` | Dispatch a safe or approved fixed-registry action and write a run ledger row. | Implemented for bounded fixed commands |
| `POST` | `/api/agent/actions/{action_id}/cancel` | Cancel a proposed, approval-pending, or approved action before dispatch reaches a terminal status. | Implemented |
| `GET` | `/api/agent/runs/{run_id}` | Read a tool or workflow run. | Implemented |
| `GET` | `/api/agent/evidence/{evidence_id}` | Resolve an evidence reference. | Implemented |
| `GET` | `/api/agent/desks` | List desk agents, health, allowed tools, and current blockers. | Implemented |
| `GET` | `/api/agent/live/readiness` | Report MiniQMT/QMT live readiness without submitting orders. | Implemented readiness probe |
| `POST` | `/api/agent/live/preview` | Preview a MiniQMT/QMT live order with readiness, cash gate, broker impact, and `submitted=false`. | Implemented preview gate |
| `GET` | `/api/agent/reports` | List generated CEO reports, optionally scoped to a session. | Implemented |
| `POST` | `/api/agent/reports` | Generate a CEO report artifact and register report evidence. | Implemented |
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
| `astroq agent message --session SESSION_ID --desk DESK --text TEXT --json` | Add a CEO message and return the deterministic desk response. | Implemented |
| `astroq agent actions --session SESSION_ID --json` | List session actions. | Implemented |
| `astroq agent handoffs --session SESSION_ID --json` | List cross-desk handoffs. | Implemented |
| `astroq agent handoff resolve HANDOFF_ID --json` | Mark a cross-desk handoff as resolved. | Implemented |
| `astroq agent action show ACTION_ID --json` | Show action details. | Implemented |
| `astroq agent run ACTION_ID --json` | Dispatch a safe or approved action through the fixed tool registry. | Implemented for bounded fixed commands |
| `astroq agent approve ACTION_ID --json` | Approve an action. | Implemented |
| `astroq agent reject ACTION_ID --reason REASON --json` | Reject an action. | Implemented |
| `astroq agent cancel ACTION_ID --reason REASON --json` | Cancel a proposed, approval-pending, or approved action before terminal completion. | Implemented |
| `astroq agent expire --session SESSION_ID --json` | Mark expired queued actions. | Implemented |
| `astroq agent reports --session SESSION_ID --json` | List generated CEO reports. | Implemented |
| `astroq agent report daily --session SESSION_ID --json` | Generate an evidence-cited daily CEO brief. | Implemented |
| `astroq agent live readiness --json` | Report MiniQMT/QMT live readiness and blockers without PaperBroker fallback. | Implemented readiness probe |
| `astroq agent live preview --symbol SYMBOL --side buy\|sell --quantity N --limit-price PRICE --evidence EVIDENCE_ID --json` | Preview a live limit order without submission, including approval requirement, readiness blockers, cash gate, and estimated broker impact. | Implemented preview gate |
| `astroq agent evidence EVIDENCE_ID --json` | Resolve evidence. | Implemented |
| `astroq agent desks --json` | List desk registry and health. | Implemented |
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

### 5.4 AgentRun

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

### 5.5 EvidenceRef

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
- register the JSON file as `kind=report` evidence so it can be resolved and snapshotted.

### 5.7 ApprovalPolicy

```json
{
  "policy_id": "policy_live_order",
  "risk_level": "live_order",
  "default_decision": "approval_required",
  "required_role": "ceo",
  "expires_after_seconds": 900,
  "reason": "Live broker orders require explicit CEO approval."
}
```

Every action has an `expires_at` timestamp. `astroq agent expire`,
`POST /api/agent/actions/expire`, approval, and dispatch all enforce expiry:
expired actions are marked `expired`, cannot be approved, and dispatch records a
blocked run without calling the tool runner.

### 5.8 DeskAgent

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

### 5.9 AgentHandoff

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

### 5.10 DeskResponse

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

### 5.11 LiveBrokerHealth

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

### 5.12 LiveOrderPreview

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
    "checks": [{"name": "live_readiness", "passed": false}]
  },
  "estimated_cash_effect": -1005.0,
  "estimated_position_effect": {"symbol": "600000.SH", "quantity_delta": 100}
}
```

Current preview rules:

- Live readiness blockers become preview blockers.
- Buy orders require account cash to cover notional plus estimated fees.
- Missing symbol, side, positive quantity, limit price, or evidence reference blocks preview.
- The response must always keep `approval_required=true`, `submitted=false`, and `paper_fallback=false`.

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
- Long-running tools must report status through run ledger updates.
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
| `var/db/agent_os.sqlite` | Sessions, messages, actions, approvals, runs, and desk registry snapshots. |
| `var/artifacts/agent/runs/` | Run outputs. |
| `var/artifacts/agent/evidence/` | Evidence snapshots. |
| `var/artifacts/agent/memory/` | Transparent memory exports. |
| `var/artifacts/agent/reports/` | CEO briefs and audit packs. |

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

As of 2026-06-14:

- Foundation runtime is partially implemented in `agent_os/`.
- The local SQLite ledger stores sessions, messages, actions, evidence, run table schema, and open/resolved cross-desk handoffs under `var/db/agent_os.sqlite`.
- `astroq agent sessions/session create/session show/session update/message/actions/handoffs/handoff resolve/action show/run/approve/reject/cancel/expire/reports/report/live readiness/live preview/evidence/desks/memory show/memory export/memory prune/memory clear --json` is available.
- `/api/agent/sessions`, `/api/agent/sessions/{session_id}` `GET/PATCH`, `/api/agent/actions`, `/api/agent/actions/expire`, `/api/agent/handoffs`, `/api/agent/handoffs/{handoff_id}/resolve`, `/api/agent/actions/{action_id}/run`, `/api/agent/actions/{action_id}/cancel`, `/api/agent/runs/{run_id}`, `/api/agent/evidence/{evidence_id}`, `/api/agent/desks`, `/api/agent/live/readiness`, `/api/agent/live/preview`, `/api/agent/reports`, `/api/agent/memory`, `/api/agent/memory/export`, `/api/agent/memory/prune`, and `/api/agent/memory/clear` are available.
- Action dispatch is intentionally bounded to fixed `AgentToolRegistry` command arrays. Read-only actions can run; approval-required actions are blocked until approved; approved fixed-registry templated commands bind only tool-declared safe parameters.
- Fixed registry tools are checked against desk policy at both action proposal and dispatch time. A stale or externally inserted action with a tool outside the desk scope is marked `blocked` and does not call the runner.
- Desk responses can persist structured `answer/confidence/evidence_refs/proposed_actions/blockers/handoffs`; invalid handoff targets are rejected by runtime desk policy; open handoffs can be resolved with an audit timestamp.
- Web-route evidence resolves to safe local navigation metadata, and CEO Office can render an evidence link into the related Web view.
- CEO reports can be generated as JSON/Markdown artifacts, registered as report evidence, listed through CLI/API, and shown as CEO Office report cards.
- MiniQMT/QMT readiness probing is available and defaults to `live_disabled`; missing SDK, login, permission, or disabled kill switch returns `blocked`, and `paper_fallback` is always false.
- MiniQMT/QMT live order preview is available through CLI/API. It never submits, never falls back to PaperBroker, always requires approval, and blocks on readiness, invalid intent, missing evidence, or insufficient cash.
- Existing Web System pages already provide CodeGraph, AST diagnostics, test design intelligence, lifecycle readiness, and data source capability evidence.
- Existing CLI commands already provide many deterministic tools that future desk agents can call.
- CEO Office is implemented as the default `/` route with session creation, message entry, desk status, and approval queue display; `/market` carries the market overview.
- Actual advanced desk reasoning, broad tool execution, streaming updates, full operating-rhythm report cadence, and MiniQMT/QMT live submission/reconciliation are not yet implemented.
