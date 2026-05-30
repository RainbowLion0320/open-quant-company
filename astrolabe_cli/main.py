from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from astrolabe_cli.commands.config import validate_config
from astrolabe_cli.commands.backtest import check as backtest_check
from astrolabe_cli.commands.backtest import run_backtest
from astrolabe_cli.commands.data import repair as data_repair
from astrolabe_cli.commands.execution import dry_run as execution_dry_run
from astrolabe_cli.commands.data import status as data_status
from astrolabe_cli.commands.docs import check_docs
from astrolabe_cli.commands.health import run_health
from astrolabe_cli.commands.regime import status as regime_status
from astrolabe_cli.commands.regime import train_profit as regime_train_profit
from astrolabe_cli.commands.strategy import catalog as strategy_catalog
from astrolabe_cli.commands.strategy import evidence as strategy_evidence
from astrolabe_cli.commands.strategy import run_strategy
from astrolabe_cli.commands.web import build as web_build
from astrolabe_cli.commands.web import serve as web_serve
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

    regime = sub.add_parser("regime", help="Inspect and train Market Regime policy")
    regime_sub = regime.add_subparsers(dest="regime_command", required=True)

    regime_status_cmd = regime_sub.add_parser("status", help="Detect current Market Regime")
    add_common_flags(regime_status_cmd)
    regime_status_cmd.set_defaults(handler=lambda args: regime_status())

    regime_train_cmd = regime_sub.add_parser("train-profit", help="Run Market Regime profit trainer")
    regime_train_cmd.add_argument("--dry-run", action="store_true")
    add_common_flags(regime_train_cmd)
    regime_train_cmd.set_defaults(handler=lambda args: regime_train_profit(args.dry_run))

    backtest = sub.add_parser("backtest", help="Run strategy backtests")
    backtest_sub = backtest.add_subparsers(dest="backtest_command", required=True)
    backtest_run_cmd = backtest_sub.add_parser("run", help="Run all or one strategy backtest")
    backtest_run_cmd.add_argument("--strategy", default="")
    backtest_run_cmd.add_argument("--dry-run", action="store_true")
    add_common_flags(backtest_run_cmd)
    backtest_run_cmd.set_defaults(handler=lambda args: run_backtest(args.strategy, args.dry_run))

    backtest_check_cmd = backtest_sub.add_parser("check", help="Run backtest quality checks")
    add_common_flags(backtest_check_cmd)
    backtest_check_cmd.set_defaults(handler=lambda args: backtest_check())

    execution = sub.add_parser("execution", help="Paper execution operations")
    execution_sub = execution.add_subparsers(dest="execution_command", required=True)
    execution_dry_run_cmd = execution_sub.add_parser("dry-run", help="Dry-run paper execution")
    add_common_flags(execution_dry_run_cmd)
    execution_dry_run_cmd.set_defaults(handler=lambda args: execution_dry_run())

    docs = sub.add_parser("docs", help="Check documentation hygiene")
    docs_sub = docs.add_subparsers(dest="docs_command", required=True)
    docs_check_cmd = docs_sub.add_parser("check", help="Scan docs for known stale phrases")
    add_common_flags(docs_check_cmd)
    docs_check_cmd.set_defaults(handler=lambda args: check_docs())

    web = sub.add_parser("web", help="Build or serve the Web UI")
    web_sub = web.add_subparsers(dest="web_command", required=True)
    web_build_cmd = web_sub.add_parser("build", help="Build Vite frontend assets")
    web_build_cmd.add_argument("--dry-run", action="store_true")
    add_common_flags(web_build_cmd)
    web_build_cmd.set_defaults(handler=lambda args: web_build(args.dry_run))

    web_serve_cmd = web_sub.add_parser("serve", help="Serve the Web API")
    web_serve_cmd.add_argument("--host", default="0.0.0.0")
    web_serve_cmd.add_argument("--port", type=int, default=8501)
    web_serve_cmd.set_defaults(handler=lambda args: web_serve(args.host, args.port))

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


if __name__ == "__main__":
    main()
