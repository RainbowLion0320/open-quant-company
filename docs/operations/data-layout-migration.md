# Data Layout Migration

> Updated: 2026-06-06

## Purpose

`data/` is now the Python data-layer source package. Local runtime outputs live under `var/` and are ignored by git.

```text
data/
  storage/
  ingestion/
  market/
  features/
  quality/
  ops/
  llm/
  rates/
  strategy/
  reference/

var/
  store/
  cache/
  artifacts/
    backtests/
    models/
    tournaments/
    reports/
  db/
  logs/
  migration/
```

This separates code and static reference files from local caches, databases, trained models, backtest files, and generated reports.

## Commands

Always run a dry run first:

```bash
python scripts/migrate_data_layout.py --dry-run
```

Apply the migration after reviewing the plan:

```bash
python scripts/migrate_data_layout.py --apply
```

Use JSON output for automation:

```bash
python scripts/migrate_data_layout.py --dry-run --json
python scripts/migrate_data_layout.py --apply --json
```

Use `--root <path>` when migrating an isolated checkout or test fixture.

## Migration Rules

| Legacy input | New target |
|--------------|------------|
| `data/store/` | `var/store/` |
| `data/cache/` | `var/cache/` |
| `data/backtest_*.pkl` | `var/artifacts/backtests/` |
| `data/price_matrix_*.pkl` | `var/cache/backtest/` |
| `data/backtest_price_matrix_*.pkl` | `var/cache/backtest/` |
| `data/tournament/` | `var/artifacts/tournaments/` |
| `data/models/*.pkl`, `*.json`, `*.jsonl`, `report.md` | `var/artifacts/models/` |
| `data/quant_results*.db`, `data/quant_results*.duckdb` | `var/db/` |
| `data/.financials_progress.json` | `var/cache/runtime/financials_progress.json` |

Static reference files are not runtime outputs. They live in `data/reference/`, including `tushare_ind.json`, `tushare_industry.json`, `universe_raw.json`, and the seed HMM model under `data/reference/models/regime_hmm/`.

## Manifest And Conflicts

Every apply run writes a manifest:

```text
var/migration/data-layout-YYYYMMDD-HHMMSS.json
```

Each item records source, target, size, hash when available, and final status.

The script never overwrites an existing target. If a target already exists with different content, the item is recorded as `conflict`. Resolve conflicts manually after comparing the old and new files, then keep the manifest with the resolution notes in `var/migration/`.

## Rollback

Rollback is manual and manifest driven:

1. Open the latest manifest in `var/migration/`.
2. For each item with status `moved`, move the target path back to the recorded source path.
3. Do not roll back static reference moves unless you are reverting the code commit too.
4. Re-run `python scripts/migrate_data_layout.py --dry-run` to verify that no unexpected legacy runtime files remain.

## Runtime Configuration

Defaults are declared in `config/settings.yaml`:

| Setting | Default | Environment override |
|---------|---------|----------------------|
| `paths.runtime_root` | `var` | `ASTROLABE_VAR` |
| `paths.store_root` | `var/store` | `ASTROLABE_STORE` |
| `paths.cache_root` | `var/cache` | `ASTROLABE_CACHE` |
| `paths.artifact_root` | `var/artifacts` | `ASTROLABE_ARTIFACTS` |
| `paths.db_root` | `var/db` | `ASTROLABE_DB` |

`ASTROLABE_STORE` and `ASTROLABE_CACHE` remain supported for existing deployments.

## Developer Rules

- New code uses canonical imports such as `data.storage.datahub`, `data.ingestion.fetcher`, `data.market.price_service`, and `data.features.feature_store`.
- Historical top-level data imports have been removed. Use canonical domain packages only.
- `data_registry.cache` remains relative to the DataHub store root. Do not put `var/store` or absolute paths in dimension cache patterns.
- Runtime outputs must go through DataHub path helpers or the `paths.*` config section.
- `data/` root must not contain `.pkl`, `.db`, `.duckdb`, cache/store/tournament directories, or trained model outputs.
