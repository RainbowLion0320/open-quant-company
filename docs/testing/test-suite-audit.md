# Test Suite Audit

> Date: 2026-06-03
> Scope: all Python test sources under `tests/`, documentation test references, and test-side production side effects.

## Findings And Fixes

| Finding | Action |
|---|---|
| `tests/test_boundary.py` was a print-based script, not a pytest module, while `docs/acceptance-matrix.md` treated it as an acceptance contract. | Rewrote it into collected pytest tests with explicit assertions. |
| The old boundary script wrote and restored real `data/store` Buffett result files. | Replaced real store access with isolated `DataHub`/DuckDB monkeypatching under `tmp_path`. |
| `tests/test_new_modules.py` was an uncollected smoke script duplicating collected syntax/import/DSL/broker tests. | Removed it. |
| `tests/run_all.py` hid live-data `test_*` functions in a non-collected script and could trigger real market/financial fetches. | Removed it. |
| Factor promotion tests modified the real `signals/expression.py` file and restored it afterward. | Added injectable `EXPRESSION_PATH` and changed tests to promote into a temporary expression file. |
| `signals/dsl_parser.py` documented `close_t-N` lag references, but parsed them as arithmetic subtraction because bare `close_t` was translated first. | Fixed translation order and added a regression assertion for `close_t / close_t-3 - 1`. |
| Signal-system docs described stale `Close/SMA/RSI/MACD/parse_and_compute` DSL contracts that do not match current code. | Updated acceptance matrix and signal spec to `Ref/Ret/MA/Std/Delta` and `compute_formula`. |

## Guardrails Added

`tests/test_test_suite_health.py` now blocks these stale-test patterns:

- `test*.py` files without pytest-collected test functions/classes.
- top-level calls or assertions in pytest modules, which usually means script-style tests.
- non-collected support files under `tests/` hiding `test_*` functions.
- acceptance matrix references to missing `test_*.py` files.
- generated Python bytecode files being tracked by git under `tests/`.

## Inventory

Current collection after cleanup: 590 pytest tests.

| File | Tests | Classes | Lines | Audit note |
|---|---:|---:|---:|---|
| `test_api_services.py` | 7 | 0 | 174 | API service contracts; kept. |
| `test_architecture_contracts.py` | 48 | 0 | 751 | Broad architecture/source contracts; kept because they guard recent modularization and doc consistency. |
| `test_asset_contracts.py` | 27 | 6 | 307 | Asset adapter contracts; kept. |
| `test_audit.py` | 14 | 3 | 141 | Audit ledger contracts; kept. |
| `test_auth.py` | 21 | 4 | 380 | Auth/settings security contracts; kept. |
| `test_backfill.py` | 22 | 5 | 219 | Backfill ledger contracts; kept. |
| `test_backtest_pipeline_runner_contracts.py` | 2 | 0 | 116 | Production PipelineBacktest stage contracts; kept. |
| `test_backtest_pit_contracts.py` | 4 | 1 | 79 | PIT/no-lookahead contracts; kept. |
| `test_backtest_reproducibility.py` | 3 | 1 | 104 | Deterministic backtest contract; kept. |
| `test_boundary.py` | 5 | 0 | 245 | Converted from old script into collected cross-module boundary contracts. |
| `test_broker_risk_persistence_allocator.py` | 5 | 0 | 150 | Broker/risk/allocation regression contracts; kept. |
| `test_buffett_financial_sector.py` | 1 | 0 | 39 | Bank moat special-case contract; kept. |
| `test_candidate_strategy_contracts.py` | 3 | 0 | 54 | Candidate strategy output contracts; kept. |
| `test_cli_data_commands.py` | 2 | 0 | 36 | CLI data commands; kept. |
| `test_cli_foundation.py` | 7 | 0 | 86 | CLI JSON and docs contracts; kept. |
| `test_cli_ops_commands.py` | 5 | 0 | 86 | CLI ops commands; kept. |
| `test_cli_strategy_commands.py` | 5 | 0 | 92 | CLI strategy commands; kept. |
| `test_contract.py` | 24 | 4 | 314 | Generic data contract utilities; kept. |
| `test_cron_logger_contracts.py` | 7 | 4 | 101 | Cron log contracts; kept. |
| `test_data_cleaner_contracts.py` | 11 | 6 | 198 | Data cleaner contracts; kept. |
| `test_data_fetcher_resilience.py` | 5 | 2 | 114 | Retry/throttle contracts with monkeypatched time; kept. |
| `test_datahub_contracts.py` | 8 | 0 | 152 | DataHub registry/path/health contracts; kept. |
| `test_documentation_contracts.py` | 3 | 0 | 68 | Acceptance/documentation consistency; kept. |
| `test_execution_observability.py` | 5 | 1 | 76 | Execution observability contracts; kept. |
| `test_factor_gate.py` | 15 | 5 | 208 | Candidate factor gate contracts; changed to isolated expression file. |
| `test_fill_models.py` | 25 | 8 | 200 | Fill model contracts; kept. |
| `test_frontend_i18n_contracts.py` | 4 | 0 | 82 | Frontend localization contracts; kept. |
| `test_hindsight_contracts.py` | 1 | 0 | 20 | Hindsight contract; kept. |
| `test_hmm_engine.py` | 2 | 0 | 80 | HMM engine contract; kept. |
| `test_ledger.py` | 19 | 6 | 350 | Event ledger contracts using temporary storage; kept. |
| `test_market_data_view.py` | 3 | 0 | 48 | Market data view contracts; kept. |
| `test_market_regime_v2.py` | 10 | 0 | 358 | Regime scoring/state contracts with synthetic data; kept. |
| `test_market_route_contracts.py` | 5 | 0 | 111 | Market API contracts; kept. |
| `test_modularization_contracts.py` | 7 | 0 | 184 | Module size/split contracts; kept. |
| `test_multi_asset_tournament.py` | 12 | 4 | 127 | Multi-asset contracts; kept. |
| `test_order_sm.py` | 22 | 1 | 172 | Order state machine contracts; kept. |
| `test_pipeline_contracts.py` | 23 | 9 | 259 | Pipeline domain contracts; kept. |
| `test_pipeline_route_contracts.py` | 4 | 0 | 264 | Pipeline API/parameter transparency contracts; kept. |
| `test_project_version.py` | 4 | 0 | 94 | Version bump contracts; kept. |
| `test_provider.py` | 18 | 5 | 216 | Provider capability/status contracts; kept. |
| `test_quality_gate.py` | 13 | 1 | 357 | Quality gate contracts with isolated DataHub roots; kept. |
| `test_regime_profit_training.py` | 11 | 0 | 358 | Profit-oriented regime training contracts; kept. |
| `test_regime_scoring.py` | 8 | 0 | 133 | Regime scoring contracts; kept. |
| `test_regime_state.py` | 4 | 0 | 89 | Regime state machine contracts; kept. |
| `test_regime_training.py` | 10 | 0 | 195 | Regime trainer contracts; kept. |
| `test_registry_status.py` | 26 | 7 | 131 | Registry status contracts; kept. |
| `test_sector_pipeline.py` | 30 | 0 | 685 | Sector pipeline and multifactor integration contracts; kept. |
| `test_settings_schema_contracts.py` | 4 | 0 | 53 | Settings schema contracts; kept. |
| `test_shared_infra.py` | 12 | 0 | 238 | Shared infra contracts; kept. |
| `test_strategy_backtest_evidence.py` | 1 | 0 | 32 | Strategy evidence artifact contract; kept. |
| `test_strategy_catalog.py` | 2 | 0 | 28 | Strategy catalog API contracts; kept. |
| `test_strategy_evaluation.py` | 5 | 0 | 101 | Strategy evaluation contracts; kept. |
| `test_strategy_research_governance.py` | 7 | 0 | 166 | Strategy research governance contracts; kept. |
| `test_strategy_runtime_gates.py` | 4 | 0 | 100 | Runtime mode isolation contracts; kept. |
| `test_test_suite_health.py` | 4 | 0 | 87 | New suite hygiene guardrails. |
| `test_web_system_contracts.py` | 22 | 0 | 534 | Web/API/UI architecture contracts; kept. |
| `test_websocket_contracts.py` | 4 | 1 | 71 | WebSocket contracts; kept. |

## Remaining Risk

- `test_architecture_contracts.py`, `test_web_system_contracts.py`, and `test_sector_pipeline.py` are intentionally broad. They are still valid now, but they should be split by domain if they grow materially again.
- There are generated `tests/__pycache__` files in the working tree, but none are tracked by git. The health test guards the tracked-file case.
