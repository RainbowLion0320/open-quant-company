# Claude Entry Point

This file is intentionally thin. The shared operating guide for Claude, Codex, cron jobs, and other automation agents is [AGENTS.md](AGENTS.md).

## Required First Read

Before making changes, read:

1. [AGENTS.md](AGENTS.md)
2. [README.md](README.md) or [README.en.md](README.en.md)
3. [docs/product/prd.md](docs/product/prd.md)
4. Relevant files under [docs/specs/](docs/specs/)
5. Relevant concepts or decisions under [wiki/](wiki/index.md)

## Claude-Specific Notes

- Treat current code, tests, specs, wiki, and generated artifacts as the active source of truth.
- Do not rely on historical implementation plans or old progress notes unless the user explicitly asks for history.
- Keep the root README human-facing. Agent rules belong in `AGENTS.md`, not in README.
- Do not stage local runtime residue such as `var/`, `reports/`, `data/cache/`, `.codegraph/`, model outputs, databases, or cache files.
- API secrets must come from process environment variables only; never write secrets into config files, docs, screenshots, or logs.

## Verification

Use the verification gates in [AGENTS.md](AGENTS.md). For documentation-only changes, the normal minimum is:

```bash
git diff --check
astroq docs check --json
.venv/bin/pre-commit run --files <changed-doc-files>
```
