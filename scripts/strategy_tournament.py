#!/usr/bin/env python3
"""Generate the canonical fair strategy competition report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.run_all_strategies import run_strategy_comparison
from research.strategy_competition import write_strategy_competition_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate fair strategy competition report")
    parser.add_argument("--run-backtest", action="store_true", help="Run the canonical 12-strategy backtest first")
    parser.add_argument("--oos-months", type=int, default=36)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.run_backtest:
        run_strategy_comparison()
    report, path = write_strategy_competition_report(oos_months=args.oos_months)
    if args.json:
        print(json.dumps({"path": str(path), "report": report}, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Strategy competition report written: {path}")
        for row in report.get("rankings", [])[:5]:
            oos = row.get("metrics", {}).get("oos", {})
            print(
                f"  #{row['rank']} {row['strategy']}: {row['recommended_status']} "
                f"Sharpe={float(oos.get('sharpe', 0)):.2f} "
                f"OOS={float(oos.get('total_return', 0)):.2%}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
