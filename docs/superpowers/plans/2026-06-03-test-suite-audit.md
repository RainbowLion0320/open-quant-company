# Test Suite Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit every test file, remove or modernize obsolete tests, and fix real design problems exposed by the audit.

**Architecture:** Treat tests as product contracts, not passive coverage. Keep behavior tests close to public APIs, keep architecture tests focused on stable boundaries, and move brittle source-string checks to the module that now owns the responsibility.

**Tech Stack:** Python pytest, FastAPI TestClient, Vue/Vite, Playwright smoke checks, local shell auditing scripts.

---

### Task 1: Build The Test Inventory

**Files:**
- Read: `tests/**/*.py`
- Create: `docs/testing/test-suite-audit.md` if durable notes are needed

- [x] Collect the active pytest node list with `.venv/bin/python3 -m pytest --collect-only -q`.
- [x] Inventory each test file: line count, test count, top-level executable checks, `Path(...).read_text` source contracts, TestClient usage, monkeypatch usage, subprocess/shell usage, and skipped/xfail tests.
- [x] Compare collected tests with files under `tests/` to find uncollected scripts, stale helpers, and cache-only artifacts.

### Task 2: Review Tests By Risk Category

**Files:**
- Read/modify: all files under `tests/`

- [x] Review script-style tests first (`test_boundary.py` and duplicate smoke scripts) because they often predate pytest conventions.
- [x] Review source-string architecture contracts and decide whether each is still a stable system contract after the recent modularization.
- [x] Review API and route tests for removed endpoints, legacy redirects, stale model names, or duplicate route coverage.
- [x] Review data, broker, regime, strategy, pipeline, and frontend contract tests for overlap and outdated expectations.

### Task 3: Apply Test And Design Fixes

**Files:**
- Modify: affected tests and production modules discovered by the audit

- [x] Delete tests only when they are obsolete and not encoding a valid contract.
- [x] Rewrite brittle tests to target current module ownership rather than legacy file locations.
- [x] If a test exposes a production design issue, fix the production boundary and keep or add a regression test.

### Task 4: Add Test Health Guardrails

**Files:**
- Modify/create: `tests/test_test_suite_health.py` or equivalent

- [x] Add guardrails against common stale-test patterns: top-level executable assertions, tracked bytecode caches, uncollected test files, and contracts tied to obsolete monolith locations.
- [x] Keep the guardrails narrow enough not to block valid architecture contracts.

### Task 5: Verify And Report

**Files:**
- Read: git diff and test outputs

- [x] Run targeted tests for every edited area.
- [x] Run `npm run build` for frontend-affecting changes.
- [x] Run `.venv/bin/python3 -m pytest -q`.
- [x] Run `git diff --check`.
- [x] Summarize deleted/updated tests, fixed design issues, and remaining risk.
