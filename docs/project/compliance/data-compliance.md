# Data Compliance

Astrolabe is code and local workflow infrastructure. It is not a market data redistribution project.

## Provider Terms

Users are responsible for complying with the terms of each data provider they configure, including AKShare, Tushare, brokers, notification providers, and LLM providers. Provider tokens and account-specific data must not be committed to this repository.

## Repository Policy

The repository must not include:

- Paid or provider-restricted raw market data.
- Private trading records.
- API tokens, webhook URLs, account IDs, or credential files.
- Local databases, runtime caches, model artifacts, or generated reports under `var/`.
- Screenshots that expose private account, token, order, or portfolio information.

Allowed committed data is limited to small static reference files, synthetic fixtures, tests, documentation examples, and seed artifacts that are safe to redistribute.

## DataHub Boundary

Runtime data belongs under `var/`:

- `var/store/` for local Parquet stores.
- `var/cache/` for temporary caches and runtime state.
- `var/artifacts/` for backtests, model outputs, reports, and diagnostics.
- `var/db/` for local SQLite/DuckDB files.
- `var/logs/` for local logs.

Code and docs should refer to DataHub paths instead of hard-coded local data paths.

## Research and Backtest Integrity

Contributions that affect research, backtests, or execution should preserve:

- Point-in-time data access.
- Explicit raw versus adjusted price semantics.
- Configurable thresholds and weights.
- Documented assumptions about data availability, provider permissions, and missing data.
