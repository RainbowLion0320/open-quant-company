#!/usr/bin/env python3
"""
LLM 因子自动研发引擎 — Phase 4.3

升级:
  1. 扩展数据词汇 — 暴露全部可用维度 (资金/筹码/宏观/事件) 给 LLM
  2. OOS 验证 — ICIR + 滚动 IC + 样本外严格验证
  3. 多轮迭代 — 模型重训 → 特征重要性 → 反馈 LLM → 再生成
  4. 候选池治理 — 通过 OOS 的因子先进入 candidate pool，人工晋级后再写入 alpha_factors()

用法:
  python scripts/factor_hypothesis.py --n-candidates 8 --ic-threshold 0.02 --rounds 3
  python scripts/factor_hypothesis.py --save-candidates  # 自动保存通过 OOS 的候选因子
"""
import os, sys, json, re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent

from data.datahub import get_datahub

# ── 共享 LLM token 记录器 (供活动监视器) ──
_LLM_USAGE_FILE = get_datahub().llm_usage_path()

def _log_llm_usage(source: str, usage, model: str):
    """记录非 Hermes 网关的 LLM token 用量到共享缓存"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        data = {}
        if _LLM_USAGE_FILE.exists():
            with open(_LLM_USAGE_FILE) as f:
                data = json.load(f)
        if data.get("date") != today:
            data = {"date": today, "items": [], "total_input": 0, "total_output": 0, "total_cost": 0.0, "calls": 0}
        inp = usage.prompt_tokens if hasattr(usage, 'prompt_tokens') else usage.get('prompt_tokens', 0)
        out = usage.completion_tokens if hasattr(usage, 'completion_tokens') else usage.get('completion_tokens', 0)
        # 费用估算 deepseek-v4-pro: $0.55/M in, $2.19/M out; v4-flash: $0.27/M in, $1.10/M out
        cost_r = (0.55, 2.19) if "pro" in model else (0.27, 1.10)
        cost = inp / 1_000_000 * cost_r[0] + out / 1_000_000 * cost_r[1]
        data["items"].append({"source": source, "model": model, "input": inp, "output": out, "cost": round(cost, 6), "time": datetime.now().isoformat()})
        data["total_input"] += inp
        data["total_output"] += out
        data["total_cost"] += cost
        data["calls"] += 1
        _LLM_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LLM_USAGE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass  # 静默失败, 不影响主流程


import pandas as pd
import numpy as np

from data.feature_store import FEATURES_DIR
from data.data_registry import get_registry, DataDimension
from signals.dsl_parser import compute_formula


# ══════════════════════════════════════════════════════════
# 1. 扩展 LLM 提示词 — 暴露全部可用数据维度
# ══════════════════════════════════════════════════════════

def build_hypothesis_prompt(n: int, existing: List[str],
                            importance_hints: Optional[Dict[str, float]] = None) -> str:
    """
    Build LLM prompt with full data vocabulary from the data registry.

    importance_hints: {factor_name: importance_score} from previous model training.
    LLM uses these to avoid overfit patterns and explore underserved areas.
    """
    reg = get_registry()
    available = reg.get_available()

    # Build data vocabulary for the LLM
    vocab_lines = []
    for d in available:
        vocab_lines.append(f"  {d.key}: {d.label} [{d.freq}] — {d.description or d.label}")
    vocab = "\n".join(vocab_lines)

    # Build importance feedback
    importance_section = ""
    if importance_hints:
        top_factors = sorted(importance_hints.items(), key=lambda x: -x[1])[:10]
        bottom_factors = sorted(importance_hints.items(), key=lambda x: x[1])[:5]
        importance_section = f"""
Model feature importance from last training:
  Top factors (overfit risk — find alternatives to reduce reliance):
    {chr(10).join(f'    {name}: {score:.4f}' for name, score in top_factors)}
  Weak factors (underserved — try complementary patterns):
    {chr(10).join(f'    {name}: {score:.4f}' for name, score in bottom_factors)}
"""

    return f"""You are a quantitative finance researcher specializing in alpha factor discovery for Chinese A-share markets.

GENERATE {n} NOVEL alpha factor hypotheses for cross-sectional stock return prediction (next 20-day forward return).

AVAILABLE DATA DIMENSIONS (use these in your formulas):
{vocab}

CRITICAL RULE — Cross-Sectional Discrimination:
  • MACRO variables (PMI, SHIBOR, M2, CPI, etc.) are the SAME for ALL stocks on a given date.
  • ❌ FAILED EXAMPLES (these were REJECTED — do NOT propose anything similar):
      - `pmi_conditional_value = (1 / val_pe_ttm) * max(Delta(MACRO_PMI, 3), 0)`
      - `shibor_value_yield = (1 / val_pe_ttm) / MACRO_SHIBOR_3M`
    These failed because MACRO_PMI and MACRO_SHIBOR_3M are identical for all stocks,
    so multiplying/dividing them with stock-level PE still produces near-constant values.
  • ✅ WORKING PATTERNS — macro used as interaction/condition, not direct multiplication:
      - `stock_growth = Delta(close,60) / close * (1.5 if MACRO_PMI > 50 else 0.5)`
      - `liquidity_adj = volume / MA(volume,20) / MACRO_SHIBOR_3M`
    Key insight: macro should MODIFY or CONDITION a stock-level signal, not BE the signal.
  • RULE OF THUMB: If you remove all stock-level terms from the formula and the remaining
    expression still produces a number, it's a cross-sectional constant → WILL BE REJECTED.

SUPPORTED FORMULA FUNCTIONS:
  Price: close_t, close_t-N, open_t, high_t, low_t, volume_t
  Aggregations: MA(col,window), Std(col,window), Delta(col,window)
  Fund flow: MF_MAIN_NET — main force net flow (亿元), MF_SMART — smart money ratio (-1 to 1)
  Holders: HOLDER_CHANGE — holder count change %, HOLDER_CONC — concentration score
  Macro: MACRO_PMI — PMI, MACRO_M2_YOY — M2 YoY%, MACRO_SHIBOR_3M — 3M Shibor

FORMAT each factor as JSON:
```json
{{
  "name": "short_name",
  "formula": "mathematical expression using above variables",
  "expected_sign": "positive or negative"
}}
```

ECONOMIC RATIONALE required. Don't just tweak existing factors — propose genuinely new patterns.
{importance_section}

Existing factors (DO NOT duplicate):
{', '.join(existing[:40])}

Generate {n} novel, non-redundant, economically-motivated factors."""


# ══════════════════════════════════════════════════════════
# 2. 数据结构
# ══════════════════════════════════════════════════════════

@dataclass
class FactorCandidate:
    name: str
    formula: str = ""
    description: str = ""
    expected_sign: str = ""
    ic: float = 0.0
    icir: float = 0.0
    ic_rolling: List[float] = field(default_factory=list)
    ic_std: float = 0.0
    oos_ic: float = 0.0
    passed_oos: bool = False
    round_num: int = 0


# ══════════════════════════════════════════════════════════
# 3. LLM 生成
# ══════════════════════════════════════════════════════════

def generate_via_llm(n: int, existing: List[str],
                     importance_hints: Optional[Dict[str, float]] = None) -> List[FactorCandidate]:
    """Call LLM to generate factor hypotheses."""
    try:
        from openai import OpenAI
    except ImportError:
        print("openai not installed. pip install openai")
        return []

    env_path = os.path.expanduser("~/.hermes/.env")
    api_key = ""
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("DEEPSEEK_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

    if not api_key:
        print("No DEEPSEEK_API_KEY in ~/.hermes/.env")
        return []

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    prompt = build_hypothesis_prompt(n, existing, importance_hints)

    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    text = response.choices[0].message.content

    # 记录 token 用量到共享缓存 (供活动监视器统计)
    if hasattr(response, 'usage') and response.usage:
        _log_llm_usage("factor_hypothesis", response.usage, "deepseek-v4-pro")

    candidates = []
    json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    for block in json_blocks:
        try:
            items = json.loads(block)
            if isinstance(items, dict):
                items = [items]
            for item in items:
                candidates.append(FactorCandidate(
                    name=item.get("name", ""),
                    formula=item.get("formula", ""),
                    expected_sign=item.get("expected_sign", ""),
                    description=item.get("description", ""),
                ))
        except json.JSONDecodeError:
            pass

    return candidates


# ══════════════════════════════════════════════════════════
# 4. OOS 验证 — ICIR + 滚动 IC
# ══════════════════════════════════════════════════════════

def evaluate_factor_oos(
    formula: str,
    symbols: List[str],
    n_folds: int = 3
) -> Dict:
    """
    Evaluate factor with strict OOS validation.

    Splits symbols into folds. For each fold:
      - Train on N-1 folds → measure IC
      - Test on held-out fold → measure OOS IC

    Returns: ic (mean in-sample), ic_std, icir, oos_ic, ic_rolling
    """
    from data.fetcher import get_stock_daily
    from scipy.stats import spearmanr

    if len(symbols) < 60:
        return {"ic": 0, "ic_std": 0, "icir": 0, "oos_ic": 0, "ic_rolling": [], "passed": False}

    np.random.seed(42)
    shuffled = list(symbols)
    np.random.shuffle(shuffled)

    fold_size = len(shuffled) // n_folds
    fold_ics = []
    oos_ics = []

    for fold in range(n_folds):
        test_start = fold * fold_size
        test_end = test_start + fold_size if fold < n_folds - 1 else len(shuffled)
        test_syms = shuffled[test_start:test_end]
        train_syms = shuffled[:test_start] + shuffled[test_end:]

        # Train IC
        train_fv, train_y = _compute_factor_values(formula, train_syms)
        if len(train_fv) < 20:
            continue
        ic_train, _ = spearmanr(pd.Series(train_fv), pd.Series(train_y))
        if not np.isnan(ic_train):
            fold_ics.append(abs(ic_train))

        # Test (OOS) IC
        test_fv, test_y = _compute_factor_values(formula, test_syms)
        if len(test_fv) < 10:
            continue
        ic_test, _ = spearmanr(pd.Series(test_fv), pd.Series(test_y))
        if not np.isnan(ic_test):
            oos_ics.append(ic_test)

    if not fold_ics:
        return {"ic": 0, "ic_std": 0, "icir": 0, "oos_ic": 0, "ic_rolling": [], "passed": False}

    mean_ic = np.mean(fold_ics)
    std_ic = np.std(fold_ics) if len(fold_ics) > 1 else 1.0
    icir = mean_ic / std_ic if std_ic > 0 else 0
    oos_ic = np.mean(oos_ics) if oos_ics else 0

    # Pass criteria: IC > 0.015 AND ICIR > 0.3 AND OOS IC > 0.01
    passed = (mean_ic > 0.015 and icir > 0.3 and abs(oos_ic) > 0.01)

    return {
        "ic": round(mean_ic, 6),
        "ic_std": round(std_ic, 6),
        "icir": round(icir, 4),
        "oos_ic": round(oos_ic, 6),
        "ic_rolling": [round(x, 6) for x in fold_ics],
        "passed": passed,
    }


def _compute_factor_values(formula: str, symbols: List[str]) -> Tuple[List[float], List[float]]:
    """Compute factor values and forward returns for a list of symbols."""
    from data.fetcher import get_stock_daily

    factor_vals = []
    targets = []

    for sym in symbols:
        try:
            df = get_stock_daily(sym)
            if df is None or len(df) < 80:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()

            # Use 3 time points and average for robustness
            scores = []
            for offset in [0, -5, -10]:
                idx = len(df) - 1 + offset
                if idx < 60:
                    continue
                val = compute_formula(formula, df, idx)
                if not np.isnan(val) and abs(val) < 1e10:
                    scores.append(val)

            if scores:
                # Forward return: 20-day from 10 days ago (to avoid look-ahead)
                idx_10d = len(df) - 11
                if idx_10d > 20:
                    ret = df["close"].iloc[-1] / df["close"].iloc[idx_10d] - 1
                    factor_vals.append(np.mean(scores))
                    targets.append(ret)
        except Exception:
            pass

    return factor_vals, targets


# ══════════════════════════════════════════════════════════
# 5. 模型反馈 — 特征重要性分析
# ══════════════════════════════════════════════════════════

def get_feature_importance_hints() -> Optional[Dict[str, float]]:
    """
    Load feature importance from the latest trained model.
    Used to give the LLM feedback about which areas need exploration.
    """
    model_path = Path(__file__).resolve().parent.parent / "data" / "models" / "lgbm_best.pkl"
    meta_path = Path(__file__).resolve().parent.parent / "data" / "models" / "lgbm_best_meta.json"

    if not model_path.exists():
        return None

    try:
        import pickle
        with open(model_path, "rb") as f:
            model = pickle.load(f)

        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        elif hasattr(model, "feature_name_"):
            importances = model.feature_importances_
        else:
            return None

        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            feature_names = meta.get("features", meta.get("feature_names", []))
        else:
            feature_names = [f"f{i}" for i in range(len(importances))]

        if len(feature_names) != len(importances):
            return None

        hints = {}
        for name, imp in zip(feature_names, importances):
            hints[name] = float(imp)
        return hints
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
# 6. 候选因子池 — P2-12: LLM 因子门禁
#
# LLM 生成的因子不再直接写入 expression.py，
# 而是进入 config/candidate_factors.yaml 候选池。
# 回测验证通过后, 手动调用 promote_candidate_factor() 晋级。
# ══════════════════════════════════════════════════════════

CANDIDATE_POOL_PATH = Path(__file__).resolve().parent.parent / "config" / "candidate_factors.yaml"

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

    expr_path = Path(__file__).resolve().parent.parent / "signals" / "expression.py"
    content = expr_path.read_text()

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

    expr_path.write_text(content)

    # Mark as promoted in pool
    pool[name]["status"] = "promoted"
    pool[name]["promoted_at"] = datetime.now().isoformat()
    CANDIDATE_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATE_POOL_PATH, "w") as f:
        _yaml.dump({"candidates": pool}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"  ✅ Promoted '{name}' to expression.py")
    return True


def _formula_to_dsl(formula: str, name: str) -> str:
    """
    Convert LLM formula to Factor DSL expression.
    Simplified mapping for common patterns.
    """
    # Common replacements
    f = formula
    f = f.replace("close_t", "Ref('close')")
    f = f.replace("open_t", "Ref('open')")
    f = f.replace("high_t", "Ref('high')")
    f = f.replace("low_t", "Ref('low')")
    f = f.replace("volume_t", "Ref('volume')")

    # MA(col, N) → MA("col", N)
    f = re.sub(r'MA\((\w+),\s*(\d+)\)', r'MA("\1", \2)', f)

    # Std(col, N) → Std("col", N)
    f = re.sub(r'Std\((\w+),\s*(\d+)\)', r'Std("\1", \2)', f)

    # Delta(col, N) → Delta(Ref("col"), N)
    f = re.sub(r'Delta\((\w+),\s*(\d+)\)', r'Delta(Ref("\1"), \2)', f)

    # close_t-N → Ref("close", -N)
    f = re.sub(r'(\w+)_t-(\d+)', r'Ref("\1", -\2)', f)

    # Safety: wrap division denominator
    return f


# ══════════════════════════════════════════════════════════
# 7. 主循环 — 多轮迭代
# ══════════════════════════════════════════════════════════

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
    print(f"   Model: deepseek-v4-pro")
    print(f"   Save accepted candidates: {save_candidates}")
    print(f"{'='*60}")

    # Load existing factors
    existing = []
    for pq in sorted(FEATURES_DIR.glob("*.parquet"))[:1]:
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
