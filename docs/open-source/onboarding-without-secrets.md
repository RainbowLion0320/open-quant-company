# Onboarding Without Secrets

Astrolabe should be inspectable without provider credentials. A new contributor can validate the codebase, build the Web UI, and run deterministic checks without `TUSHARE_TOKEN`, `DEEPSEEK_API_KEY`, notification webhooks, or private local data.

## What Works Without Secrets

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements-dev.txt
python -m pip install -e .

.venv/bin/astroq health --json
.venv/bin/astroq config validate --json
.venv/bin/astroq docs check --json
.venv/bin/astroq test design --json
.venv/bin/astroq architecture ast --json
.venv/bin/python -m pytest -q
```

Frontend:

```bash
cd web/frontend
npm ci
npm run typecheck
npm run build
```

## What Requires Secrets

- Full Tushare capability probing and backfill require `TUSHARE_TOKEN`.
- LLM-assisted factor discovery and provider usage checks require provider API keys such as `DEEPSEEK_API_KEY`.
- Push notifications require Telegram, WeChat, or Feishu webhook configuration.

## Local Runtime Data

Generated files go under `var/` by default. They are not committed and should not be attached to public issues unless they are synthetic fixtures with secrets and private records removed.

## Contributor Rule

If a feature cannot be tested without secrets, provide a mocked unit/contract test and document the manual secret-backed verification command in the pull request.
