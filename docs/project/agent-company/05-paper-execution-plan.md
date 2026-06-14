# Agent Company OS Phase 5 - Paper Execution Control Plan

> Status: preview/proposal foundation implemented; submission/reconciliation planned
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
- Later: approved paper submission, broker ledger linkage, reconciliation, and outcome evidence

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
- Approved `paper_order` actions are still not wired to submit through PaperBroker; dispatch blocks on the missing submit tool instead of silently executing.

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

## 6. Remaining Work

Before paper execution control is complete, implement:

- Approved `paper_order` dispatch tool that submits through PaperBroker only after re-running preview/risk gates against current broker state.
- Paper order run ledger entries with order id, broker status, and masked account/broker metadata.
- PaperBroker reconciliation artifact comparing intended order, broker order, trade, cash, and position state.
- CEO Office paper order action card UI with preview/risk details and approve/reject controls.
- Kill/cancel semantics for queued paper order actions.
- Regression tests proving an approved but stale preview is re-blocked when price, cash, or holdings changed.

## 7. Acceptance Criteria

- Previewing a paper order does not mutate PaperBroker state.
- A passing preview can create an approval-required action with evidence.
- A blocked preview does not create an action.
- Dispatch before approval records a blocked run.
- No current Agent Runtime path submits a paper order without a dedicated approved submit tool.
- Future submit tool must re-check risk and write reconciliation evidence before marking success.
