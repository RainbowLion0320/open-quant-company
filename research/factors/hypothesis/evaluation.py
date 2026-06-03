"""OOS evaluation and model feedback for LLM factors."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from signals.dsl_parser import compute_formula

ROOT = Path(__file__).resolve().parents[3]

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
    model_path = ROOT / "data" / "models" / "lgbm_best.pkl"
    meta_path = ROOT / "data" / "models" / "lgbm_best_meta.json"

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

CANDIDATE_POOL_PATH = ROOT / "config" / "candidate_factors.yaml"

AUTO_REGISTER_START = "# ── LLM 自动注册因子 — AUTO-REGISTER START (do not edit manually) ──"
AUTO_REGISTER_END = "# ── AUTO-REGISTER END ──"
