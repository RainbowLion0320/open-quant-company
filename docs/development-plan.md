# CLI Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified `astroq` CLI control plane so agents, cron jobs and local operators can inspect, validate, run and repair Astrolabe Quant OS through stable, JSON-capable commands.

**Architecture:** The CLI is an orchestration layer only. It must call existing domain modules in `data/`, `signals/`, `research/`, `backtest/`, `scripts/` and `web/` instead of duplicating business logic. Commands return a typed `CliResult`, support `--json`, use consistent exit codes, and require explicit flags for write or long-running actions.

**Tech Stack:** Python 3.11, stdlib `argparse`, existing project modules, pytest, FastAPI/uvicorn for web serving, no new runtime dependency.

---

## Non-Negotiable Rules

- CLI must not bypass Strategy Catalog, runtime mode gates, DataHub paths, settings validation or existing safety rules.
- CLI must not reimplement data fetching, strategy scoring, backtesting, regime training or web services.
- Every command that can write data, start a long task, repair data, or run research must support `--dry-run` where meaningful and require explicit arguments.
- Every command intended for agents must support `--json` with stable keys: `ok`, `command`, `data`, `message`, `errors`.
- Default strategy execution mode is `production`; candidate strategy scans require `--mode research`.
- Old scripts remain callable during transition, but docs and agent-facing examples must point to `astroq`.
- Do not push commits unless the user explicitly asks.

## Command Name Decision

The public command name is `astroq`.

Name checks performed on 2026-05-29:

- `npm view quant name --silent`: no exact package found, but `quant` is too generic and has high future collision risk.
- `npm view astrolabe name --silent`: exact package exists, do not use.
- `npm view astroq name --silent`: no exact package found.
- `command -v astroq`: no local command found.

Rationale: `astroq` is short, English, tied to Astrolabe Quant, and less likely to collide than generic names such as `quant` or taken names such as `astrolabe`.

## Target Command Surface

```bash
astroq --help
astroq health [--json]
astroq config validate [--json]
astroq data status [--json]
astroq data repair <table> [--limit N] [--days N] [--dry-run] [--json]
astroq strategy catalog [--json]
astroq strategy run <name|all> [--mode production|research] [--limit N] [--dry-run] [--json]
astroq strategy evidence <name> [--json]
astroq regime status [--json]
astroq regime train-profit [--dry-run] [--json]
astroq backtest run [--strategy NAME] [--dry-run] [--json]
astroq docs check [--json]
astroq web build [--json]
astroq web serve [--host HOST] [--port PORT]
```

## File Map

Create:

- `astrolabe_cli/__init__.py` — package marker and exported version.
- `astrolabe_cli/main.py` — argparse entrypoint and command dispatch.
- `astrolabe_cli/results.py` — `CliResult`, `ExitCode`, JSON/text rendering.
- `astrolabe_cli/safety.py` — dry-run helpers and explicit-mode validation.
- `astrolabe_cli/commands/__init__.py` — command package marker.
- `astrolabe_cli/commands/health.py` — `astroq health`.
- `astrolabe_cli/commands/config.py` — `astroq config validate`.
- `astrolabe_cli/commands/data.py` — `astroq data status/repair`.
- `astrolabe_cli/commands/strategy.py` — `astroq strategy catalog/run/evidence`.
- `astrolabe_cli/commands/regime.py` — `astroq regime status/train-profit`.
- `astrolabe_cli/commands/backtest.py` — `astroq backtest run`.
- `astrolabe_cli/commands/docs.py` — `astroq docs check`.
- `astrolabe_cli/commands/web.py` — `astroq web build/serve`.
- `tests/test_cli_foundation.py` — base parser/result/console-script contract.
- `tests/test_cli_strategy_commands.py` — Strategy Catalog/run/evidence commands.
- `tests/test_cli_data_commands.py` — DB health and repair command safety.
- `tests/test_cli_ops_commands.py` — health/config/regime/backtest/docs/web command contracts.

Modify:

- `pyproject.toml` — add `astrolabe_cli*` package and `[project.scripts] astroq = "astrolabe_cli.main:main"`.
- `Makefile` — replace script-heavy targets with `astroq` wrappers where stable.
- `docs/DOCUMENTATION.md` — document CLI as agent-facing control plane.
- `docs/specs/05-web-platform.md` — mention CLI control plane for local operation.
- `docs/acceptance-matrix.md` — add CLI acceptance rows.

Do not modify:

- Strategy formulas, Market Regime production policy, DataHub storage format, or Web UI layout unless a CLI test exposes a real bug.

---

## Task 1: CLI Foundation And Console Script

**Files:**
- Create: `astrolabe_cli/__init__.py`
- Create: `astrolabe_cli/main.py`
- Create: `astrolabe_cli/results.py`
- Create: `astrolabe_cli/commands/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli_foundation.py`

- [ ] **Step 1: Write failing foundation tests**

Create `tests/test_cli_foundation.py`:

```python
import json


def test_cli_result_json_shape():
    from astrolabe_cli.results import CliResult

    payload = CliResult(ok=True, command="health", data={"status": "ok"}, message="ready").to_dict()

    assert payload == {
        "ok": True,
        "command": "health",
        "data": {"status": "ok"},
        "message": "ready",
        "errors": [],
    }


def test_cli_health_help_exits_zero(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["health", "--help"])
    out = capsys.readouterr().out

    assert code == 0
    assert "usage:" in out


def test_cli_json_flag_renders_json(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["health", "--json"])
    out = capsys.readouterr().out

    assert code == 0
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["command"] == "health"
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_foundation.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'astrolabe_cli'`.

- [ ] **Step 3: Add result contract**

Create `astrolabe_cli/__init__.py`:

```python
"""Agent-facing CLI control plane for Astrolabe Quant OS."""

__all__ = ["__version__"]
__version__ = "2.0.0"
```

Create `astrolabe_cli/results.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2
    FAILED = 1


@dataclass(frozen=True)
class CliResult:
    ok: bool
    command: str
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "data": self.data,
            "message": self.message,
            "errors": self.errors,
        }

    def render_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    def render_text(self) -> str:
        status = "OK" if self.ok else "ERROR"
        lines = [f"{status}: {self.message or self.command}"]
        for key, value in self.data.items():
            lines.append(f"{key}: {value}")
        for err in self.errors:
            lines.append(f"error: {err}")
        return "\n".join(lines)
```

- [ ] **Step 4: Add argparse entrypoint**

Create `astrolabe_cli/commands/__init__.py`:

```python
"""CLI command implementations."""
```

Create `astrolabe_cli/main.py`:

```python
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from astrolabe_cli.results import CliResult, ExitCode


def _health_command(args: argparse.Namespace) -> CliResult:
    return CliResult(
        ok=True,
        command="health",
        data={"status": "ok"},
        message="Astrolabe CLI ready",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="astroq", description="Astrolabe Quant OS control plane")
    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="Check CLI and local project health")
    health.add_argument("--json", action="store_true", help="Render machine-readable JSON")
    health.set_defaults(handler=_health_command)

    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    result: CliResult = args.handler(args)
    output = result.render_json() if getattr(args, "json", False) else result.render_text()
    print(output)
    return int(ExitCode.OK if result.ok else ExitCode.FAILED)


def main() -> None:
    raise SystemExit(run_cli(sys.argv[1:]))
```

- [ ] **Step 5: Add console script**

Modify `pyproject.toml`:

```toml
[project.scripts]
astroq = "astrolabe_cli.main:main"
```

Add package include:

```toml
include = [
    "astrolabe_cli*",
    "backtest*",
    "broker*",
    "core*",
    "cybernetics*",
    "data*",
    "models*",
    "notify*",
    "pipeline*",
    "research*",
    "scripts*",
    "signals*",
    "web*",
]
```

- [ ] **Step 6: Run foundation tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_foundation.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add astrolabe_cli pyproject.toml tests/test_cli_foundation.py
git commit -m "codex: add astroq cli foundation"
```

---

## Task 2: Shared Command Rendering And Safety Helpers

**Files:**
- Create: `astrolabe_cli/safety.py`
- Modify: `astrolabe_cli/main.py`
- Modify: `astrolabe_cli/results.py`
- Test: `tests/test_cli_foundation.py`

- [ ] **Step 1: Add failing tests for errors and dry-run safety**

Append to `tests/test_cli_foundation.py`:

```python
def test_unknown_command_returns_usage_exit():
    from astrolabe_cli.main import run_cli

    try:
        run_cli(["missing"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("argparse should exit for unknown command")


def test_validate_runtime_mode_rejects_invalid_mode():
    from astrolabe_cli.safety import validate_runtime_mode

    try:
        validate_runtime_mode("paper")
    except ValueError as exc:
        assert "Invalid runtime mode" in str(exc)
    else:
        raise AssertionError("invalid runtime mode should fail")
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_foundation.py::test_validate_runtime_mode_rejects_invalid_mode -q
```

Expected: FAIL because `astrolabe_cli.safety` does not exist.

- [ ] **Step 3: Add safety helpers**

Create `astrolabe_cli/safety.py`:

```python
from __future__ import annotations


VALID_RUNTIME_MODES = {"production", "research"}


def validate_runtime_mode(mode: str) -> str:
    if mode not in VALID_RUNTIME_MODES:
        raise ValueError(f"Invalid runtime mode: {mode}. Expected production or research.")
    return mode


def dry_run_payload(action: str, **kwargs) -> dict:
    return {
        "dry_run": True,
        "action": action,
        "would_run": kwargs,
    }
```

- [ ] **Step 4: Ensure all subcommands can inherit `--json`**

Modify `astrolabe_cli/main.py` so every command can add `--json` consistently:

```python
def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Render machine-readable JSON")
```

Replace direct `health.add_argument("--json", ...)` with:

```python
add_common_flags(health)
```

- [ ] **Step 5: Run foundation tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_foundation.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add astrolabe_cli tests/test_cli_foundation.py
git commit -m "codex: add cli safety helpers"
```

---

## Task 3: Health And Config Commands

**Files:**
- Create: `astrolabe_cli/commands/health.py`
- Create: `astrolabe_cli/commands/config.py`
- Modify: `astrolabe_cli/main.py`
- Test: `tests/test_cli_ops_commands.py`

- [ ] **Step 1: Write failing ops command tests**

Create `tests/test_cli_ops_commands.py`:

```python
import json


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_health_command_reports_core_sections(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["health", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["project"] == "astrolabe-quant"
    assert "version" in data["data"]
    assert "store_root" in data["data"]


def test_config_validate_reports_strategy_count(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["config", "validate", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["strategy_count"] >= 4
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_ops_commands.py::test_config_validate_reports_strategy_count -q
```

Expected: FAIL because `config` command is not registered.

- [ ] **Step 3: Implement health command**

Create `astrolabe_cli/commands/health.py`:

```python
from __future__ import annotations

from astrolabe_cli.results import CliResult


def run_health() -> CliResult:
    from data.datahub import get_datahub
    from web.api.version import get_project_version

    hub = get_datahub()
    return CliResult(
        ok=True,
        command="health",
        message="Astrolabe local environment is reachable",
        data={
            "project": "astrolabe-quant",
            "version": get_project_version(),
            "store_root": str(hub.store_root),
            "cache_root": str(hub.cache_root),
        },
    )
```

- [ ] **Step 4: Implement config validate command**

Create `astrolabe_cli/commands/config.py`:

```python
from __future__ import annotations

from astrolabe_cli.results import CliResult


def validate_config() -> CliResult:
    from core.settings import get_settings
    from data.registry import get_enabled_strategies, load_registry

    cfg = get_settings()
    registry = load_registry(force_reload=True)
    enabled = get_enabled_strategies()
    required = {"strategies", "backtest", "risk_control"}
    missing = sorted(section for section in required if section not in cfg)
    ok = not missing
    return CliResult(
        ok=ok,
        command="config validate",
        message="Config valid" if ok else "Config missing required sections",
        data={
            "strategy_count": len(registry),
            "enabled_strategy_count": len(enabled),
            "missing_sections": missing,
        },
        errors=[f"missing section: {name}" for name in missing],
    )
```

- [ ] **Step 5: Register commands in parser**

Modify `astrolabe_cli/main.py`:

```python
from astrolabe_cli.commands.config import validate_config
from astrolabe_cli.commands.health import run_health
```

Replace `_health_command` body:

```python
def _health_command(args: argparse.Namespace) -> CliResult:
    return run_health()
```

Add config parser:

```python
config = sub.add_parser("config", help="Inspect and validate project configuration")
config_sub = config.add_subparsers(dest="config_command", required=True)
config_validate = config_sub.add_parser("validate", help="Validate settings and strategy registry")
add_common_flags(config_validate)
config_validate.set_defaults(handler=lambda args: validate_config())
```

- [ ] **Step 6: Run tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_foundation.py tests/test_cli_ops_commands.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add astrolabe_cli tests/test_cli_ops_commands.py
git commit -m "codex: add cli health and config commands"
```

---

## Task 4: Strategy Catalog, Run And Evidence Commands

**Files:**
- Create: `astrolabe_cli/commands/strategy.py`
- Modify: `astrolabe_cli/main.py`
- Test: `tests/test_cli_strategy_commands.py`

- [ ] **Step 1: Write failing strategy command tests**

Create `tests/test_cli_strategy_commands.py`:

```python
import json


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_strategy_catalog_command_outputs_items(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["strategy", "catalog", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["total"] >= 4
    assert any(item["name"] == "multifactor" for item in data["data"]["items"])


def test_strategy_run_dry_run_requires_explicit_research_for_candidate(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["strategy", "run", "trend_following", "--dry-run", "--json"])
    data = _json_from_cli(capsys)

    assert code == 1
    assert data["ok"] is False
    assert "research" in data["message"]


def test_strategy_run_research_dry_run_lists_candidate(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["strategy", "run", "trend_following", "--mode", "research", "--dry-run", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["data"]["dry_run"] is True
    assert data["data"]["would_run"]["strategy"] == "trend_following"
    assert data["data"]["would_run"]["mode"] == "research"
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_strategy_commands.py -q
```

Expected: FAIL because `strategy` command is not registered.

- [ ] **Step 3: Implement strategy commands**

Create `astrolabe_cli/commands/strategy.py`:

```python
from __future__ import annotations

from pathlib import Path

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload, validate_runtime_mode


def catalog() -> CliResult:
    from research.strategy_catalog import catalog_items

    items = [item.__dict__ for item in catalog_items()]
    return CliResult(
        ok=True,
        command="strategy catalog",
        message=f"{len(items)} strategies",
        data={"items": items, "total": len(items)},
    )


def run_strategy(strategy: str, mode: str, limit: int, dry_run: bool) -> CliResult:
    from data.registry import get_strategy
    from data.strategy_plugins import iter_strategy_plugins, run_registered_strategies

    mode = validate_runtime_mode(mode)
    meta = get_strategy(strategy) if strategy != "all" else {"status": "production"}
    if not meta:
        return CliResult(False, "strategy run", message=f"Unknown strategy: {strategy}", errors=[strategy])
    if strategy != "all" and meta.get("status") != "production" and mode != "research":
        return CliResult(
            ok=False,
            command="strategy run",
            message=f"{strategy} is not production; rerun with --mode research",
            errors=["candidate_requires_research_mode"],
        )

    plugins = [plugin.name for plugin in iter_strategy_plugins(strategy, mode=mode)]
    if dry_run:
        return CliResult(
            ok=True,
            command="strategy run",
            message=f"Dry run: {len(plugins)} strategy plugin(s)",
            data=dry_run_payload("strategy.run", strategy=strategy, mode=mode, limit=limit, plugins=plugins),
        )

    result = run_registered_strategies(strategy, limit=limit, mode=mode)
    return CliResult(
        ok=True,
        command="strategy run",
        message=f"Ran {strategy} in {mode} mode",
        data={"strategies": result, "mode": mode},
    )


def evidence(strategy: str) -> CliResult:
    from research.strategy_evaluation import strategy_evidence_dir

    path = strategy_evidence_dir() / f"{strategy}.json"
    if not path.exists():
        return CliResult(
            ok=False,
            command="strategy evidence",
            message=f"No evidence report found for {strategy}",
            data={"path": str(path)},
            errors=["evidence_missing"],
        )
    return CliResult(
        ok=True,
        command="strategy evidence",
        message=f"Evidence report found for {strategy}",
        data={"path": str(Path(path).resolve())},
    )
```

- [ ] **Step 4: Register strategy parser**

Modify `astrolabe_cli/main.py`:

```python
from astrolabe_cli.commands.strategy import catalog as strategy_catalog
from astrolabe_cli.commands.strategy import evidence as strategy_evidence
from astrolabe_cli.commands.strategy import run_strategy
```

Add:

```python
strategy = sub.add_parser("strategy", help="Inspect and run registered strategies")
strategy_sub = strategy.add_subparsers(dest="strategy_command", required=True)

strategy_catalog_cmd = strategy_sub.add_parser("catalog", help="Show Strategy Catalog")
add_common_flags(strategy_catalog_cmd)
strategy_catalog_cmd.set_defaults(handler=lambda args: strategy_catalog())

strategy_run_cmd = strategy_sub.add_parser("run", help="Run a strategy through runtime gates")
strategy_run_cmd.add_argument("name", help="Strategy name or all")
strategy_run_cmd.add_argument("--mode", choices=["production", "research"], default="production")
strategy_run_cmd.add_argument("--limit", type=int, default=0)
strategy_run_cmd.add_argument("--dry-run", action="store_true")
add_common_flags(strategy_run_cmd)
strategy_run_cmd.set_defaults(
    handler=lambda args: run_strategy(args.name, args.mode, args.limit, args.dry_run)
)

strategy_evidence_cmd = strategy_sub.add_parser("evidence", help="Show strategy evidence report path")
strategy_evidence_cmd.add_argument("name")
add_common_flags(strategy_evidence_cmd)
strategy_evidence_cmd.set_defaults(handler=lambda args: strategy_evidence(args.name))
```

- [ ] **Step 5: Run strategy tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_strategy_commands.py tests/test_strategy_runtime_gates.py tests/test_strategy_catalog.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add astrolabe_cli tests/test_cli_strategy_commands.py
git commit -m "codex: add cli strategy commands"
```

---

## Task 5: Data Status And Repair Commands

**Files:**
- Create: `astrolabe_cli/commands/data.py`
- Modify: `astrolabe_cli/main.py`
- Test: `tests/test_cli_data_commands.py`

- [ ] **Step 1: Write failing data command tests**

Create `tests/test_cli_data_commands.py`:

```python
import json


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_data_status_runs_health_check(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    monkeypatch.setattr(
        "scripts.db_health_check.run_health_check",
        lambda: [{"table": "summary", "missing_pct": 0}],
    )

    code = run_cli(["data", "status", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["rows"] == 1


def test_data_repair_dry_run_does_not_call_repair(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    calls = []
    monkeypatch.setattr("scripts.repair_table.repair", lambda *args, **kwargs: calls.append((args, kwargs)))

    code = run_cli(["data", "repair", "stock_valuation", "--dry-run", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert calls == []
    assert data["data"]["dry_run"] is True
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_data_commands.py -q
```

Expected: FAIL because `data` command is not registered.

- [ ] **Step 3: Implement data commands**

Create `astrolabe_cli/commands/data.py`:

```python
from __future__ import annotations

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def status() -> CliResult:
    from scripts.db_health_check import run_health_check

    result = run_health_check()
    rows = len(result) if hasattr(result, "__len__") else 0
    return CliResult(
        ok=True,
        command="data status",
        message=f"DB health check returned {rows} row(s)",
        data={"rows": rows},
    )


def repair(table: str, limit: int, days: int, dry_run: bool) -> CliResult:
    from scripts.repair_table import REPAIR_MAP, repair as repair_table

    if table not in REPAIR_MAP:
        return CliResult(
            ok=False,
            command="data repair",
            message=f"Unknown or non-repairable table: {table}",
            errors=["unknown_table"],
            data={"table": table},
        )
    if dry_run:
        return CliResult(
            ok=True,
            command="data repair",
            message=f"Dry run: repair {table}",
            data=dry_run_payload("data.repair", table=table, limit=limit, days=days),
        )

    repair_table(table, limit=limit, days=days)
    return CliResult(
        ok=True,
        command="data repair",
        message=f"Repair complete: {table}",
        data={"table": table, "limit": limit, "days": days},
    )
```

- [ ] **Step 4: Register data parser**

Modify `astrolabe_cli/main.py`:

```python
from astrolabe_cli.commands.data import repair as data_repair
from astrolabe_cli.commands.data import status as data_status
```

Add:

```python
data = sub.add_parser("data", help="Inspect and repair local DataHub datasets")
data_sub = data.add_subparsers(dest="data_command", required=True)

data_status_cmd = data_sub.add_parser("status", help="Run DB health check")
add_common_flags(data_status_cmd)
data_status_cmd.set_defaults(handler=lambda args: data_status())

data_repair_cmd = data_sub.add_parser("repair", help="Repair one logical table")
data_repair_cmd.add_argument("table")
data_repair_cmd.add_argument("--limit", type=int, default=0)
data_repair_cmd.add_argument("--days", type=int, default=365)
data_repair_cmd.add_argument("--dry-run", action="store_true")
add_common_flags(data_repair_cmd)
data_repair_cmd.set_defaults(
    handler=lambda args: data_repair(args.table, args.limit, args.days, args.dry_run)
)
```

- [ ] **Step 5: Run data tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_data_commands.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add astrolabe_cli tests/test_cli_data_commands.py
git commit -m "codex: add cli data commands"
```

---

## Task 6: Regime, Backtest, Docs And Web Commands

**Files:**
- Create: `astrolabe_cli/commands/regime.py`
- Create: `astrolabe_cli/commands/backtest.py`
- Create: `astrolabe_cli/commands/docs.py`
- Create: `astrolabe_cli/commands/web.py`
- Modify: `astrolabe_cli/main.py`
- Test: `tests/test_cli_ops_commands.py`

- [ ] **Step 1: Add failing command tests**

Append to `tests/test_cli_ops_commands.py`:

```python
def test_regime_status_command_uses_orchestrator(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    class FakeRegime:
        value = "sideways"

    class FakeSnapshot:
        regime = FakeRegime()
        regime_score = 51.2
        index_ma_trend = "flat"

    class FakeOrchestrator:
        def detect(self):
            return FakeSnapshot()

    monkeypatch.setattr("cybernetics.orchestrator.QuantOrchestrator", FakeOrchestrator)

    code = run_cli(["regime", "status", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["data"]["regime"] == "sideways"
    assert data["data"]["score"] == 51.2


def test_docs_check_command_runs_rg(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    class FakeCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeCompleted())

    code = run_cli(["docs", "check", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True


def test_web_build_dry_run(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    code = run_cli(["web", "build", "--dry-run", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert calls == []
    assert data["data"]["dry_run"] is True
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_ops_commands.py::test_regime_status_command_uses_orchestrator -q
```

Expected: FAIL because `regime` command is not registered.

- [ ] **Step 3: Implement regime commands**

Create `astrolabe_cli/commands/regime.py`:

```python
from __future__ import annotations

import subprocess
import sys

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def status() -> CliResult:
    from cybernetics.orchestrator import QuantOrchestrator

    snapshot = QuantOrchestrator().detect()
    regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
    return CliResult(
        ok=True,
        command="regime status",
        message=f"Regime: {regime}",
        data={
            "regime": regime,
            "score": float(getattr(snapshot, "regime_score", 0.0)),
            "trend": str(getattr(snapshot, "index_ma_trend", "")),
        },
    )


def train_profit(dry_run: bool) -> CliResult:
    cmd = [sys.executable, "scripts/train_market_regime_profit.py"]
    if dry_run:
        return CliResult(
            ok=True,
            command="regime train-profit",
            message="Dry run: train Market Regime profit policy",
            data=dry_run_payload("regime.train_profit", cmd=cmd),
        )
    completed = subprocess.run(cmd, capture_output=True, text=True)
    return CliResult(
        ok=completed.returncode == 0,
        command="regime train-profit",
        message="Regime profit training finished" if completed.returncode == 0 else "Regime profit training failed",
        data={"returncode": completed.returncode},
        errors=[completed.stderr.strip()] if completed.returncode else [],
    )
```

- [ ] **Step 4: Implement backtest/docs/web commands**

Create `astrolabe_cli/commands/backtest.py`:

```python
from __future__ import annotations

import subprocess
import sys

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def run_backtest(strategy: str, dry_run: bool) -> CliResult:
    cmd = [sys.executable, "backtest/run_all_strategies.py"]
    if strategy:
        cmd.extend(["--strategy", strategy])
    if dry_run:
        return CliResult(True, "backtest run", data=dry_run_payload("backtest.run", cmd=cmd), message="Dry run")
    completed = subprocess.run(cmd, capture_output=True, text=True)
    return CliResult(
        ok=completed.returncode == 0,
        command="backtest run",
        message="Backtest finished" if completed.returncode == 0 else "Backtest failed",
        data={"returncode": completed.returncode},
        errors=[completed.stderr.strip()] if completed.returncode else [],
    )
```

Create `astrolabe_cli/commands/docs.py`:

```python
from __future__ import annotations

import subprocess

from astrolabe_cli.results import CliResult


DRIFT_PATTERNS = "34 维度|34维度|四维加权|多因子四维|9 页|9页|FastAPI（9|3页|3 页|5517|全局 ticker|底部 ticker|点位与日涨跌|Regime Score"


def check_docs() -> CliResult:
    cmd = [
        "rg",
        "-n",
        DRIFT_PATTERNS,
        "README.md",
        "CLAUDE.md",
        "docs",
        "wiki",
        "-g",
        "!docs/DOCUMENTATION.md",
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    ok = completed.returncode in {0, 1}
    findings = [line for line in completed.stdout.splitlines() if line.strip()]
    return CliResult(
        ok=ok and not findings,
        command="docs check",
        message="No known stale phrases found" if not findings else "Known stale phrases found",
        data={"findings": findings, "returncode": completed.returncode},
        errors=[] if ok else [completed.stderr.strip()],
    )
```

Create `astrolabe_cli/commands/web.py`:

```python
from __future__ import annotations

import subprocess
import sys

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def build(dry_run: bool) -> CliResult:
    cmd = ["npm", "run", "build"]
    if dry_run:
        return CliResult(True, "web build", data=dry_run_payload("web.build", cmd=cmd, cwd="web/frontend"), message="Dry run")
    completed = subprocess.run(cmd, cwd="web/frontend", capture_output=True, text=True)
    return CliResult(completed.returncode == 0, "web build", data={"returncode": completed.returncode}, message="Web build finished")


def serve(host: str, port: int) -> CliResult:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "web.api.app:create_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
    ]
    subprocess.run(cmd)
    return CliResult(True, "web serve", data={"host": host, "port": port}, message="Web server stopped")
```

- [ ] **Step 5: Register parsers**

Modify `astrolabe_cli/main.py` by importing the new command functions and adding subparsers for `regime`, `backtest`, `docs`, and `web`. Use these exact argument sets:

```python
regime_status_cmd.add_argument("--json", action="store_true")
regime_train_cmd.add_argument("--dry-run", action="store_true")
backtest_run_cmd.add_argument("--strategy", default="")
backtest_run_cmd.add_argument("--dry-run", action="store_true")
docs_check_cmd.add_argument("--json", action="store_true")
web_build_cmd.add_argument("--dry-run", action="store_true")
web_serve_cmd.add_argument("--host", default="0.0.0.0")
web_serve_cmd.add_argument("--port", type=int, default=8501)
```

For consistency, prefer `add_common_flags()` over direct `--json` where there is no conflict.

- [ ] **Step 6: Run ops tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_ops_commands.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add astrolabe_cli tests/test_cli_ops_commands.py
git commit -m "codex: add cli ops commands"
```

---

## Task 7: Makefile And Documentation Alignment

**Files:**
- Modify: `Makefile`
- Modify: `docs/DOCUMENTATION.md`
- Modify: `docs/specs/05-web-platform.md`
- Modify: `docs/acceptance-matrix.md`
- Test: `tests/test_cli_foundation.py`

- [ ] **Step 1: Add failing documentation contract test**

Append to `tests/test_cli_foundation.py`:

```python
from pathlib import Path


def test_docs_describe_xp_as_agent_control_plane():
    docs = Path("docs/DOCUMENTATION.md").read_text(encoding="utf-8")
    web_spec = Path("docs/specs/05-web-platform.md").read_text(encoding="utf-8")
    acceptance = Path("docs/acceptance-matrix.md").read_text(encoding="utf-8")

    assert "astroq" in docs
    assert "Agent-facing Control Plane" in web_spec
    assert "CLI Control Plane" in acceptance
```

- [ ] **Step 2: Run test and confirm red**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_foundation.py::test_docs_describe_xp_as_agent_control_plane -q
```

Expected: FAIL because docs do not mention CLI control plane.

- [ ] **Step 3: Update Makefile wrappers**

Modify `Makefile` targets:

```make
scan:
	$(PYTHON) -m astrolabe_cli.main strategy run all --mode production

backtest:
	$(PYTHON) -m astrolabe_cli.main backtest run

regime:
	$(PYTHON) -m astrolabe_cli.main regime status

web: web-build
	$(PYTHON) -m astrolabe_cli.main web serve --host 0.0.0.0 --port 8501

web-build:
	$(PYTHON) -m astrolabe_cli.main web build
```

- [ ] **Step 4: Update documentation**

Add to `docs/DOCUMENTATION.md` under 权威来源:

```markdown
| Agent/cron/local 操作入口 | `astroq` CLI (`astrolabe_cli/`) | 新自动化优先调用 CLI；旧脚本作为底层实现或兼容入口。 |
```

Add to `docs/specs/05-web-platform.md`:

```markdown
### 2.4 Agent-facing Control Plane

`astroq` 是 Web/API 之外的本地控制平面，用于 agent、cron 和人工维护。CLI 只做编排：策略扫描仍走 `data.strategy_plugins`，数据修复仍走 `scripts.repair_table`，Web 服务仍走 `uvicorn web.api.app:create_app`。所有 agent 依赖命令必须支持 `--json`。
```

Add to `docs/acceptance-matrix.md` Web 平台 section:

```markdown
| 5.15 | CLI Control Plane | `astrolabe_cli/` | `test_cli_*.py` | `astroq health`, `astroq strategy catalog`, `astroq data status` | Agent 可通过 JSON 输出判断下一步动作 | OK | 继续扩大命令覆盖 |
```

- [ ] **Step 5: Run docs test**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_foundation.py::test_docs_describe_xp_as_agent_control_plane -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add Makefile docs/DOCUMENTATION.md docs/specs/05-web-platform.md docs/acceptance-matrix.md tests/test_cli_foundation.py
git commit -m "codex: document astroq cli control plane"
```

---

## Task 8: Final Verification And Migration Notes

**Files:**
- Modify: `docs/development-plan.md` only if implementation reveals a real mismatch in this plan.

- [ ] **Step 1: Run focused CLI tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_cli_foundation.py \
  tests/test_cli_strategy_commands.py \
  tests/test_cli_data_commands.py \
  tests/test_cli_ops_commands.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent regression tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_strategy_runtime_gates.py \
  tests/test_strategy_catalog.py \
  tests/test_strategy_backtest_evidence.py \
  tests/test_web_system_contracts.py::test_strategy_lab_exposes_catalog_and_candidate_language \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend build if Makefile web target changed**

Run:

```bash
cd web/frontend && npm run typecheck && npm run build
```

Expected: both commands exit 0.

- [ ] **Step 4: Run command smoke tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main health --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main config validate --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main strategy catalog --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main strategy run trend_following --mode research --limit 5 --dry-run --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main data repair stock_valuation --dry-run --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main docs check --json
```

Expected: each command prints valid JSON. `docs check` must return `ok=true` unless it reports real stale phrases, in which case fix the stale text before commit.

- [ ] **Step 5: Install editable package smoke test**

Run:

```bash
.venv/bin/python -m pip install -e .
astroq health --json
```

Expected: `astroq` resolves from the console script and prints JSON with `ok=true`.

- [ ] **Step 6: Final diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. `git status --short` should only show intended files before final commit.

- [ ] **Step 7: Final commit**

Run:

```bash
git add astrolabe_cli pyproject.toml Makefile docs tests
git commit -m "codex: add astroq cli control plane"
```

Expected: commit succeeds. Do not push unless the user asks.

---

## Acceptance Criteria

- `astroq health --json` returns stable JSON with project version and data roots.
- `astroq config validate --json` validates settings and strategy registry.
- `astroq strategy catalog --json` returns Strategy Catalog data.
- `astroq strategy run all` defaults to `mode=production`.
- `astroq strategy run trend_following --dry-run` fails unless `--mode research` is specified.
- `astroq data status --json` runs DB health check through existing code.
- `astroq data repair <table> --dry-run --json` never calls repair code.
- `astroq docs check --json` performs the documented drift scan.
- `astroq web build` delegates to the existing Vite build command.
- CLI tests and adjacent strategy/web contracts pass.

## Known Follow-Up After MVP

- Add `astroq job` commands only after the local job queue has durable storage.
- Add `astroq cron` commands only after cron definitions have one machine-readable registry.
- Add shell completion only after command names stabilize.
- Add richer evidence report rendering after `data/store/research/strategy_evidence/*.json` contains real baseline payloads.
