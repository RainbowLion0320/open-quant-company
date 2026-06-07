#!/usr/bin/env python3
"""Night-run CLI for offline Market Regime champion/challenger research."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from research.regime.features import load_full_market_breadth_history
from research.regime.reports import run_and_write_report, write_regime_training_report


def _load_index_daily(symbol: str = "sh000001") -> pd.DataFrame:
    """Load benchmark index daily data, preferring local API cache."""
    try:
        from data.ingestion.fetcher import _read_cache, get_index_daily

        cached = _read_cache(f"index_daily_{symbol}_default", max_age_hours=0)
        if cached is not None and len(cached) > 0:
            return cached
        return get_index_daily(symbol, force_refresh=False)
    except Exception:
        return pd.DataFrame()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train and validate Market Regime challenger policies.")
    parser.add_argument("--start", default="2016-01-01", help="Start date, YYYY-MM-DD.")
    parser.add_argument("--end", default="auto", help="End date, YYYY-MM-DD or auto.")
    parser.add_argument("--max-candidates", type=int, default=500, help="Maximum challenger policies to evaluate.")
    parser.add_argument("--output", required=True, help="Output directory under reports/regime_training/.")
    parser.add_argument("--no-apply", action="store_true", help="Do not apply recommended config to production.")
    parser.add_argument("--symbol", default="sh000001", help="Benchmark index symbol.")
    parser.add_argument("--skip-breadth", action="store_true", help="Use index-derived breadth proxy only.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    print(f"[regime-trainer] output={output}")
    print(f"[regime-trainer] start={args.start} end={args.end} max_candidates={args.max_candidates}")
    if not args.no_apply:
        print("[regime-trainer] auto-apply is intentionally disabled in this version; writing advisory config only")

    index_df = _load_index_daily(args.symbol)
    if index_df.empty:
        summary = write_regime_training_report(
            output,
            {
                "decision": "insufficient_data",
                "champion_score": 0.0,
                "best_challenger_score": 0.0,
                "best_challenger_id": "",
                "candidate_rows": [],
                "walk_forward_rows": [],
                "strategy_rows": [],
                "stability_rows": [],
                "component_rows": [],
                "event_rows": [],
                "notes": [f"insufficient_data: benchmark index {args.symbol} not available"],
            },
        )
        print(f"[regime-trainer] decision={summary['decision']}")
        return 2

    breadth = pd.DataFrame()
    if not args.skip_breadth:
        print("[regime-trainer] loading full-market breadth history from local stock parquet")
        breadth = load_full_market_breadth_history(start=args.start, end=args.end)
        print(f"[regime-trainer] breadth_rows={len(breadth)}")
    else:
        print("[regime-trainer] skip_breadth=true; using benchmark-derived proxy")

    try:
        summary = run_and_write_report(
            index_df=index_df,
            output_dir=output,
            start=args.start,
            end=args.end,
            max_candidates=args.max_candidates,
            breadth_history=breadth,
        )
    except Exception as exc:
        summary = write_regime_training_report(
            output,
            {
                "decision": "insufficient_data",
                "champion_score": 0.0,
                "best_challenger_score": 0.0,
                "best_challenger_id": "",
                "candidate_rows": [],
                "walk_forward_rows": [],
                "strategy_rows": [],
                "stability_rows": [],
                "component_rows": [],
                "event_rows": [],
                "notes": [f"run_failed: {type(exc).__name__}: {exc}"],
            },
        )
        print(f"[regime-trainer] failed={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"[regime-trainer] decision={summary['decision']}")
    print(f"[regime-trainer] champion_score={summary['champion_score']}")
    print(f"[regime-trainer] best_challenger={summary['best_challenger_id']} score={summary['best_challenger_score']}")
    print("[regime-trainer] production_formula_applied=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
