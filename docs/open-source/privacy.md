# Privacy

Astrolabe is local-first by design. The application does not intentionally collect telemetry from users, upload local trading records, or send repository runtime data to project maintainers.

## Local-First Defaults

By default, runtime outputs stay on the user's machine under `var/`. This includes local data stores, caches, generated reports, model artifacts, test artifacts, and databases.

## External Calls

Astrolabe can make external calls when the user explicitly configures provider credentials or runs workflows that require network access:

- Market data providers such as AKShare and Tushare.
- LLM providers configured for factor research or usage reporting.
- Notification providers such as Telegram, WeChat, and Feishu.
- GitHub Actions when CI, security scanning, or release workflows run in the repository.

External provider behavior is governed by each provider's own terms and privacy policies.

## Secrets

Secrets are read from process environment variables. They should not be stored in YAML config, `.env` files, screenshots, notebooks, issue reports, logs, or committed artifacts.

## Public Issues and Pull Requests

Before posting logs or screenshots, remove:

- API tokens and webhook URLs.
- Account IDs and private identifiers.
- Portfolio holdings, orders, or trading records that should remain private.
- Provider-restricted data.
