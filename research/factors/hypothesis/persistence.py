"""Candidate factor pool persistence and promotion helpers."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from research.factors.hypothesis.candidates import FactorCandidate, _formula_to_dsl

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE_POOL_PATH = ROOT / "config" / "candidate_factors.yaml"
EXPRESSION_PATH = ROOT / "signals" / "expression.py"
AUTO_REGISTER_START = "# ── LLM 自动注册因子 — AUTO-REGISTER START (do not edit manually) ──"
AUTO_REGISTER_END = "# ── AUTO-REGISTER END ──"

def save_to_candidate_pool(accepted: List[FactorCandidate]) -> bool:
    """
    Save LLM-discovered factors to the candidate pool (config/candidate_factors.yaml).

    Candidates must pass OOS validation before being promoted to expression.py.
    This prevents unvalidated factors from entering production strategy scans.
    """
    # Load existing pool
    existing: dict[str, dict] = {}
    if CANDIDATE_POOL_PATH.exists():
        import yaml as _yaml
        with open(CANDIDATE_POOL_PATH) as f:
            existing = _yaml.safe_load(f) or {}

    pool = existing.get("candidates", {}) if isinstance(existing, dict) else {}

    added = 0
    for c in accepted:
        if c.name in pool:
            continue
        pool[c.name] = {
            "formula": c.formula,
            "ic": c.ic,
            "icir": c.icir,
            "oos_ic": c.oos_ic,
            "passed_oos": c.passed_oos,
            "status": "candidate",
            "discovered_at": datetime.now().isoformat(),
        }
        added += 1

    if added == 0:
        print("  (all factors already in candidate pool)")
        return True

    import yaml as _yaml
    CANDIDATE_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATE_POOL_PATH, "w") as f:
        _yaml.dump({"candidates": pool}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"  ✅ Saved {added} factors to candidate pool: {CANDIDATE_POOL_PATH}")
    print(f"  📋 Run promote_candidate_factor('<name>') to promote after validation.")
    return True

def list_candidate_factors(status: str = "") -> dict[str, dict]:
    """List factors in the candidate pool, optionally filtered by status."""
    if not CANDIDATE_POOL_PATH.exists():
        return {}
    import yaml as _yaml
    with open(CANDIDATE_POOL_PATH) as f:
        data = _yaml.safe_load(f) or {}
    pool = data.get("candidates", {})
    if status:
        return {k: v for k, v in pool.items() if v.get("status") == status}
    return pool

def promote_candidate_factor(name: str) -> bool:
    """
    Promote a candidate factor from the pool into expression.py.
    After promotion, the factor status changes to 'promoted' in the pool.

    Returns True on success, False if factor not found or already promoted.
    """
    import yaml as _yaml

    pool = list_candidate_factors()
    if name not in pool:
        print(f"  ✗ Factor '{name}' not found in candidate pool.")
        return False
    if pool[name].get("status") == "promoted":
        print(f"  ✗ Factor '{name}' is already promoted.")
        return False

    factor = pool[name]
    dsl = _formula_to_dsl(factor["formula"], name)

    content = EXPRESSION_PATH.read_text()

    factor_line = f'        "{name}": {dsl},'

    if AUTO_REGISTER_START in content:
        start_idx = content.index(AUTO_REGISTER_START)
        end_idx = content.index(AUTO_REGISTER_END, start_idx)
        old_block = content[start_idx + len(AUTO_REGISTER_START):content.index(AUTO_REGISTER_END, start_idx)]

        existing_lines = [l for l in old_block.split("\n") if l.strip().startswith('"')]
        existing_lines.append(factor_line)
        new_block = AUTO_REGISTER_START + "\n" + "\n".join(existing_lines) + "\n        " + AUTO_REGISTER_END

        content = content[:start_idx] + new_block + content[end_idx:]
    else:
        block = (
            f"\n        {AUTO_REGISTER_START}\n"
            f"{factor_line}\n"
            f"        {AUTO_REGISTER_END}\n"
        )
        content = content.replace("    return factors", block + "    return factors")

    EXPRESSION_PATH.write_text(content)

    # Mark as promoted in pool
    pool[name]["status"] = "promoted"
    pool[name]["promoted_at"] = datetime.now().isoformat()
    CANDIDATE_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATE_POOL_PATH, "w") as f:
        _yaml.dump({"candidates": pool}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"  ✅ Promoted '{name}' to expression.py")
    return True
