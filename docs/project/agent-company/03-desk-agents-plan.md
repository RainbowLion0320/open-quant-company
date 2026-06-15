# Agent Company OS Phase 3 - Desk Agents Plan

> Status: planned implementation phase
> Created: 2026-06-14
> Parent roadmap: [00-master-roadmap.md](00-master-roadmap.md)
> Depends on: [01-foundation-plan.md](01-foundation-plan.md) and [02-ceo-office-plan.md](02-ceo-office-plan.md)

## 1. Goal

Create specialized desk agents that operate like a small quant company. Each desk has a mandate, allowed tools, evidence requirements, and escalation rules.

The desk agent layer should organize work and communication. It must not bypass the existing deterministic gates for data, backtest, lifecycle readiness, risk, execution, tests, or architecture diagnostics.

## 2. Shared Desk Contract

Each desk agent must expose:

| Field | Meaning |
| --- | --- |
| `desk_id` | Stable id such as `data`, `research`, `risk`, `execution`, `engineering`, `reporting`. |
| `display_name` | Human-readable desk name. |
| `mandate` | What the desk is responsible for. |
| `allowed_tools` | Tool registry ids the desk may invoke. |
| `forbidden_actions` | Actions the desk cannot perform. |
| `evidence_required` | Evidence kinds required before making claims. |
| `handoff_targets` | Desks this desk may hand off to. |
| `default_policy` | Approval behavior for desk actions. |

Each desk response must include:

- `answer`
- `confidence`
- `evidence_refs`
- `proposed_actions`
- `blockers`
- `handoffs`

## 3. Data Desk

Mandate:

- Source capability registry
- Tushare/AKShare/candidate source audit
- Local DataHub coverage
- Freshness and schema health
- Repair and backfill proposals

Allowed tools:

- `astroq data status --json`
- `astroq data sources --json`
- `astroq data sources audit ... --dry-run --json`
- `astroq data sources diff-registry --json`
- `astroq data repair <dimension> --dry-run --json`
- `astroq data tushare-audit --json`

Hard rules:

- Missing permission must be reported as `missing_capability` or `no_permission`.
- Stale data must not be green.
- Backfill writes require approval.

## 4. Research Desk

Mandate:

- Strategy catalog interpretation
- Candidate strategy research
- Backtest evidence
- OOS/IC/ICIR analysis
- Promotion or retirement proposals

Allowed tools:

- `astroq strategy catalog --json`
- `astroq strategy compete --json`
- `astroq backtest run --dry-run --json`
- `astroq backtest check --json`
- `astroq lifecycle check --json`

Hard rules:

- Missing score panels or alpha evidence must be `blocked`, not treated as weak performance.
- Risk overlay strategies may use overlay evidence instead of IC/ICIR, but must mark IC/ICIR as `not_applicable` with a reason.
- Full backtests that write official evidence require approval.

## 5. Risk Desk

Mandate:

- Lifecycle readiness interpretation
- Portfolio risk
- Exposure and drawdown checks
- Data readiness gates
- Execution risk gates

Allowed tools:

- `astroq lifecycle check --json`
- `astroq execution dry-run --json`
- Portfolio and risk read-only API endpoints
- Strategy evidence artifacts

Hard rules:

- Missing raw execution price blocks execution.
- Missing risk-free curve blocks risk-adjusted metrics.
- Risk gate failures cannot be overridden by another desk; only the CEO can decide whether to change configuration.

## 6. Execution Desk

Mandate:

- Paper order proposals
- Live readiness checks
- Broker state reconciliation
- Order previews
- Kill switch state

Allowed tools:

- `astroq execution dry-run --json`
- Broker readiness checks
- Paper broker state read APIs
- `astroq agent live readiness --json` MiniQMT/QMT readiness probe

Hard rules:

- Paper orders require approval.
- Live orders require live mode, broker readiness, account readiness, risk gate pass, and approval.
- Missing MiniQMT/QMT SDK or permission is `not_integrated` or `blocked`; never fallback to paper.

## 7. Engineering Desk

Mandate:

- CodeGraph diagnostics
- AST duplicate implementation diagnostics
- Test design intelligence
- Bug triage
- Work order creation

Allowed tools:

- `astroq architecture ast --json`
- `astroq test design --json`
- `astroq docs check --json`
- CodeGraph read APIs
- Work-order creation
- `astroq agent work-orders --json`
- `astroq agent work-order create ... --json`

Hard rules:

- The Web Engineering Desk does not edit repo files.
- It can create an engineering work order with evidence, impact, affected files, and suggested verification.
- Engineering work orders are auditable through runtime, CLI, API, memory snapshot, CEO Office, and engineering digest reports.
- Codex, Claude, or a human handles code changes outside the Web runtime.

## 8. Reporting Desk

Mandate:

- Daily CEO brief
- Weekly research review
- Data quality summary
- Risk and execution summary
- Audit pack and release summary

Allowed tools:

- Read all current evidence artifacts
- Resolve evidence references
- Generate reports under `var/artifacts/agent/reports/`

Hard rules:

- Reports must cite evidence.
- Missing evidence must be visible in the report.
- Reports should not copy secrets or raw token values.

## 9. Handoff Model

Common handoffs:

| Source desk | Target desk | Trigger |
| --- | --- | --- |
| Data | Research | Data becomes ready for a blocked strategy. |
| Research | Risk | Strategy promotion proposal needs gate review. |
| Risk | Execution | Approved paper or live action is risk-cleared. |
| Execution | Risk | Broker state or reconciliation issue appears. |
| Engineering | Data | Code risk points to data pipeline bug. |
| Reporting | Any desk | Brief identifies unresolved blocker. |

Handoffs must be recorded as ledger events, not hidden inside a conversational paragraph.

## 10. Initial Workflows

### Daily CEO Brief

1. Reporting Desk gathers lifecycle readiness.
2. Data Desk explains data blockers.
3. Research Desk explains strategy evidence state.
4. Risk Desk explains action safety.
5. Execution Desk reports paper/live readiness.
6. Reporting Desk produces a concise CEO brief with action cards.

### Strategy Competition Review

1. Research Desk reads strategy competition artifact.
2. Missing evidence becomes blockers.
3. Data Desk receives data gap handoff if needed.
4. Risk Desk reviews promotion candidate.
5. CEO receives approve/reject proposal.

### Data Gap Repair

1. Data Desk identifies missing dimension and source capability.
2. Data Desk runs dry-run repair plan.
3. CEO approves write repair.
4. Data Desk executes approved repair and writes outcome evidence.
5. Research/Risk desks are notified if blockers clear.

### Engineering Risk Review

1. Engineering Desk reads AST/CodeGraph/test design diagnostics.
2. Desk classifies true issue vs false positive.
3. Desk creates work order if real.
4. Codex/Claude executes outside Web runtime.
5. Evidence links back to commit/tests.

## 11. Acceptance Criteria

- Each desk has a registry entry with mandate and tool permissions.
- Every desk-declared fixed tool exists in `AgentToolRegistry` with matching desk scope.
- Common CEO intents route to concrete safe tools where the deterministic contract is known, including data source registry diff, strategy competition, backtest dry-run, test design, and docs check.
- Desk responses include evidence references and structured blockers.
- A desk cannot invoke a tool outside its allowed scope.
- A desk cannot execute write/paper/live actions without approval policy.
- Handoffs are persisted and visible in the CEO Office.
- Engineering Desk creates work orders instead of editing code.
- Reporting Desk produces evidence-cited summaries.

## 12. Risks

| Risk | Mitigation |
| --- | --- |
| Desk boundaries become decorative | Enforce tool permissions in runtime, not only prompts. |
| Desks overuse natural language | Require structured response schema and evidence refs. |
| Handoffs become noisy | Only record handoffs when another desk must act. |
| Reporting becomes stale | Reports must show artifact age and freshness status. |
