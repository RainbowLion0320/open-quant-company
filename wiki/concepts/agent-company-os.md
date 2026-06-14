---
title: Agent Company OS
created: 2026-06-14
updated: 2026-06-14
type: concept
tags: [agent-company, ceo-office, roadmap]
---

# Agent Company OS

Agent Company OS is the long-term operating layer for Open Quant Company. The user acts as CEO, and desk agents coordinate data, research, risk, execution, engineering, and reporting work through approval-gated actions and evidence references.

This page is an index, not the detailed plan. The authoritative documents are:

- [Master roadmap](../../docs/project/agent-company/00-master-roadmap.md)
- [Foundation runtime plan](../../docs/project/agent-company/01-foundation-plan.md)
- [CEO Office plan](../../docs/project/agent-company/02-ceo-office-plan.md)
- [Desk agents plan](../../docs/project/agent-company/03-desk-agents-plan.md)
- [Live execution plan](../../docs/project/agent-company/04-live-execution-plan.md)
- [Formal behavior spec](../../docs/specs/07-agent-company-os.md)

Key decisions:

- CEO Office becomes the future default `/` page.
- The current market overview moves to `/market`.
- Read-only and dry-run work can run automatically; state-changing actions require approval.
- Memory is transparent local ledger state, not opaque hidden model memory.
- MiniQMT/QMT is the first planned live broker adapter and must not fallback to PaperBroker when live readiness is missing.
- The Web Engineering Desk creates work orders instead of editing repository code directly.
