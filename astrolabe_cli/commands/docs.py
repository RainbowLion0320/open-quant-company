from __future__ import annotations

import re
import subprocess

from astrolabe_cli.results import CliResult


def _drift_token(*parts: str) -> str:
    return "".join(parts)


REMOVED_COMPATIBILITY_TOKENS = (
    _drift_token("from backtest", ".pipeline import"),
    _drift_token("`backtest/", "pipeline.py`"),
    _drift_token("test_backtest", "_pipeline_contracts.py"),
    _drift_token("TUSHARE", "_PRO_TOKEN"),
    _drift_token("ASTROLABE", "_STORE"),
    _drift_token("ASTROLABE", "_CACHE"),
    _drift_token("ASTROLABE", "_ARTIFACTS"),
    _drift_token("ASTROLABE", "_DB"),
    _drift_token("migrate", "_data_layout"),
    _drift_token("data-layout", "-migration"),
    _drift_token("backtest", "_monthly_result"),
    _drift_token("/api/portfolio", "/sector-exposure"),
    _drift_token("Compatibility", " alias"),
    _drift_token("legacy", " static tests"),
    _drift_token("Compatibility", " facade"),
    _drift_token("Compatibility", " CLI"),
    _drift_token("legacy", " import"),
    _drift_token("旧", "入口"),
    _drift_token("迁移期", "兼容"),
    _drift_token("web.api", ".settings_schema"),
    _drift_token("data.llm", ".deepseek_usage"),
    _drift_token("cybernetics", ".hmm_engine"),
    _drift_token("cybernetics", ".market_observations"),
    _drift_token("research", ".regime_training"),
    _drift_token("research.regime", ".core"),
    _drift_token("data.market", ".sectors"),
    _drift_token("scripts/factor", "_hypothesis.py"),
    _drift_token("monthly point", "-in-time feature store"),
    _drift_token("月末", "兼容"),
    _drift_token("/api/system/tests/", "summary"),
    _drift_token("/api/system/tests/", "domains"),
    _drift_token("/api/system/tests/", "runs"),
    _drift_token("Test", "System.vue"),
    _drift_token("test", "System"),
)


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
    *REMOVED_COMPATIBILITY_TOKENS,
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
        "!docs/project/documentation.md",
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
