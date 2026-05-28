#!/usr/bin/env python3
"""
Regime-Aware ML — 按市场状态训练三模型 (bull/bear/sideways)

预测时: 检测当前 regime → 选择对应模型 → 生成信号
"""
import os, json


import pandas as pd

from data.datahub import get_datahub
from data.feature_store import load_feature_panel
from models import LightGBMRegressor, prepare_xy, MODEL_DIR

HUB = get_datahub()


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
    from backtest.run_all_strategies import build_production_regime_map

    regime_map = build_production_regime_map(df_idx["close"])

    # 2. Load all feature data and assign regime
    all_features = load_feature_panel(hub=HUB)
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
        model.save(regime)

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
