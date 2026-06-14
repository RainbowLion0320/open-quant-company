# Agent Company OS Phase 5 - Paper Execution Control Plan

> Status: preview/proposal/submission/cancellation/CEO Office card foundation implemented
> Created: 2026-06-14
> Parent roadmap: [00-master-roadmap.md](00-master-roadmap.md)
> Related spec: [07-agent-company-os.md](../../specs/07-agent-company-os.md)

## 1. Goal

Make PaperBroker execution controllable from Agent Company OS without weakening the existing broker safety model. Agents may preview and propose paper orders, but no paper order may be submitted unless the CEO approves it and the execution path writes a durable run and reconciliation record.

This phase is the safety rehearsal for MiniQMT/QMT live execution. Paper execution may be simulated, but the approval, evidence, risk gate, ledger, and reconciliation rules must be treated as real.

## 2. Scope

In scope:

- Non-mutating PaperBroker order preview
- Agent-generated paper order approval cards
- Evidence artifacts for preview state
- Approval-required `paper_order` actions
- Risk gate blockers for missing price, missing evidence, insufficient cash, sellability, and broker risk rules
- Approved paper submission after re-running preview/risk gates
- Broker ledger linkage, reconciliation artifact, and outcome evidence
- Dedicated cancellation controls for queued approval requests and broker-cancelable submitted paper orders

Out of scope:

- Live MiniQMT/QMT order submission
- Bypassing PaperBroker risk rules
- Unattended order submission from chat text
- Repository edits from Web runtime

## 3. Current Foundation

- `broker.paper_core.PaperBroker.preview_order()` previews a limit order without creating an order, changing cash, changing positions, or appending broker ledger events.
- `agent_os.runtime.AgentRuntime.propose_paper_order()` writes the preview to `var/artifacts/agent/paper_previews/`, registers artifact evidence, and creates an approval-required `paper_order` action.
- `astroq agent paper propose ... --json` exposes the proposal flow for automation.
- `POST /api/agent/paper/proposals` exposes the same proposal flow for CEO Office and future UI cards.
- `agent_os.runtime.AgentRuntime.submit_paper_order_action()` submits only approved `paper_order` actions, re-runs PaperBroker preview/risk gates against current broker state, and blocks stale approvals before any order is created.
- `astroq agent paper submit ACTION_ID --json` and `POST /api/agent/paper/actions/{action_id}/submit` expose the approved submit flow.
- `astroq agent paper cancel ACTION_ID --json` and `POST /api/agent/paper/actions/{action_id}/cancel` expose the dedicated paper cancellation flow.
- Successful submits write an `AgentRun`, register reconciliation evidence, and persist default PaperBroker state/trades/NAV through the current `ASTROLABE_VAR` runtime root.
- Queued paper approval-request cancellation writes a `paper.paper_order.cancel` run and reconciliation evidence with `status=queued_action_canceled`.
- Submitted paper order cancellation keeps the original action `succeeded`; if `PaperBroker.cancel_order(order_id)` accepts the active order, runtime writes a new `paper.paper_order.cancel` run and `status=order_canceled` reconciliation evidence. If the order is filled, missing, expired, rejected, or otherwise non-cancelable, runtime writes a blocked cancellation run instead of pretending success.
- CEO Office action detail shows PaperBroker preview/risk gate summary and exposes a dedicated submit button for approved `paper_order` actions; paper orders do not use the generic action run button.
- CEO Office run history exposes run artifact evidence refs, so reconciliation artifacts can be opened from the submitted action without leaving the control page.

## 4. PaperOrderPreview Contract

Required fields:

- `status`: `preview_ready` or `blocked`
- `intent`: normalized symbol, side, quantity, order type, limit price, strategy, reason, evidence refs
- `approval_required`: always `true`
- `submitted`: always `false`
- `risk_gate`: `passed`, `blockers`, and per-check evidence
- `estimated_cash_effect`
- `estimated_position_effect`
- `fees`
- `account_snapshot`

The preview must fail closed for:

- Missing symbol
- Invalid side
- Non-positive quantity
- Unsupported order type
- Missing execution price
- Missing evidence refs
- Insufficient cash
- Insufficient sellable shares
- PaperBroker risk rule failure

## 5. Proposal Contract

A paper order proposal must:

- Require an existing `AgentSession`.
- Use Execution Desk scope.
- Create `AgentAction` with `action_type=paper_order` and `risk_level=paper_order`.
- Set `status=approval_required`.
- Attach preview artifact evidence.
- Keep broker state unchanged.
- Avoid any `submit_order()` call.

Blocked previews return `status=blocked` and must not create an approval action.

## 6. Submission Contract

Approved paper submission must:

- Require `AgentAction.status=approved`.
- Require `action_type=paper_order` and `risk_level=paper_order`.
- Re-run `PaperBroker.preview_order()` against current broker state before calling `submit_order()`.
- Block without submitting when cash, price, holdings, evidence, or broker risk state changed after approval.
- Write a terminal `AgentRun` with `tool_name=paper.paper_order.submit`.
- Register reconciliation evidence under `var/artifacts/agent/paper_reconciliation/`.
- Mark the action `succeeded` only after PaperBroker returns a `PAPER_*` order id.
- Mark the action `blocked` or `failed` with structured reasons when submit cannot safely complete.

## 7. Remaining Work

Paper execution control is functionally complete for local paper proposal, approval, submission, cancellation, and reconciliation evidence. Future improvements should deepen the view rather than change the safety contract:

- More compact inline diff views for intended order, broker order, trade, cash, and position deltas.
- Optional PaperBroker order-state persistence if the default paper broker later needs cancellation after process restart; until then, missing order state must block with evidence.

## 8. Acceptance Criteria

- Previewing a paper order does not mutate PaperBroker state.
- A passing preview can create an approval-required action with evidence.
- A blocked preview does not create an action.
- Dispatch before approval records a blocked run.
- Approved submission re-checks preview/risk gates before any broker mutation.
- A stale approval is re-blocked when cash, price, holdings, or evidence no longer satisfies preview requirements.
- Successful submission writes an `AgentRun`, reconciliation artifact evidence, and default PaperBroker persistence state.
- CEO Office displays paper preview/risk summary and uses the dedicated approved submit path instead of generic action dispatch.
- CEO Office run history links reconciliation evidence from `AgentRun.artifact_refs`.
- Queued paper approval requests can be canceled through the dedicated paper cancel path and write reconciliation evidence.
- Submitted paper actions can record a broker-confirmed paper order cancellation when the order is still active; non-cancelable orders return blocked cancellation evidence.
