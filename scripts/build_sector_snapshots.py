#!/usr/bin/env python3
"""Build sector snapshots — industry membership, performance, signal aggregation, exposure.

Usage:
    python scripts/build_sector_snapshots.py          # build all
    python scripts/build_sector_snapshots.py --membership  # membership only
    python scripts/build_sector_snapshots.py --dry-run     # validate without writing
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root on path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build sector snapshots")
    parser.add_argument("--membership", action="store_true", help="Build membership only")
    parser.add_argument("--performance", action="store_true", help="Build performance only")
    parser.add_argument("--signals", action="store_true", help="Build signal aggregation only")
    parser.add_argument("--exposure", action="store_true", help="Build exposure only")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = parser.parse_args()

    from data.storage.datahub import DataHub
    from data import sectors

    hub = DataHub()

    # Determine which builders to run
    all_builders = {
        "membership": sectors.build_membership,
        "performance": sectors.build_sector_performance,
        "signals": sectors.build_signal_aggregation,
        "exposure": sectors.build_exposure,
    }

    specific = [k for k in ["membership", "performance", "signals", "exposure"] if getattr(args, k)]
    builders = {k: all_builders[k] for k in specific} if specific else all_builders

    if args.dry_run:
        print("Dry run — validating only, no writes.")
        for name, builder in builders.items():
            print(f"  {name}: builder available ({builder.__name__})")
        print("OK")
        return

    results = {}
    for name, builder in builders.items():
        try:
            df = builder(hub)
            results[name] = {"status": "ok", "rows": len(df)}
            print(f"  {name}: {len(df)} rows")
        except Exception as e:
            results[name] = {"status": "error", "message": str(e)[:200]}
            print(f"  {name}: ERROR — {e}")

    errs = sum(1 for r in results.values() if r["status"] == "error")
    print(f"\nDone. {len(results)} builders, {errs} errors.")
    if errs:
        sys.exit(1)


if __name__ == "__main__":
    main()
