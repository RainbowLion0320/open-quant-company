# DataHub Internal Modularization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or an equivalent task-by-task implementation flow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `DataHub` as the stable data-access facade while splitting internal path, parquet, manifest, dimension, and freshness-gate responsibilities into focused modules.

**Architecture:** External callers continue importing `DataHub`, `get_datahub()`, and `reset_datahub()` from `data/datahub.py`. New internal modules own single responsibilities, and `DataHub` delegates to them without changing public method signatures. This is not decentralization: business modules should still depend on `DataHub`, while `DataHub` must not depend on strategy, web, CLI, or execution logic.

**Tech Stack:** Python 3.11, pandas/pyarrow parquet, pytest, CodeGraph.

---

## Scope

- Preserve every existing `DataHub` public method and return shape.
- Reduce `data/datahub.py` from an implementation-heavy module to a facade plus catalog/audit orchestration.
- Move shared data health freshness-gate logic from CLI/Web into `data.freshness_gate`.
- Add architecture tests that prevent Web API from depending on CLI and prevent Pipeline service from importing entrypoint scripts directly.
- Update data pipeline documentation to describe `DataHub` as a facade with internal components.

## Out of Scope

- No storage backend migration.
- No external API rename.
- No DataRegistry schema redesign.
- No runtime behavior change for writes, manifest recording, or dimension path expansion.

## Target File Structure

- Create `data/datahub_paths.py`: path resolution, safe path leaves, env lookup, store/cache helper paths.
- Create `data/datahub_manifest.py`: manifest read, lookup, schema hash, file hash, date range, manifest record.
- Create `data/datahub_parquet.py`: atomic parquet read/write/append/latest/list helpers.
- Create `data/datahub_dimensions.py`: registry cache root/path expansion and latest snapshot discovery.
- Create `data/freshness_gate.py`: shared freshness gate and health-result normalization.
- Modify `data/datahub.py`: preserve facade API and delegate to internal components.
- Modify `astrolabe_cli/commands/data.py`: re-export/use shared freshness helpers.
- Modify `web/api/services/system_data_health.py`: encapsulate health-check execution for Web services.
- Modify `web/api/services/pipeline.py`: depend on Web service boundary, not CLI/scripts.
- Modify `tests/test_datahub_contracts.py`: assert facade delegates to internal components and preserves behavior.
- Modify `tests/test_architecture_contracts.py`: lock the new dependency boundaries.
- Modify `docs/specs/01-data-pipeline.md` and `wiki/decisions/datahub.md`: document the facade/component split.

## Tasks

### Task 1: Protect Existing Facade Behavior

- [x] Add failing tests in `tests/test_datahub_contracts.py` that assert `DataHub` has internal `paths`, `parquet`, `manifest`, and `dimensions` components while preserving existing path/write/manifest behavior.
- [x] Run the new tests and confirm they fail before production code exists.

### Task 2: Split Shared Freshness Gate

- [x] Create `data/freshness_gate.py`.
- [x] Move CLI-local `freshness_gate()` and health-result normalization into the shared module.
- [x] Update CLI and Web services to use the shared data-domain logic.
- [x] Add architecture tests preventing Web API from importing `astrolabe_cli` and preventing Pipeline service from importing `scripts.*`.

### Task 3: Split DataHub Internal Components

- [x] Create `data/datahub_paths.py` and move path helper behavior behind `DataHubPaths`.
- [x] Create `data/datahub_manifest.py` and move manifest helper behavior behind `ManifestStore`.
- [x] Create `data/datahub_parquet.py` and move parquet helper behavior behind `ParquetStore`.
- [x] Create `data/datahub_dimensions.py` and move registry dimension behavior behind `DimensionStore`.
- [x] Update `data/datahub.py` so public methods delegate to these components and keep method signatures unchanged.

### Task 4: Documentation Alignment

- [x] Update `docs/specs/01-data-pipeline.md` to describe `DataHub` as a facade with `DataHubPaths`, `ParquetStore`, `ManifestStore`, and `DimensionStore`.
- [x] Update `wiki/decisions/datahub.md` with the same design intent: center data access, not business logic.

### Task 5: Verification

- [x] Run targeted tests:
  - `PYTHONPATH=. .venv/bin/python -m pytest tests/test_datahub_contracts.py tests/test_shared_infra.py tests/test_architecture_contracts.py tests/test_cli_data_commands.py tests/test_execution_observability.py tests/test_pipeline_route_contracts.py -q`
- [x] Run full tests:
  - `PYTHONPATH=. .venv/bin/python -m pytest -q`
- [x] Run CodeGraph sync and inspect fanout:
  - `codegraph sync .`
  - `codegraph status .`

## Acceptance Criteria

- Existing callers still use `from data.datahub import DataHub, get_datahub`.
- `DataHub.write_parquet()` still writes atomically and records manifest metadata.
- `DataHub.append_parquet()` still uses file locks and dedupe/sort behavior.
- `DataHub.dimension_path()`, `dimension_root()`, `list_dimension_snapshots()`, and `latest_dimension_snapshot()` still work from DataRegistry cache patterns.
- `web/api` contains no `astrolabe_cli` imports.
- `web/api/services/pipeline.py` contains no direct `scripts.*` imports.
- Full pytest passes.
