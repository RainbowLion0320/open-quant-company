# Agent Company OS Phase 1 - Foundation Runtime Plan

> Status: planned implementation phase
> Created: 2026-06-14
> Parent roadmap: [00-master-roadmap.md](00-master-roadmap.md)
> Formal contract: [07-agent-company-os.md](../../specs/07-agent-company-os.md)

## 1. Goal

Build the local Agent Runtime that all future desk agents and the CEO Office will use. Phase 1 must be usable from CLI and tests before the Web conversation page exists.

The runtime is not a general-purpose autonomous agent framework. It is a deterministic orchestration layer over Open Quant Company tools, evidence artifacts, approvals, and ledgers.

## 2. Scope

In scope:

- Runtime package and schemas
- Session, message, action, run, run event, approval, and evidence ledgers
- Tool registry with risk classification
- Approval policy engine
- Evidence resolver
- JSON CLI commands under `astroq agent *`
- Contract tests

Out of scope:

- Full CEO Office Web page
- Desk-specific natural language routing quality
- Live broker implementation
- External hosted agent memory

## 3. Proposed Module Shape

Future implementation may use a top-level package such as `agent_os/` or another canonical package name chosen during implementation. The important boundary is the responsibility split:

| Area | Responsibility |
| --- | --- |
| `schemas` | Pydantic or dataclass contracts for sessions, messages, actions, runs, run events, evidence, policies, and desks. |
| `ledger` | Local persistence for sessions, messages, actions, approvals, run outcomes, and run event timelines. |
| `tools` | Registry for CLI/API/backtest/data/system tools with risk level and allowed desk scopes. |
| `approval` | Policy evaluation, approval request creation, expiry, and decision recording. |
| `evidence` | Resolve `EvidenceRef` into Web links, CLI commands, files, code locations, and artifact summaries. |
| `runtime` | Execute read-only analysis, queue action proposals, and dispatch approved actions. |
| `desks` | Shared desk interface and initial deterministic desk shells. |

## 4. Core Schemas

### AgentSession

Represents a CEO conversation or desk workflow.

Required fields:

- `session_id`
- `title`
- `created_at`
- `updated_at`
- `status`: `active`, `archived`, `blocked`
- `created_by`: `human`, `agent`, `system`
- `default_desk`
- `tags`

### AgentMessage

Represents a human, desk, or system message.

Required fields:

- `message_id`
- `session_id`
- `role`: `ceo`, `desk_agent`, `system`, `tool`
- `desk`
- `content`
- `evidence_refs`
- `action_refs`
- `created_at`

### AgentAction

Represents a proposed state-changing or material operation.

Required fields:

- `action_id`
- `session_id`
- `desk`
- `action_type`
- `risk_level`: `read_only`, `dry_run`, `write_config`, `write_data`, `run_backtest`, `paper_order`, `live_order`, `code_change`
- `status`: `proposed`, `approval_required`, `approved`, `rejected`, `running`, `succeeded`, `failed`, `blocked`, `expired`, `canceled`
- `summary`
- `parameters`
- `expected_effect`
- `evidence_refs`
- `approval_required`
- `approval_decision`
- `expires_at`
- `created_at`
- `updated_at`

### EvidenceRef

Represents a traceable source used by an agent.

Required fields:

- `evidence_id`
- `kind`: `web_route`, `api_endpoint`, `cli_command`, `artifact`, `file`, `code`, `report`, `ledger`
- `label`
- `uri`
- `snapshot_uri`
- `summary`
- `generated_at`
- `hash`
- `freshness_status`

### AgentRun

Represents a tool execution or desk workflow run.

Required fields:

- `run_id`
- `action_id`
- `tool_name`
- `command`
- `started_at`
- `finished_at`
- `status`
- `return_code`
- `stdout_summary`
- `stderr_summary`
- `artifact_refs`

### AgentRunEvent

Represents a status, stdout/stderr, or terminal event emitted by a tool execution.

Required fields:

- `event_id`
- `run_id`
- `action_id`
- `sequence`
- `event_type`: `queued`, `running`, `stdout`, `stderr`, `succeeded`, `failed`, `blocked`
- `status`
- `message`
- `payload`
- `created_at`

### ApprovalPolicy

Defines whether an action can run automatically or must wait for CEO approval.

Required fields:

- `policy_id`
- `risk_level`
- `default_decision`
- `required_role`
- `expires_after_seconds`
- `reason`

## 5. Persistence

Target local paths:

| Path | Purpose |
| --- | --- |
| `var/db/agent_os.sqlite` | Sessions, messages, actions, approvals, run ledger, run event timeline, desk registry snapshots. |
| `var/artifacts/agent/runs/` | Per-run outputs and summaries. |
| `var/artifacts/agent/evidence/` | Evidence snapshots that should survive source mutation. |
| `var/artifacts/agent/reports/` | Generated CEO briefs and audit packs. |

The runtime must not store secrets. Any environment or provider state must be masked and referenced through existing config health commands.

## 6. Tool Registry

The registry maps safe tool names to fixed commands or internal callables. It must avoid arbitrary shell strings.

Initial tool families:

| Family | Examples | Default policy |
| --- | --- | --- |
| Health | `astroq health --json`, `astroq config env --json` | Auto-run read-only. |
| Data audit | `astroq data status --json`, `astroq data sources diff-registry --json` | Auto-run read-only. |
| Data repair | `astroq data repair <dimension> --dry-run --json` | Auto-run dry-run; writes require approval. |
| Strategy | `astroq strategy catalog --json`, `astroq strategy compete --json` | Read-only auto-run; long runs may require approval. |
| Backtest | `astroq backtest run --dry-run --json` | Dry-run auto-run; full runs require approval. |
| Lifecycle | `astroq lifecycle check --json` | Auto-run read-only. |
| System intelligence | `astroq architecture ast --json`, `astroq test design --json` | Approval recommended because they write artifacts. |
| Execution | `astroq execution dry-run --json` | Dry-run auto-run; paper/live actions require approval. |
| Engineering | Work-order creation only | Repository edits are outside Web runtime. |

## 7. Approval Policy

| Risk level | Default behavior |
| --- | --- |
| `read_only` | Can run automatically and write no runtime artifacts except command logs. |
| `dry_run` | Can run automatically if it does not mutate production data or broker state. |
| `write_data` | Requires CEO approval. |
| `write_config` | Requires CEO approval and config diff evidence. |
| `run_backtest` | Requires approval when long-running or writing official evidence. |
| `paper_order` | Requires CEO approval and risk gate pass. |
| `live_order` | Requires CEO approval, live mode enabled, broker readiness, risk gate pass, and kill switch availability. |
| `code_change` | Web runtime cannot execute directly; create an engineering work order. |

## 8. CLI Contract

Phase 1 should add JSON-readable commands:

| Command | Purpose |
| --- | --- |
| `astroq agent sessions --json` | List local agent sessions. |
| `astroq agent session create --title ... --json` | Create a session. |
| `astroq agent session run-readonly <session_id> --json` | Run proposed read-only actions for one session and skip write/trading actions. |
| `astroq agent message --session <id> --desk <desk> --text ... --json` | Add a CEO message and route it. |
| `astroq agent actions --session <id> --json` | List proposed and running actions. |
| `astroq agent approve <action_id> --json` | Approve an action. |
| `astroq agent reject <action_id> --reason ... --json` | Reject an action. |
| `astroq agent evidence <evidence_id> --json` | Resolve evidence. |
| `astroq agent desks --json` | List desk agents, status, and allowed tools. |
| `astroq agent policies --json` | List explicit approval policies, default decisions, roles, expiry windows, and reasons. |

## 9. Acceptance Criteria

- Creating a session writes a durable local record.
- Adding a message writes a durable message and produces deterministic desk routing metadata.
- Read-only tools can run through fixed command arrays.
- Session-level read-only workflow runs dispatch only proposed/read_only actions and report skipped write/trading actions.
- State-changing actions are queued as `approval_required`.
- Approval policies are explicit runtime/CLI/API contracts, not hidden conditionals.
- Approval and rejection decisions are persisted.
- Expired queued actions are marked `expired` and cannot be approved or dispatched.
- Evidence references resolve without requiring a running Web server.
- Missing evidence returns `missing_evidence`, not an empty success.
- Test coverage verifies no arbitrary shell execution, no secret persistence, and no paper/live execution without approval.

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| Runtime becomes another compatibility layer | Keep schemas strict and avoid wrapping every existing module unless it becomes an agent tool. |
| Agent memory becomes opaque | Store memory as auditable ledger rows and evidence references. |
| Tool registry becomes unsafe | Use fixed command arrays and risk classifications. |
| Web work starts before foundation is stable | Phase 2 depends on Phase 1 schemas and ledgers. |
