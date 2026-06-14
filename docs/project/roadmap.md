# Roadmap

Open Quant Company is developed as a local-first quant research and execution operating system. This roadmap describes direction, not guaranteed delivery dates.

## Near Term

- Keep Web UI and `astroq` CLI behavior aligned for system control, data health, strategy evidence, and diagnostics.
- Harden CI, dependency automation, security scanning, and release automation for public contributions.
- Improve no-token onboarding with documented offline checks and deterministic local fixtures.
- Expand data coverage reports for Tushare permissions and local completeness.

## Mid Term

- Improve strategy promotion workflows from candidate to paper to production with stronger evidence gates.
- Add more deterministic architecture diagnostics for duplicated code paths, canonical helper bypass, and high-coupling modules.
- Strengthen PaperBroker accounting, execution reports, and reconciliation views.
- Build richer risk-free rate, corporate action, and adjusted/raw price validation around backtests and execution.

## Long Term

- Support more asset classes and provider backends without hard-coding provider assumptions.
- Make research evidence more reproducible across machines through portable manifests and fixture packs.
- Add optional deployment profiles while preserving local-first defaults.
- Mature the project toward stable extension contracts for strategies, data dimensions, and Web diagnostics.

## Non-Goals

- Open Quant Company is not investment advice and does not promise returns.
- The repository will not redistribute paid provider data or private trading records.
- Web UI convenience should not bypass the CLI/control-plane contracts used by automation.
