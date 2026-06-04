"""Multi-round factor discovery orchestration."""
from __future__ import annotations

from typing import List

from data.datahub import get_datahub
from data.feature_store import iter_feature_files
from data.llm_usage import resolve_llm_use_case
from research.factors.hypothesis.candidates import FactorCandidate
from research.factors.hypothesis.evaluation import evaluate_factor_oos, get_feature_importance_hints
from research.factors.hypothesis.llm import generate_via_llm
from research.factors.hypothesis.persistence import save_to_candidate_pool

def run_research_loop(
    n_candidates: int = 8,
    ic_threshold: float = 0.015,
    max_rounds: int = 3,
    save_candidates: bool = False,
):
    """
    Full multi-round factor discovery pipeline.

    Round 1: Generate → OOS evaluate → select
    Round 2-N: Load model importance → feedback to LLM → generate → evaluate
    """
    print(f"🧪 LLM Factor Research Engine v4.3 (P2-12: candidate pool gate)")
    print(f"   Candidates/round: {n_candidates}")
    print(f"   IC threshold: {ic_threshold}")
    print(f"   Max rounds: {max_rounds}")
    llm_runtime = resolve_llm_use_case("factor_hypothesis")
    print(f"   Model: {llm_runtime['provider']}:{llm_runtime['model']}")
    print(f"   Save accepted candidates: {save_candidates}")
    print(f"{'='*60}")

    # Load existing factors
    existing = []
    for pq in iter_feature_files()[:1]:
        df = get_datahub().read_parquet(pq)
        existing = [c for c in df.columns if c not in ("symbol", "month", "ret_fwd_20d", "name")]
        break

    # Load data symbols
    from data.symbols import CIRCLE_STOCKS
    symbols = list(CIRCLE_STOCKS)[:500]  # 500 for stable OOS IC estimates

    all_accepted: List[FactorCandidate] = []

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'─'*60}")
        print(f"  ROUND {round_num}/{max_rounds}")
        print(f"{'─'*60}")

        # Get importance hints after round 1
        hints = None
        if round_num > 1:
            hints = get_feature_importance_hints()
            if hints:
                print(f"  📊 Model feedback: {len(hints)} feature importances loaded")

        # Generate candidates
        candidates = generate_via_llm(n_candidates, existing, hints)
        if not candidates:
            print("  ⚠️ LLM returned no candidates")
            break

        print(f"  Generated {len(candidates)} candidates:")

        # Evaluate each with OOS
        round_accepted = []
        for c in candidates:
            result = evaluate_factor_oos(c.formula, symbols)
            c.ic = result["ic"]
            c.ic_std = result["ic_std"]
            c.icir = result["icir"]
            c.oos_ic = result["oos_ic"]
            c.ic_rolling = result["ic_rolling"]
            c.passed_oos = result["passed"]
            c.round_num = round_num

            status = "✅" if c.passed_oos else "❌"
            print(f"  {status} {c.name:25s} IC={c.ic:.4f} ICIR={c.icir:.2f} OOS_IC={c.oos_ic:.4f} | {c.formula[:50]}")

            if c.passed_oos:
                round_accepted.append(c)

        print(f"\n  Round {round_num}: {len(round_accepted)}/{len(candidates)} passed OOS validation")

        all_accepted.extend(round_accepted)

        # Update existing list for next round
        existing.extend([c.name for c in round_accepted])

        # Save to candidate pool after each round if requested
        if save_candidates and round_accepted:
            save_to_candidate_pool(round_accepted)

        # Early stop: no new factors
        if not round_accepted:
            print("  ⏹ No factors passed in this round — stopping")
            break

    # Save to scoreboard
    from data.factor_scoreboard import record as scoreboard_record
    all_candidates_dicts = []
    for c in all_accepted:
        all_candidates_dicts.append({
            "name": c.name, "formula": c.formula, "ic": c.ic,
            "ic_std": c.ic_std, "icir": c.icir, "oos_ic": c.oos_ic,
            "round_num": c.round_num, "passed_oos": True,
        })
    if all_candidates_dicts:
        scoreboard_record(all_candidates_dicts)

    # Summary
    print(f"\n{'='*60}")
    print(f"RESEARCH COMPLETE")
    print(f"{'='*60}")
    print(f"  Total rounds: {round_num}")
    print(f"  Total accepted: {len(all_accepted)} factors")

    for c in sorted(all_accepted, key=lambda x: -x.icir):
        print(f"  ✅ {c.name:25s} IC={c.ic:.4f} ICIR={c.icir:.2f} OOS_IC={c.oos_ic:.4f} (round {c.round_num})")

    if save_candidates and all_accepted:
        print(f"\n  📝 Accepted factors saved to candidate pool")
        print(f"     Promote selected candidates, then rebuild features and retrain the model.")

    return all_accepted
