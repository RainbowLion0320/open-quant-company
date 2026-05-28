from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from astrolabe_cli.commands.config import validate_config
from astrolabe_cli.commands.health import run_health
from astrolabe_cli.results import CliResult, ExitCode


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Render machine-readable JSON")


def _health_command(args: argparse.Namespace) -> CliResult:
    return run_health()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="astroq", description="Astrolabe Quant OS control plane")
    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="Check CLI and local project health")
    add_common_flags(health)
    health.set_defaults(handler=_health_command)

    config = sub.add_parser("config", help="Inspect and validate project configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_validate = config_sub.add_parser("validate", help="Validate settings and strategy registry")
    add_common_flags(config_validate)
    config_validate.set_defaults(handler=lambda args: validate_config())

    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        if exc.code == 0:
            return int(ExitCode.OK)
        raise
    result: CliResult = args.handler(args)
    output = result.render_json() if getattr(args, "json", False) else result.render_text()
    print(output)
    return int(ExitCode.OK if result.ok else ExitCode.FAILED)


def main() -> None:
    raise SystemExit(run_cli(sys.argv[1:]))
