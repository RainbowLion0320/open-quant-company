"""Command line entrypoint for LLM factor hypothesis research."""
from __future__ import annotations

import argparse
from typing import Sequence

from research.factors.hypothesis.core import run_research_loop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM Factor Research Engine")
    parser.add_argument("--n-candidates", type=int, default=8)
    parser.add_argument("--ic-threshold", type=float, default=0.015)
    parser.add_argument("--rounds", type=int, default=3, help="Max rounds of iteration")
    parser.add_argument("--save-candidates", action="store_true", help="Save accepted factors to the candidate pool")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_research_loop(
        n_candidates=args.n_candidates,
        ic_threshold=args.ic_threshold,
        max_rounds=args.rounds,
        save_candidates=args.save_candidates,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
