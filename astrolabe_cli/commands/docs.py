from __future__ import annotations

import re
import subprocess

from astrolabe_cli.results import CliResult


DRIFT_TOKENS = (
    "34 维度",
    "34维度",
    "四维加权",
    "多因子四维",
    "9 页",
    "9页",
    "FastAPI（9",
    "3页",
    "3 页",
    "5517",
    "全局 ticker",
    "底部 ticker",
    "点位与日涨跌",
    "Regime Score",
    "7 节点",
    "七个固定节点",
    "v1 展示 Market Regime",
    "CSS grid + inline SVG",
    "GET /signals/buffett",
    "POST /backtest/run",
    "GET /system/health",
    "GET /stocks/{code}/kline",
    "POST /signals/scan",
    "GET /system/cron-log",
    "Canvas力导向图",
    "Canvas 力导向图",
    "11个业务路由模块",
    "routes/ (11 domain modules)",
    "from signals.buffett import BuffettFilter",
    "generate_ml_signals",
    "def generate_signals(",
    "compute_all()",
    'DataStep("load_prices")',
    'StrategyStep("compute_signals")',
    'SelectionStep("top_n"',
    'RiskStep("max_position_20pct")',
    'ExecutionStep("equal_weight")',
    "update_positions(prices)",
    "broker.get_nav_history()",
    "is_circuit_breaker_triggered",
    "rm.reset_circuit_breaker",
    "broadcast_progress",
    "`/ws/{job_id}`",
    "JobQueue.add",
    "def universe(self)",
    "def metadata(self",
    "allocator.detect_regime",
    "detect_regime(index_data)",
    "detect_regime(close)",
    "backtest/multi_asset_tournament.py",
    "GET /backtest",
    "`GET /portfolio`",
    "buy/sell/hold 信号",
    "from data.quality.cleaner import clean_ohlcv",
    "Data/Strategy/Selection/Risk/Execution",
    "回测: Backtrader",
    "横截面排名→交易信号",
    "四策略对比",
    "from backtest.pipeline import",
    "`backtest/pipeline.py`",
    "test_backtest_pipeline_contracts.py",
    "TUSHARE_PRO_TOKEN",
    "HINDSIGHT_API_LLM_API_KEY",
    "ASTROLABE_STORE",
    "ASTROLABE_CACHE",
    "ASTROLABE_ARTIFACTS",
    "ASTROLABE_DB",
    "migrate_data_layout",
    "data-layout-migration",
    "backtest_monthly_result",
    "/api/portfolio/sector-exposure",
    "Compatibility alias",
    "legacy static tests",
)
DRIFT_PATTERNS = "|".join(re.escape(token) for token in DRIFT_TOKENS)


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
        "-g",
        "!docs/development-plan.md",
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return CliResult(
            ok=False,
            command="docs check",
            message="ripgrep is required for docs drift check",
            data={"findings": [], "returncode": 127},
            errors=[str(exc)],
        )

    ok = completed.returncode in {0, 1}
    findings = [line for line in completed.stdout.splitlines() if line.strip()]
    return CliResult(
        ok=ok and not findings,
        command="docs check",
        message="No known stale phrases found" if not findings else "Known stale phrases found",
        data={"findings": findings, "returncode": completed.returncode},
        errors=[] if ok else [completed.stderr.strip()],
    )
