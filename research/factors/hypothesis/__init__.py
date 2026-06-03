"""LLM factor hypothesis research package."""
from research.factors.hypothesis.candidates import FactorCandidate, _formula_to_dsl
from research.factors.hypothesis.core import run_research_loop
from research.factors.hypothesis.evaluation import evaluate_factor_oos, get_feature_importance_hints
from research.factors.hypothesis.llm import build_hypothesis_prompt, generate_via_llm, _parse_llm_candidates
from research.factors.hypothesis.persistence import list_candidate_factors, promote_candidate_factor, save_to_candidate_pool

__all__ = [
    "FactorCandidate",
    "_formula_to_dsl",
    "_parse_llm_candidates",
    "build_hypothesis_prompt",
    "evaluate_factor_oos",
    "generate_via_llm",
    "get_feature_importance_hints",
    "list_candidate_factors",
    "promote_candidate_factor",
    "run_research_loop",
    "save_to_candidate_pool",
]
