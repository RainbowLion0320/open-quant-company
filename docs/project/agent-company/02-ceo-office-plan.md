# Agent Company OS Phase 2 - CEO Office Web Plan

> Status: planned implementation phase
> Created: 2026-06-14
> Parent roadmap: [00-master-roadmap.md](00-master-roadmap.md)
> Depends on: [01-foundation-plan.md](01-foundation-plan.md)

## 1. Goal

Make the Web UI's default page the daily operating room for the human CEO. The CEO Office should let the user ask questions, review desk recommendations, approve or reject actions, and jump into detailed evidence views without losing access to the existing DataHub, Strategy Lab, Pipeline, System, and Portfolio pages.

The CEO Office is not a marketing landing page and not a generic chat page. It is an operational command surface.

## 2. Route Plan

Target routing:

| Route | Target page |
| --- | --- |
| `/` | CEO Office conversation and action control page. |
| `/market` | Current market overview, including regime orb and macro/sector summary. |
| `/research` | Market research. |
| `/strategy-lab` | Strategy catalog, evidence, and backtest pages. |
| `/portfolio` | Portfolio and execution. |
| `/pipeline` | Pipeline transparency. |
| `/datahub` | Data health and source capability pages. |
| `/system` | System intelligence and configuration pages. |

The migration must preserve direct deep links. Existing `/` market links should be redirected or updated during implementation.

## 3. Page Layout

The CEO Office should use a dense operational layout:

| Region | Content |
| --- | --- |
| Header | System mode, broker mode, data freshness, lifecycle blockers, current session. |
| Conversation timeline | CEO messages, desk responses, tool summaries, cited evidence, action cards. |
| Action queue | Pending approvals, blocked actions, running actions, recent outcomes. |
| Desk rail | Data, Research, Risk, Execution, Engineering, Reporting status and latest recommendation. |
| Evidence drawer | Evidence details, artifact metadata, Web deep links, CLI command reproduction. |
| Context footer | Recommended next commands and stale artifact warnings. |

## 4. Conversation Behavior

Each desk response must be structured:

- Direct answer
- Evidence references
- Recommended action, if any
- Required approval, if any
- Blockers, if any
- Deep links into existing Web pages

Examples:

| User asks | Expected routing |
| --- | --- |
| "今天系统该做什么？" | Reporting Desk gathers lifecycle, data, strategy, and risk evidence; may hand off to Data/Risk/Research desks. |
| "为什么策略都被阻断？" | Research Desk and Data Desk explain missing score panels, IC/ICIR evidence, stale data, or capability gaps. |
| "补一下缺的数据" | Data Desk creates dry-run evidence first, then proposes a write action requiring approval. |
| "可以下单吗？" | Execution Desk runs readiness and risk checks; paper/live order remains approval-gated. |
| "这个 P1 代码风险是真的吗？" | Engineering Desk cites CodeGraph/AST/test design evidence and creates a work order, not a direct repo edit. |

## 5. Action Cards

Action cards are the main safety boundary in the Web UI.

Required fields:

- Action title
- Desk
- Risk level
- Current status
- Expected effect
- Parameters
- Evidence list
- Approval controls
- Expiry time
- Outcome summary

Action cards must distinguish:

- Read-only observations
- Dry-run proposals
- Write proposals
- Paper order proposals
- Live order proposals
- Engineering work orders

## 6. Evidence Deep Links

Every evidence card should support one or more of:

- Open a Web route, such as `/datahub?tab=sources` or `/system?tab=lifecycle`.
- Show the CLI command that generated the evidence.
- Open a local artifact path.
- Open a code or spec file location.
- Show freshness, hash, row counts, and source metadata when available.

## 7. API Dependencies

The CEO Office should consume the Agent Runtime API defined in [07-agent-company-os.md](../../specs/07-agent-company-os.md):

- `GET /api/agent/sessions`
- `POST /api/agent/sessions`
- `GET /api/agent/sessions/{session_id}`
- `GET /api/agent/sessions/{session_id}/stream`
- `POST /api/agent/sessions/{session_id}/messages`
- `GET /api/agent/actions`
- `POST /api/agent/actions/{action_id}/approve`
- `POST /api/agent/actions/{action_id}/reject`
- `POST /api/agent/actions/{action_id}/cancel`
- `GET /api/agent/runs/{run_id}/stream`
- `GET /api/agent/evidence/{evidence_id}`
- `GET /api/agent/desks`
- `GET /api/agent/work-orders`
- `POST /api/agent/work-orders`
- `PATCH /api/agent/work-orders/{work_order_id}`

Session and run-event updates use server-sent events. The Web client must use the shared authenticated fetch-SSE helper rather than browser `EventSource`, because local deployments may require `ASTROLABE_API_KEY` bearer headers.

## 8. UX States

The page must handle:

- No agent runtime initialized
- Empty session
- Running tool
- Pending approval
- Blocked action
- Evidence missing
- Stale artifact
- Broker live mode disabled
- Open Engineering Desk work orders
- Engineering work order status changes
- Safe workflow results for proposed read-only and dry-run actions
- Desk unavailable
- API unavailable

No state may show fake success or silently hide blockers.

## 9. Internationalization

Chinese and English strings must be maintained together. The Chinese wording should remain direct and operational, not marketing-heavy. Suggested page names:

| Key | Chinese | English |
| --- | --- | --- |
| `ceoOffice` | CEO 办公室 | CEO Office |
| `actionQueue` | 行动队列 | Action Queue |
| `evidence` | 证据 | Evidence |
| `deskStatus` | Desk 状态 | Desk Status |
| `approvalRequired` | 需要审批 | Approval Required |

## 10. Acceptance Criteria

- `/` renders the CEO Office.
- `/market` renders the former market overview.
- A new session can be created from the Web UI.
- The current session can be archived from the Web UI without deleting ledger history.
- The current session subscribes to a session snapshot SSE stream and refreshes when message/action/run counts change.
- The selected action subscribes to the latest run's event snapshot SSE stream and updates the run timeline without reloading the whole page.
- A user message appears in the timeline and is persisted.
- The user can choose the target desk for a CEO message from the registered desk list.
- The user can explicitly paste a semantic planner JSON draft, preview or send it through the same CEO message path, and see invalid JSON rejected before any API call.
- The user can explicitly enable Provider Planner for one preview or message; the UI must hide local JSON draft entry in that mode, optionally collect request-scoped provider/model overrides, visibly warn that this calls an external LLM provider and records token/cost usage locally, the API payload must use `planner_mode=provider_semantic`, and missing provider credentials must appear as a blocked semantic-assisted plan rather than falling back to a fake deterministic success.
- Provider Planner output is shown only after server-side fixed-registry filtering; unsafe, write, trading, unknown, or desk-out-of-scope actions must be rejected before they become action cards.
- The user can run proposed read-only checks for the active session from the CEO Office, with run/skipped/failed counts visible.
- The user can run one bounded autonomy step or a capped bounded autonomy loop from the CEO Office using the current target desk and planner settings, then inspect proposed actions, actual runs, skipped safety outcomes, step counts, and stop reasons.
- The desk rail supports drill-down: selecting a desk shows its mandate, allowed tools, forbidden actions, evidence requirements, related actions, and related handoffs.
- The CEO Office shows explicit approval policy rows so users can inspect which risk levels auto-run, require approval, or require engineering work orders.
- A desk response includes evidence references.
- A proposed write action appears as an approval card instead of executing immediately.
- Approving, rejecting, and canceling actions update the ledger and UI state.
- Evidence cards deep-link into existing views.
- No Web control directly edits repository files.
- Frontend typecheck and build pass.

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| Conversation page becomes vague | Require structured responses and evidence references. |
| Existing Web pages become buried | Use evidence deep links and keep primary navigation. |
| Users misunderstand dry-run as execution | Use distinct action card states and wording. |
| Frontend becomes too heavy | Keep graph/detail views on existing pages and show summaries in CEO Office. |
