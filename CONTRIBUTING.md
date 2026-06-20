# Contributing to Open Quant Company

Thank you for considering a contribution. Open Quant Company is treated as a real open source project, not a demo repository. Contributions should preserve reproducibility, data integrity, and clear boundaries between research, paper trading, and production-like workflows.

## Project Principles

- Keep the Web UI and `astroq` CLI aligned. A capability exposed in one surface should not drift from the other without a clear reason.
- Prefer canonical modules over local reimplementations. Data access should go through DataHub/DataRegistry, strategy state through Strategy Catalog, and execution state through PaperBroker-related services.
- Do not commit secrets, API tokens, raw private data, local databases, model artifacts, or files under `var/`.
- Use point-in-time data rules for research and backtests. Avoid shortcuts that introduce lookahead bias.
- Make dynamic values configurable instead of hard-coding thresholds, weights, credentials, or local paths.
- Documentation, specs, tests, and code should describe the same current design.

Project governance and long-lived contributor expectations are also documented in:

- `docs/project/governance.md`
- `docs/project/maintainers.md`
- `docs/project/roadmap.md`
- `docs/project/release.md`
- `docs/project/compliance/data-compliance.md`
- `docs/project/compliance/privacy.md`
- `docs/project/compliance/onboarding-without-secrets.md`

## Development Setup

Requirements:

- Python 3.11+
- Node.js 18+
- Git
- ripgrep (`rg`) for documentation drift checks

Basic setup:

```bash
git clone https://github.com/RainbowLion0320/open-quant-company.git
cd open-quant-company

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,ml]"

cd web/frontend
npm install
```

If you only need the minimal runtime:

```bash
python -m pip install -e .
```

Install local git hooks if you want the same lightweight checks before every commit:

```bash
pre-commit install
pre-commit run --all-files
```

The current ruff gate is intentionally conservative. It checks syntax, invalid constructs, control-flow errors, and undefined names without forcing a full historical style rewrite.

## Secrets and Local Data

Open Quant Company reads secrets only from process environment variables. Do not add secrets to YAML, `.env`, notebooks, tests, screenshots, or documentation.

Common variables:

- `TUSHARE_TOKEN`
- `DEEPSEEK_API_KEY`
- `ASTROLABE_API_KEY`
- `ASTROLABE_VAR`

Local runtime outputs belong under `var/` and are ignored by git. This includes data stores, caches, databases, backtest artifacts, model artifacts, logs, and generated reports.

## Before Opening a Pull Request

Run the smallest relevant checks for your change. For broad changes, run the full set:

```bash
cd web/frontend && npm ci && cd ../..
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q astrolabe_cli backtest broker cybernetics data models pipeline research scripts signals tests web/api
.venv/bin/astroq docs check --json
cd web/frontend && npm run typecheck && npm run build
git diff --check
```

For focused changes, include targeted tests in the pull request description and explain why they are sufficient.

## Pull Request Expectations

A good pull request should include:

- A clear problem statement.
- A concise summary of the solution.
- Tests or verification commands with actual results.
- Notes about data, config, or migration impact.
- Screenshots for user-facing Web UI changes.
- Documentation updates when behavior, architecture, CLI commands, or public workflows change.

Avoid unrelated refactors in the same pull request. If a cleanup is useful but not required, open a separate issue or pull request.

## Issue Guidelines

Use the issue templates when possible. Include enough context for maintainers to reproduce the behavior:

- Command, route, or workflow involved.
- Expected behavior and actual behavior.
- Relevant logs or tracebacks with secrets removed.
- OS, Python version, Node version, and browser when relevant.
- Whether the issue affects Web UI, CLI, data ingestion, strategy runtime, backtesting, or execution.

## Financial Disclaimer

Open Quant Company is research and infrastructure software. It is not investment advice, does not promise returns, and should not be used as the only basis for trading decisions.
