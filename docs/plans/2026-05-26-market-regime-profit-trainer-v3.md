# Market Regime Profit Trainer V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and superpowers:test-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the profit-oriented Market Regime trainer from a challenger promotion gate into a validated formula search that can identify the best currently supported formula without assuming the existing champion is already valid.

**Architecture:** Evaluate the champion and every candidate under the same diagnostics. Separate best unconstrained candidate, best validated candidate, and current champion diagnostics. Use hard gates only for true invalid states, use relative gates for turnover and production replacement, and write candidate-level gate reasons into reports.

**Tech Stack:** Python, pandas, numpy, existing `research/regime_training.py`, pytest, Markdown/YAML/CSV/Parquet reports.

---

## V3 Rules

- Champion is part of the evaluated formula pool and gets the same gate diagnostics as challengers.
- `keep_champion` no longer means “champion is best”; it means either champion is the selected validated formula or no replacement crossed the promotion margin.
- A new `best_validated_id` is selected from formulas that pass validation gates. This can be the champion or a challenger.
- A new `best_unconstrained_id` records the strongest raw profit formula, even if it fails a gate.
- Hard gates reject only structurally invalid formulas: permanent regime collapse, no risk-on participation, excessive risk-off domination, non-finite metrics, insufficient OOS evidence.
- Turnover is relative to champion and baselines, not an absolute one-sided cap that can reject all formulas while exempting the champion.
- Reports include `candidate_gate_diagnostics.csv`, `candidate_validation_summary.csv`, `champion_gate_diagnostics`, and `decision_reason`.
- Production formula remains advisory-only; V3 can recommend a challenger for review but cannot auto-apply it.

## Tasks

- [ ] Add failing tests for same-standard champion diagnostics, best validated candidate selection, gate reason reporting, and summary schema.
- [ ] Implement candidate validation summaries and gate diagnostics.
- [ ] Change V3 selection so hard gates are applied before picking `best_validated_id`.
- [ ] Update reports and recommended config to use `best_validated_id`.
- [ ] Update operator docs.
- [ ] Run targeted tests, full tests, smoke trainer, and full trainer.
