#!/usr/bin/env python3
"""
Regime-Aware ML — 按市场状态训练三模型 (bull/bear/sideways)

预测时: 检测当前 regime → 选择对应模型 → 生成信号
"""
import os, sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np

from data.feature_store import FEATURES_DIR
from models import LightGBMRegressor, prepare_xy, MODEL_DIR
from cybernetics.orchestrator import MarketRegime, detect_market_regime


def train_regime_models():
    """Train separate LightGBM models per market regime."""
    print("Regime-Aware ML Training\n" + "=" * 50)

    # 1. Load all features with regime labels
    from data.fetcher import get_index_daily
    df_idx = get_index_daily("sh000001")
    if df_idx is None:
        print("ERROR: cannot load index data")
        return
    df_idx["date"] = pd.to_datetime(df_idx["date"])
    df_idx = df_idx.set_index("date").sort_index()
    regime_map = {}  # month → regime
    for idx_date in pd.date_range("2018-01-01", "2026-06-01", freq="MS"):
        month = idx_date.strftime("%Y-%m")
        hist = df_idx[df_idx.index <= idx_date]
        if len(hist) < 60:
            regime_map[month] = "unknown"
            continue
        close = hist["close"].values[-60:]
        ma5 = close[-5:].mean()
        ma20 = close[-20:].mean()
        ma60 = close[-60:].mean()
        current = close[-1]
        if current > ma5 > ma20 > ma60:
            regime_map[month] = "bull"
        elif current < ma5 < ma20 < ma60:
            regime_map[month] = "bear"
        else:
            regime_map[month] = "sideways"

    # 2. Load all feature data and assign regime
    dfs = []
    for pq in sorted(FEATURES_DIR.glob("*.parquet")):
        if pq.stem in ("scan_meta", "buffett_scan"):
            continue
        df = pd.read_parquet(pq)
        df["month"] = pq.stem
        dfs.append(df)
    all_features = pd.concat(dfs, ignore_index=True)
    all_features["regime"] = all_features["month"].map(regime_map).fillna("unknown")

    # 3. Train per regime
    results = {}
    for regime in ["bull", "bear", "sideways"]:
        subset = all_features[all_features["regime"] == regime].dropna(subset=["ret_fwd_20d"])
        if len(subset) < 500:
            print(f"  {regime}: {len(subset)} samples — skipping (need 500+)")
            continue

        X, y = prepare_xy(subset, "ret_fwd_20d")
        feature_names = list(X.columns)
        print(f"  {regime}: {len(subset)} samples, {len(feature_names)} features")

        model = LightGBMRegressor()
        model.fit(X, y)
        path = MODEL_DIR / f"lgbm_{regime}.pkl"
        model.save(str(path.stem))

        # Predict on training set for IC
        pred = model.predict(X)
        from scipy.stats import spearmanr
        ic, _ = spearmanr(pred, y.values)
        results[regime] = {"samples": len(subset), "features": len(feature_names), "ic": round(ic, 4)}

        # Save meta
        meta = {"regime": regime, "samples": len(subset), "features": feature_names,
                "ic": round(ic, 4), "feature_importances": {}}
        if hasattr(model._model, "feature_importances_"):
            for n, imp in zip(feature_names, model._model.feature_importances_):
                meta["feature_importances"][n] = round(float(imp), 4)
        with open(MODEL_DIR / f"lgbm_{regime}_meta.json", "w") as f:
            json.dump(meta, f, indent=2)

    # 4. Summary
    print(f"\nRegime models trained:")
    for r, res in sorted(results.items(), key=lambda x: -x[1]["ic"]):
        print(f"  {r}: {res['samples']} samples, IC={res['ic']:.4f}")

    # Save registry
    with open(MODEL_DIR / "regime_registry.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    train_regime_models()
