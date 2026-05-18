"""
repair_table.py — 单表数据修复

用法:
  python scripts/repair_table.py <table_name>

对指定的逻辑表触发数据重拉，完成后自动重跑健康检查。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.fetchers.macro import MacroFetcher


def repair_macro(name: str) -> None:
    """Re-fetch macro indicator from AKShare."""
    print(f"  Fetching macro/{name} from AKShare...")
    fetcher = MacroFetcher()
    df = fetcher.fetch_indicator(name)
    if df is not None and len(df) > 0:
        print(f"  ✓ {len(df)} rows, latest: {df.iloc[-1].get('date', 'N/A')}")
    else:
        print(f"  ⚠ No data returned")


def repair_tushare_dim(dim: str, label: str) -> None:
    """Re-fetch per-symbol data from Tushare via cron_fetch_slow.py."""
    import subprocess
    venv = str(Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3")
    cmd = [venv, "scripts/cron_fetch_slow.py", "--dim", dim, "--days", "365"]
    print(f"  → {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=600)
    for line in result.stdout.strip().split("\n")[-8:]:
        print(f"    {line}")
    if result.returncode != 0:
        print(f"  ⚠ exit {result.returncode}")
        if result.stderr:
            print(f"    {result.stderr.strip()[-200:]}")


REPAIR_MAP = {
    # Macro — direct AKShare fetch
    "macro_cpi":             lambda: repair_macro("cpi"),
    "macro_gdp":             lambda: repair_macro("gdp"),
    "macro_lpr":             lambda: repair_macro("lpr"),
    "macro_money_supply":    lambda: repair_macro("money_supply"),
    "macro_pmi":             lambda: repair_macro("pmi"),
    "macro_ppi":             lambda: repair_macro("ppi"),
    "macro_shibor":          lambda: repair_macro("shibor"),
    "bond_treasury_yields":  lambda: repair_macro("bond"),
    # Stock — Tushare re-fetch
    "stock_holders":              lambda: repair_tushare_dim("holder_number", "股东户数"),
    "stock_holdertrade":          lambda: repair_tushare_dim("holder_trade", "股东增减持"),
    "stock_moneyflow_daily":      lambda: repair_macro("moneyflow_daily"),
    "stock_moneyflow_monthly":    lambda: repair_tushare_dim("moneyflow", "资金流向月频"),
    "stock_broker_recommend":     lambda: repair_tushare_dim("broker_recommend", "券商金股"),
    "stock_limit_list":           lambda: repair_tushare_dim("limit_list", "涨跌停"),
    "stock_research_report":      lambda: repair_tushare_dim("research_report", "研报"),
    "share_float":                lambda: repair_tushare_dim("share_float", "限售解禁"),
    "repurchase":                 lambda: repair_tushare_dim("repurchase", "回购"),
}


def repair(table: str) -> None:
    if table not in REPAIR_MAP:
        print(f"Unknown or non-repairable table: {table}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"REPAIR: {table}")
    print(f"{'='*60}")

    REPAIR_MAP[table]()

    # Re-run health check
    import subprocess
    venv = str(Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3")
    print(f"\n  Re-running health check...")
    result = subprocess.run(
        [venv, "scripts/db_health_check.py"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=300,
    )
    print(f"  {result.stdout.strip()}")

    print(f"\n✅ Repair complete: {table}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/repair_table.py <table_name>")
        sys.exit(1)
    repair(sys.argv[1])
