# Changelog

All notable changes to Open Quant Company are tracked here. The project uses PEP 440-compatible calendar versions for public release tags.

## [2026.6.20.1] - 2026-06-20

### Changed

- Switched public release versions from the previous three-part scheme to calendar versions in the `YYYY.M.D.N` format.
- Made the CLI package version resolve from project metadata instead of a hard-coded string.

## [2.0.0] - 2026-06-08

### Added

- Local-first daily-frequency quant research system with a bilingual Vue Web UI and agent-friendly `astroq` CLI.
- DataHub/DataRegistry storage layer with `var/` as the runtime artifact root.
- Strategy Catalog boundaries for production, paper, and candidate strategies.
- Point-in-time feature store, daily backtest pipeline, PaperBroker execution ledger, and system diagnostics.
- CodeGraph, AST Intelligence, and Test Design Intelligence surfaces under System Control.
- Community standards: contribution guide, code of conduct, security policy, support policy, issue templates, and pull request template.

### Changed

- Cleaned historical compatibility paths and legacy runtime shims in favor of current canonical modules.
- README split into Chinese and English entry points with Web UI screenshots.

### Security

- Secrets are read only from process environment variables.
- Runtime data, caches, databases, generated models, and reports are excluded from git under `var/`.
