# Release Process

Open Quant Company uses semantic versioning for public tags:

- `MAJOR`: breaking architecture, CLI, API, data layout, or strategy contract changes.
- `MINOR`: new Web UI, CLI, data, strategy, or diagnostics capabilities that preserve current contracts.
- `PATCH`: bug fixes, documentation fixes, dependency updates, and small operational improvements.

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
   git tag -a v2.0.0 -m "Open Quant Company v2.0.0"
   git push origin v2.0.0
   ```

6. The `Release` GitHub Actions workflow builds Python artifacts, builds the frontend bundle, and publishes a GitHub Release for the tag.

## Release Artifacts

The release workflow attaches:

- Python source and wheel distributions from `python -m build`.
- `open-quant-company-frontend-dist.tar.gz`, containing the built Web UI assets.

Runtime data, model artifacts, local databases, provider caches, and reports under `var/` are never release artifacts.
