#!/usr/bin/env python3
"""Compatibility CLI for the LLM factor research engine."""
from __future__ import annotations

from research.factors.hypothesis.candidates import FactorCandidate, _formula_to_dsl
from research.factors.hypothesis.core import run_research_loop
from research.factors.hypothesis.evaluation import evaluate_factor_oos, get_feature_importance_hints
from research.factors.hypothesis.llm import build_hypothesis_prompt, generate_via_llm, _parse_llm_candidates
from research.factors.hypothesis import persistence as _persistence

CANDIDATE_POOL_PATH = _persistence.CANDIDATE_POOL_PATH
EXPRESSION_PATH = _persistence.EXPRESSION_PATH
AUTO_REGISTER_START = _persistence.AUTO_REGISTER_START
AUTO_REGISTER_END = _persistence.AUTO_REGISTER_END


def _sync_persistence_paths() -> None:
    _persistence.CANDIDATE_POOL_PATH = CANDIDATE_POOL_PATH
    _persistence.EXPRESSION_PATH = EXPRESSION_PATH


def save_to_candidate_pool(accepted: list[FactorCandidate]) -> bool:
    _sync_persistence_paths()
    return _persistence.save_to_candidate_pool(accepted)


def list_candidate_factors(status: str = "") -> dict[str, dict]:
    _sync_persistence_paths()
    return _persistence.list_candidate_factors(status)


def promote_candidate_factor(name: str) -> bool:
    _sync_persistence_paths()
    return _persistence.promote_candidate_factor(name)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="LLM Factor Research Engine v4.3")
    ap.add_argument("--n-candidates", type=int, default=8)
    ap.add_argument("--ic-threshold", type=float, default=0.015)
    ap.add_argument("--rounds", type=int, default=3, help="Max rounds of iteration")
    ap.add_argument("--save-candidates", action="store_true", help="Save accepted factors to the candidate pool")
    args = ap.parse_args()

    run_research_loop(
        n_candidates=args.n_candidates,
        ic_threshold=args.ic_threshold,
        max_rounds=args.rounds,
        save_candidates=args.save_candidates,
    )
