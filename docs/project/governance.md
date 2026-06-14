# Governance

Open Quant Company is maintained as a pragmatic open source project with a small-maintainer model.

## Maintainer Authority

Maintainers are responsible for:

- Project direction and architecture boundaries.
- Reviewing and merging pull requests.
- Enforcing the Code of Conduct.
- Handling security reports.
- Deciding release timing and versioning.
- Protecting secrets, local data boundaries, and provider compliance.

The current maintainer list is in `maintainers.md`.

## Decision Principles

Technical decisions should prioritize:

- Reproducibility over convenience.
- Point-in-time correctness over optimistic shortcuts.
- Canonical modules over repeated local implementations.
- Web UI and CLI consistency.
- Clear data, strategy, backtest, and execution boundaries.
- Explicit configuration over hidden hard-coded values.

## Contribution Review

Pull requests are evaluated on:

- Correctness and maintainability.
- Tests and verification evidence.
- Documentation updates when behavior changes.
- Impact on data integrity, secrets handling, and local runtime artifacts.
- Whether the change preserves current architecture contracts.

Large changes should start as an issue or design discussion before implementation.

## Breaking Changes

Breaking changes are allowed when they simplify the current architecture or remove obsolete compatibility paths, but they must be explicit. A breaking change should update:

- `CHANGELOG.md`
- README or relevant docs/specs/wiki pages
- Tests or architecture contracts
- Migration notes when user action is required

## Financial Boundary

Maintainers and contributors must avoid presenting project behavior as investment advice, trading recommendations, or guaranteed returns.
