#!/usr/bin/env python3
"""Profit-oriented night-run CLI for Market Regime training."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from research.regime_training import (
    PromotionGateResult,
    load_full_market_breadth_history,
    load_local_equity_ohlcv,
    load_tradable_asset_panel,
    run_and_write_profit_report,
    write_regime_profit_report,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Market Regime as a profit-oriented risk-on/risk-off signal.")
    parser.add_argument("--start", default="2016-01-01", help="Start date, YYYY-MM-DD.")
    parser.add_argument("--end", default="auto", help="End date, YYYY-MM-DD or auto.")
    parser.add_argument("--max-candidates", type=int, default=1000, help="Maximum challenger policies to evaluate.")
    parser.add_argument("--output", required=True, help="Output directory under reports/regime_profit_training/.")
    parser.add_argument("--no-apply", action="store_true", help="Keep production formula unchanged; always true for v2.")
    parser.add_argument("--symbol", default="sh000001", help="Broad equity proxy symbol.")
    parser.add_argument("--skip-breadth", action="store_true", help="Use index-derived breadth proxy only.")
    return parser.parse_args()


def _empty_result(reason: str) -> dict:
    return {
        "decision": PromotionGateResult.INSUFFICIENT_DATA.value,
        "best_challenger_id": "",
        "champion_metrics": {},
        "best_challenger_metrics": {},
        "candidate_rows": [],
        "walk_forward_rows": [],
        "baseline_rows": [],
        "regime_exposure_rows": [],
        "regime_distribution_rows": [],
        "event_rows": [],
        "features": pd.DataFrame(),
        "labels": pd.DataFrame(),
        "asset_panel": pd.DataFrame(),
        "asset_sources": {},
        "notes": [reason, "production_formula_not_applied"],
    }


def main() -> int:
    args = _parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    print(f"[regime-profit-trainer] output={output}")
    print(f"[regime-profit-trainer] start={args.start} end={args.end} max_candidates={args.max_candidates}")
    print("[regime-profit-trainer] production_formula_applied=false")

    equity_df, equity_source, _equity_notes = load_local_equity_ohlcv(args.symbol)
    asset_panel = load_tradable_asset_panel(start=args.start, end=args.end, symbol=args.symbol)
    if equity_df.empty or asset_panel.empty:
        reason = f"insufficient_data: equity proxy {args.symbol} not available from local cache/parquet"
        summary = write_regime_profit_report(output, _empty_result(reason))
        print(f"[regime-profit-trainer] decision={summary['decision']}")
        return 2

    breadth = pd.DataFrame()
    if not args.skip_breadth:
        print("[regime-profit-trainer] loading full-market breadth history from local stock parquet")
        breadth = load_full_market_breadth_history(start=args.start, end=args.end)
        print(f"[regime-profit-trainer] breadth_rows={len(breadth)}")
    else:
        print("[regime-profit-trainer] skip_breadth=true; using benchmark-derived proxy")

    try:
        summary = run_and_write_profit_report(
            index_df=equity_df,
            asset_panel=asset_panel,
            output_dir=output,
            start=args.start,
            end=args.end,
            max_candidates=args.max_candidates,
            breadth_history=breadth,
        )
    except Exception as exc:
        summary = write_regime_profit_report(output, _empty_result(f"run_failed: {type(exc).__name__}: {exc}"))
        print(f"[regime-profit-trainer] failed={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"[regime-profit-trainer] equity_source={equity_source}")
    print(f"[regime-profit-trainer] asset_sources={summary.get('asset_sources', {})}")
    print(f"[regime-profit-trainer] decision={summary['decision']}")
    print(f"[regime-profit-trainer] best_challenger={summary['best_challenger_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
