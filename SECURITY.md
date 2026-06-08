# Security Policy

## Supported Scope

Security fixes are considered for the current `main` branch and the latest public release, when releases are available. Older commits, local forks, private notebooks, and untracked runtime artifacts are outside the supported scope.

## Automated Security Controls

The repository uses GitHub Actions for CodeQL analysis, dependency review, and SBOM generation. Dependabot monitors Python, frontend npm, and GitHub Actions dependencies.

These checks reduce risk, but they do not replace responsible disclosure for vulnerabilities involving secrets, local data, authentication, command execution, or provider integrations.

## Reporting a Vulnerability

Do not report security vulnerabilities in public issues.

Use GitHub private vulnerability reporting or GitHub Security Advisories if available for this repository. If that path is not available, contact the repository owner through GitHub profile contact channels and include only the information needed to start a private investigation.

Please include:

- A short description of the vulnerability.
- Affected files, commands, API routes, or workflows.
- Reproduction steps or a proof of concept.
- Impact assessment.
- Whether credentials, local data, generated artifacts, or external APIs are involved.

## What Counts as Security-Sensitive

Examples:

- Secret leakage, including API tokens or webhook URLs.
- Unsafe command execution, path traversal, or arbitrary file access.
- Authentication or authorization bypass in the Web API.
- Accidental exposure of local trading data, raw provider data, model artifacts, or runtime databases.
- Dependency vulnerabilities that are reachable in normal project workflows.

## What Is Usually Not a Security Issue

- Incorrect strategy performance, backtest results, or financial assumptions.
- Missing data coverage from provider permissions or rate limits.
- Local configuration mistakes that do not expose secrets or private data.

These may still be valid bugs, but they should use the normal issue templates.

## Disclosure

Maintainers will review valid reports, coordinate a fix when practical, and credit reporters when requested and appropriate. Please avoid public disclosure until a fix or mitigation is available.
