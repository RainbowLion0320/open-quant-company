# Security Scanning and SBOM

Astrolabe uses GitHub-native security automation plus release-time artifact discipline.

## Automated Security Checks

The `Security` workflow runs:

- CodeQL analysis for Python and TypeScript/JavaScript.
- Dependency Review on pull requests.
- CycloneDX SBOM generation as a GitHub Actions artifact.

Dependabot is configured for:

- Python dependencies from the repository root.
- Frontend npm dependencies under `web/frontend`.
- GitHub Actions dependencies.

## SBOM Policy

SBOM files are generated artifacts and are not committed by default. The workflow uploads `sbom.cdx.json` as an Actions artifact so it can be inspected for a specific run or release candidate.

## Vulnerability Reports

Security vulnerabilities should follow `SECURITY.md`. Do not disclose vulnerabilities or secrets in public issues.
