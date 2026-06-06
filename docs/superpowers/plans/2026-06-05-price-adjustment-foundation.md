# Price Adjustment Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make stock price adjustment semantics explicit and route research, backtest, valuation, and execution through a single price service.

**Architecture:** Store canonical stock OHLCV by declared mode (`raw`, `qfq`, `hfq`) and derive adjusted views from raw OHLCV plus `adj_factor` when available. Consumers request prices by use case so technical research uses adjusted return series while execution and valuation use raw market prices.

**Tech Stack:** Python, pandas, local Parquet via DataHub, pytest.

---

### Task 1: P0 Price Mode Contract

**Files:**
- Create: `data/market/price_types.py`
- Modify: `data/quality/contract.py`
- Modify: `data/storage/datahub_manifest.py`
- Test: `tests/test_price_service_contracts.py`

- [x] Add `PriceMode`, `PriceUseCase`, `PriceFrameMetadata`, and helpers to normalize/attach/read metadata.
- [x] Extend `DataContract` persistence with optional `price_mode` and `adjustment_source`.
- [x] Record price metadata into DataHub manifest when DataFrame attrs contain it.
- [x] Add failing then passing tests for price mode normalization, metadata attachment, OHLCV contract metadata, and manifest price fields.

### Task 2: P1 Unified Price Service

**Files:**
- Create: `data/market/price_service.py`
- Modify: `data/storage/datahub_paths.py`
- Modify: `data/storage/datahub.py`
- Modify: `data/ingestion/fetchers/stock_daily.py`
- Modify: `data/ingestion/fetcher.py`
- Test: `tests/test_price_service_contracts.py`

- [x] Add stock paths for `daily_raw`, legacy `daily` qfq, and `daily_hfq`.
- [x] Make `get_stock_daily(adjust=...)` read/write the matching store path instead of ignoring `adjust` on cached reads.
- [x] Implement `adjust_ohlcv()` using Tushare-style `adj_factor`: qfq ratio `factor/latest_factor`, hfq ratio `factor`.
- [x] Implement `get_stock_prices()`, `get_stock_price_matrix()`, and use-case helpers.
- [x] Add tests for raw/qfq path selection, qfq derivation from raw plus adj_factor, and legacy qfq fallback.

### Task 3: P2 Consumer Migration

**Files:**
- Modify: `backtest/run_all_strategies.py`
- Modify: `scripts/build_features.py`
- Modify: `signals/candidates/common.py`
- Modify: `signals/runners.py`
- Modify: `signals/ml_signals.py`
- Modify: `scripts/execute_paper_trades.py`
- Modify: `web/api/services/dcf.py`
- Modify: `web/api/services/stocks.py`
- Modify: `web/api/routes/portfolio.py`
- Test: `tests/test_price_service_contracts.py`
- Test: existing related tests

- [x] Route research/technical/backtest price history through `PriceUseCase.RESEARCH` or `PriceUseCase.BACKTEST` (`qfq`).
- [x] Route current execution and valuation prices through `PriceUseCase.EXECUTION` or `PriceUseCase.VALUATION` (`raw` with safe latest adjusted fallback).
- [x] Keep old `get_stock_daily()` API compatible while making new code prefer `data.market.price_service`.
- [x] Add tests that assert major modules import/use `get_stock_prices` or `get_stock_price_matrix` with explicit use cases.

### Task 4: P3 Corporate Action Event Layer

**Files:**
- Create: `data/market/corporate_actions.py`
- Modify: `data/storage/datahub_paths.py`
- Modify: `data/storage/datahub.py`
- Modify: `data/quality/contract.py`
- Test: `tests/test_price_service_contracts.py`

- [x] Add dividend/corporate-action paths and a normalized event schema.
- [x] Implement `load_corporate_actions()`, `normalize_dividend_events()`, and `apply_corporate_actions_to_position()`.
- [x] Support cash dividend events and share bonus/split events for historical position adjustment.
- [x] Add tests for dividend cash accrual and share multiplier adjustment.

### Task 5: Documentation and Registry Alignment

**Files:**
- Modify: `config/settings.yaml`
- Modify: `docs/specs/01-data-pipeline.md`
- Modify: `wiki/reference/data-schema.md`
- Test: `tests/test_documentation_contracts.py` or architecture contracts

- [x] Document raw/qfq/hfq semantics and use-case mapping.
- [x] Add registry entries/cache paths for raw daily, qfq daily, hfq daily, adj_factor, and corporate actions.
- [x] Add a contract test that docs mention explicit price modes.

### Task 6: Verification

**Files:**
- No production code unless a verification failure reveals a bug.

- [x] Run focused tests: `pytest tests/test_price_service_contracts.py tests/test_datahub_contracts.py tests/test_contract.py tests/test_architecture_contracts.py -q`.
- [x] Run import/compile checks for changed modules.
- [x] Run `git diff --check`.
- [x] Inspect `git status --short` and ensure generated data remains ignored.
