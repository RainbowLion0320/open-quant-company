from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from astrolabe_cli.commands.config import env_status
from astrolabe_cli.commands.config import validate_config
from astrolabe_cli.commands.agent import actions as agent_actions
from astrolabe_cli.commands.agent import add_message as agent_add_message
from astrolabe_cli.commands.agent import approve as agent_approve
from astrolabe_cli.commands.agent import create_session as agent_create_session
from astrolabe_cli.commands.agent import desks as agent_desks
from astrolabe_cli.commands.agent import evidence as agent_evidence
from astrolabe_cli.commands.agent import handoffs as agent_handoffs
from astrolabe_cli.commands.agent import reject as agent_reject
from astrolabe_cli.commands.agent import resolve_handoff as agent_resolve_handoff
from astrolabe_cli.commands.agent import run_action as agent_run_action
from astrolabe_cli.commands.agent import sessions as agent_sessions
from astrolabe_cli.commands.agent import show_action as agent_show_action
from astrolabe_cli.commands.agent import show_session as agent_show_session
from astrolabe_cli.commands.backtest import check as backtest_check
from astrolabe_cli.commands.backtest import run_backtest
from astrolabe_cli.commands.data import repair as data_repair
from astrolabe_cli.commands.data import sources as data_sources
from astrolabe_cli.commands.data import sources_audit as data_sources_audit
from astrolabe_cli.commands.data import sources_diff_registry as data_sources_diff_registry
from astrolabe_cli.commands.data import tushare_audit as data_tushare_audit
from astrolabe_cli.commands.data import tushare_backfill as data_tushare_backfill
from astrolabe_cli.commands.execution import dry_run as execution_dry_run
from astrolabe_cli.commands.pipeline import list_pipelines, show_pipeline
from astrolabe_cli.commands.assets import overview as assets_overview
from astrolabe_cli.commands.architecture import ast_check as architecture_ast_check
from astrolabe_cli.commands.data import status as data_status
from astrolabe_cli.commands.docs import check_docs
from astrolabe_cli.commands.health import run_health
from astrolabe_cli.commands.lifecycle import check as lifecycle_check
from astrolabe_cli.commands.regime import status as regime_status
from astrolabe_cli.commands.regime import train_profit as regime_train_profit
from astrolabe_cli.commands.strategy import catalog as strategy_catalog
from astrolabe_cli.commands.strategy import compete as strategy_compete
from astrolabe_cli.commands.strategy import evidence as strategy_evidence
from astrolabe_cli.commands.strategy import run_strategy
from astrolabe_cli.commands.test_system import check as test_check
from astrolabe_cli.commands.test_system import design as test_design
from astrolabe_cli.commands.web import build as web_build
from astrolabe_cli.commands.web import serve as web_serve
from astrolabe_cli.results import CliResult, ExitCode


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Render machine-readable JSON")


def _health_command(args: argparse.Namespace) -> CliResult:
    return run_health()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="astroq", description="Open Quant Company control plane")
    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="Check CLI and local project health")
    add_common_flags(health)
    health.set_defaults(handler=_health_command)

    agent = sub.add_parser("agent", help="Operate the local Agent Company OS runtime")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)

    agent_sessions_cmd = agent_sub.add_parser("sessions", help="List agent sessions")
    add_common_flags(agent_sessions_cmd)
    agent_sessions_cmd.set_defaults(handler=lambda args: agent_sessions())

    agent_session_cmd = agent_sub.add_parser("session", help="Create or inspect one agent session")
    agent_session_sub = agent_session_cmd.add_subparsers(dest="agent_session_command", required=True)
    agent_session_create = agent_session_sub.add_parser("create", help="Create an agent session")
    agent_session_create.add_argument("--title", required=True)
    agent_session_create.add_argument("--default-desk", default="reporting")
    add_common_flags(agent_session_create)
    agent_session_create.set_defaults(handler=lambda args: agent_create_session(args.title, args.default_desk))
    agent_session_show = agent_session_sub.add_parser("show", help="Show an agent session")
    agent_session_show.add_argument("session_id")
    add_common_flags(agent_session_show)
    agent_session_show.set_defaults(handler=lambda args: agent_show_session(args.session_id))

    agent_message_cmd = agent_sub.add_parser("message", help="Add a CEO message to a session")
    agent_message_cmd.add_argument("--session", required=True)
    agent_message_cmd.add_argument("--desk", default="reporting")
    agent_message_cmd.add_argument("--text", required=True)
    add_common_flags(agent_message_cmd)
    agent_message_cmd.set_defaults(handler=lambda args: agent_add_message(args.session, args.desk, args.text))

    agent_actions_cmd = agent_sub.add_parser("actions", help="List agent actions")
    agent_actions_cmd.add_argument("--session", default="")
    add_common_flags(agent_actions_cmd)
    agent_actions_cmd.set_defaults(handler=lambda args: agent_actions(args.session))

    agent_handoffs_cmd = agent_sub.add_parser("handoffs", help="List cross-desk handoffs")
    agent_handoffs_cmd.add_argument("--session", default="")
    add_common_flags(agent_handoffs_cmd)
    agent_handoffs_cmd.set_defaults(handler=lambda args: agent_handoffs(args.session))

    agent_handoff_cmd = agent_sub.add_parser("handoff", help="Inspect or update one cross-desk handoff")
    agent_handoff_sub = agent_handoff_cmd.add_subparsers(dest="agent_handoff_command", required=True)
    agent_handoff_resolve = agent_handoff_sub.add_parser("resolve", help="Mark one handoff as resolved")
    agent_handoff_resolve.add_argument("handoff_id")
    add_common_flags(agent_handoff_resolve)
    agent_handoff_resolve.set_defaults(handler=lambda args: agent_resolve_handoff(args.handoff_id))

    agent_action_cmd = agent_sub.add_parser("action", help="Inspect one agent action")
    agent_action_sub = agent_action_cmd.add_subparsers(dest="agent_action_command", required=True)
    agent_action_show = agent_action_sub.add_parser("show", help="Show one agent action")
    agent_action_show.add_argument("action_id")
    add_common_flags(agent_action_show)
    agent_action_show.set_defaults(handler=lambda args: agent_show_action(args.action_id))

    agent_approve_cmd = agent_sub.add_parser("approve", help="Approve an agent action")
    agent_approve_cmd.add_argument("action_id")
    add_common_flags(agent_approve_cmd)
    agent_approve_cmd.set_defaults(handler=lambda args: agent_approve(args.action_id))

    agent_reject_cmd = agent_sub.add_parser("reject", help="Reject an agent action")
    agent_reject_cmd.add_argument("action_id")
    agent_reject_cmd.add_argument("--reason", default="")
    add_common_flags(agent_reject_cmd)
    agent_reject_cmd.set_defaults(handler=lambda args: agent_reject(args.action_id, args.reason))

    agent_run_cmd = agent_sub.add_parser("run", help="Dispatch an approved or safe agent action")
    agent_run_cmd.add_argument("action_id")
    add_common_flags(agent_run_cmd)
    agent_run_cmd.set_defaults(handler=lambda args: agent_run_action(args.action_id))

    agent_evidence_cmd = agent_sub.add_parser("evidence", help="Resolve an agent evidence reference")
    agent_evidence_cmd.add_argument("evidence_id")
    add_common_flags(agent_evidence_cmd)
    agent_evidence_cmd.set_defaults(handler=lambda args: agent_evidence(args.evidence_id))

    agent_desks_cmd = agent_sub.add_parser("desks", help="List desk agents")
    add_common_flags(agent_desks_cmd)
    agent_desks_cmd.set_defaults(handler=lambda args: agent_desks())

    config = sub.add_parser("config", help="Inspect and validate project configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_validate = config_sub.add_parser("validate", help="Validate settings and strategy registry")
    add_common_flags(config_validate)
    config_validate.set_defaults(handler=lambda args: validate_config())

    config_env = config_sub.add_parser("env", help="Inspect required environment secrets")
    add_common_flags(config_env)
    config_env.set_defaults(handler=lambda args: env_status())

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

    strategy_evidence_cmd = strategy_sub.add_parser("evidence", help="Show strategy evidence artifacts")
    strategy_evidence_cmd.add_argument("name", nargs="?")
    add_common_flags(strategy_evidence_cmd)
    strategy_evidence_cmd.set_defaults(handler=lambda args: strategy_evidence(args.name))

    strategy_compete_cmd = strategy_sub.add_parser("compete", help="Generate a fair strategy competition report")
    strategy_compete_cmd.add_argument("--run-backtest", action="store_true", help="Run all strategy backtests first")
    strategy_compete_cmd.add_argument("--oos-months", type=int, default=36)
    add_common_flags(strategy_compete_cmd)
    strategy_compete_cmd.set_defaults(
        handler=lambda args: strategy_compete(args.run_backtest, args.oos_months)
    )

    data = sub.add_parser("data", help="Inspect and repair local DataHub datasets")
    data_sub = data.add_subparsers(dest="data_command", required=True)

    data_status_cmd = data_sub.add_parser("status", help="Run DB health check")
    add_common_flags(data_status_cmd)
    data_status_cmd.set_defaults(handler=lambda args: data_status())

    data_sources_cmd = data_sub.add_parser("sources", help="Inspect external data source capability registry")
    add_common_flags(data_sources_cmd)
    data_sources_cmd.set_defaults(handler=lambda args: data_sources())
    data_sources_sub = data_sources_cmd.add_subparsers(dest="sources_command")

    data_sources_audit_cmd = data_sources_sub.add_parser("audit", help="Audit external source capabilities")
    data_sources_audit_cmd.add_argument(
        "--source",
        choices=[
            "all",
            "akshare",
            "tushare",
            "tencent_finance",
            "eastmoney",
            "sina_finance",
            "tonghuashun",
            "exchange_official",
            "cninfo",
            "computed",
        ],
        default="all",
    )
    data_sources_audit_cmd.add_argument("--offline", action="store_true", help="Skip token-gated network probes")
    data_sources_audit_cmd.add_argument(
        "--discovery-depth",
        choices=["catalog", "sample", "full-sample"],
        default="catalog",
        help="catalog discovers interfaces; sample runs allowlisted tiny probes; full-sample closes every capability with probe metadata or a block reason",
    )
    data_sources_audit_cmd.add_argument("--dry-run", action="store_true", help="Plan full-sample probes without calling providers")
    data_sources_audit_cmd.add_argument("--resume", action="store_true", help="Reuse completed probe metadata from the latest artifact")
    add_common_flags(data_sources_audit_cmd)
    data_sources_audit_cmd.set_defaults(
        handler=lambda args: data_sources_audit(
            args.source,
            args.source in {"all", "tushare"} and not args.offline,
            args.discovery_depth,
            args.dry_run,
            args.resume,
        )
    )

    data_sources_diff_cmd = data_sources_sub.add_parser(
        "diff-registry",
        help="Diff external source capabilities against project data_registry",
    )
    add_common_flags(data_sources_diff_cmd)
    data_sources_diff_cmd.set_defaults(handler=lambda args: data_sources_diff_registry())

    data_repair_cmd = data_sub.add_parser("repair", help="Repair one logical table")
    data_repair_cmd.add_argument("table")
    data_repair_cmd.add_argument("--limit", type=int, default=0)
    data_repair_cmd.add_argument("--days", type=int, default=365)
    data_repair_cmd.add_argument("--dry-run", action="store_true")
    add_common_flags(data_repair_cmd)
    data_repair_cmd.set_defaults(
        handler=lambda args: data_repair(args.table, args.limit, args.days, args.dry_run)
    )

    data_tushare_audit_cmd = data_sub.add_parser("tushare-audit", help="Audit Tushare capabilities and local coverage")
    data_tushare_audit_cmd.add_argument("--offline", action="store_true", help="Skip network capability probes")
    add_common_flags(data_tushare_audit_cmd)
    data_tushare_audit_cmd.set_defaults(handler=lambda args: data_tushare_audit(not args.offline))

    data_tushare_backfill_cmd = data_sub.add_parser("tushare-backfill", help="Backfill missing Tushare dimensions")
    data_tushare_backfill_cmd.add_argument("--scope", choices=["missing", "all", "p0", "p1", "p2"], default="missing")
    data_tushare_backfill_cmd.add_argument("--resume", action="store_true", default=True)
    data_tushare_backfill_cmd.add_argument("--no-resume", dest="resume", action="store_false")
    data_tushare_backfill_cmd.add_argument("--dry-run", action="store_true")
    data_tushare_backfill_cmd.add_argument("--limit", type=int, default=0)
    data_tushare_backfill_cmd.add_argument("--days", type=int, default=365)
    add_common_flags(data_tushare_backfill_cmd)
    data_tushare_backfill_cmd.set_defaults(
        handler=lambda args: data_tushare_backfill(args.scope, args.resume, args.dry_run, args.limit, args.days)
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

    pipeline = sub.add_parser("pipeline", help="Inspect pipeline flows")
    pipeline_sub = pipeline.add_subparsers(dest="pipeline_command", required=True)
    pipeline_list_cmd = pipeline_sub.add_parser("list", help="List available pipelines")
    add_common_flags(pipeline_list_cmd)
    pipeline_list_cmd.set_defaults(handler=lambda args: list_pipelines())
    pipeline_show_cmd = pipeline_sub.add_parser("show", help="Show a specific pipeline")
    pipeline_show_cmd.add_argument("key", help="Pipeline key (e.g. market_regime)")
    add_common_flags(pipeline_show_cmd)
    pipeline_show_cmd.set_defaults(handler=lambda args: show_pipeline(args.key))

    assets = sub.add_parser("assets", help="Inspect multi-asset coverage")
    assets_sub = assets.add_subparsers(dest="assets_command", required=True)
    assets_overview_cmd = assets_sub.add_parser("overview", help="Show asset coverage and readiness")
    add_common_flags(assets_overview_cmd)
    assets_overview_cmd.set_defaults(handler=lambda args: assets_overview())

    lifecycle = sub.add_parser("lifecycle", help="Inspect end-to-end lifecycle readiness")
    lifecycle_sub = lifecycle.add_subparsers(dest="lifecycle_command", required=True)
    lifecycle_check_cmd = lifecycle_sub.add_parser("check", help="Generate lifecycle readiness artifact")
    add_common_flags(lifecycle_check_cmd)
    lifecycle_check_cmd.set_defaults(handler=lambda args: lifecycle_check())

    docs = sub.add_parser("docs", help="Check documentation hygiene")
    docs_sub = docs.add_subparsers(dest="docs_command", required=True)
    docs_check_cmd = docs_sub.add_parser("check", help="Scan docs for known stale phrases")
    add_common_flags(docs_check_cmd)
    docs_check_cmd.set_defaults(handler=lambda args: check_docs())

    architecture = sub.add_parser("architecture", help="Inspect architecture intelligence artifacts")
    architecture_sub = architecture.add_subparsers(dest="architecture_command", required=True)
    architecture_ast_cmd = architecture_sub.add_parser("ast", help="Generate deterministic AST duplicate intelligence artifact")
    add_common_flags(architecture_ast_cmd)
    architecture_ast_cmd.set_defaults(handler=lambda args: architecture_ast_check())

    test = sub.add_parser("test", help="Run and record project test gates")
    test_sub = test.add_subparsers(dest="test_command", required=True)
    test_check_cmd = test_sub.add_parser("check", help="Run a configured test suite and write System Test artifacts")
    test_check_cmd.add_argument("--suite", choices=["quick", "full"], default="quick")
    add_common_flags(test_check_cmd)
    test_check_cmd.set_defaults(handler=lambda args: test_check(args.suite))

    test_design_cmd = test_sub.add_parser("design", help="Generate deterministic test design intelligence artifact")
    add_common_flags(test_design_cmd)
    test_design_cmd.set_defaults(handler=lambda args: test_design())

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
