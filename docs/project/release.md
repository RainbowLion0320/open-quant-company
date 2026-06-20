# Release Process

Open Quant Company uses PEP 440-compatible calendar versions for public tags:

- Format: `YYYY.M.D.N`, for example `2026.6.20.1`.
- `YYYY.M.D` is the release date.
- `N` is the release sequence for that date, starting at `1`.
- Breaking changes, new capabilities, fixes, and dependency updates are described in `CHANGELOG.md` instead of encoded into the version number.
- Git tags use a `v` prefix, for example `v2026.6.20.1`.

## Release Checklist

1. Update `pyproject.toml` `[project].version`.
2. Update `CHANGELOG.md` with the release date and notable changes.
3. Run the release verification gate locally:

   ```bash
   .venv/bin/python -m pytest -q
   .venv/bin/python -m compileall -q astrolabe_cli backtest broker cybernetics data models pipeline research scripts signals tests web/api
   .venv/bin/astroq docs check --json
   cd web/frontend && npm run typecheck && npm run build
   git diff --check
   ```

4. Commit the version and changelog changes.
5. Create and push an annotated tag:

   ```bash
   git tag -a v2026.6.20.1 -m "Open Quant Company v2026.6.20.1"
   git push origin v2026.6.20.1
   ```

6. The `Release` GitHub Actions workflow builds Python artifacts, builds the frontend bundle, and publishes a GitHub Release for the tag.

## Release Artifacts

The release workflow attaches:

- Python source and wheel distributions from `python -m build`.
- `open-quant-company-frontend-dist.tar.gz`, containing the built Web UI assets.

Runtime data, model artifacts, local databases, provider caches, and reports under `var/` are never release artifacts.
