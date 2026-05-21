"""
Optuna 超参数优化 + 模型训练 + 评估

用法:
  python scripts/tune_model.py --n-trials 50
"""
import os, sys, time, json
from pathlib import Path

for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from data.datahub import get_datahub
from data.feature_store import FEATURES_DIR, TimeSeriesSplitter
from models import LightGBMRegressor, prepare_xy, MODEL_DIR

HUB = get_datahub()


def load_all_features() -> pd.DataFrame:
    """加载所有月份的特征并拼接"""
    dfs = []
    for pq in sorted(FEATURES_DIR.glob("*.parquet")):
        if pq.stem in ("scan_meta", "buffett_scan"):
            continue
        df = HUB.read_parquet(pq)
        if "month" not in df.columns:
            df["month"] = pq.stem
        dfs.append(df)
    if not dfs:
        raise RuntimeError(f"No features found in {FEATURES_DIR}")
    return pd.concat(dfs, ignore_index=True)


def optimize_hyperparams(n_trials: int = 50) -> dict:
    """Optuna 超参数搜索"""
    try:
        import optuna
    except ImportError:
        print("Optuna not installed. Run: pip install optuna")
        return {}

    print(f"\n[Optuna] 超参数优化 ({n_trials} trials)...")
    df = load_all_features()
    valid = df.dropna(subset=["ret_fwd_20d"])

    # ── 滚动窗口 CV (消除数据泄露) ──
    from data.feature_store import TimeSeriesSplitter
    months = sorted(valid["month"].unique())
    splitter = TimeSeriesSplitter(train_months=48, test_months=6, step_months=12)
    splits = splitter.split(months)

    if len(splits) < 2:
        print(f"  ⚠️ 只有 {len(splits)} 个 CV split, 用80/20 fallback")
        split_idx = int(len(months) * 0.8)
        splits = [(months[:split_idx], months[split_idx:])]

    # 预构建每轮的数据
    fold_data = []
    for train_ms, test_ms in splits:
        train = valid[valid["month"].isin(train_ms)]
        test = valid[valid["month"].isin(test_ms)]
        if len(train) < 100 or len(test) < 20:
            continue
        X_tr, y_tr = prepare_xy(train, "ret_fwd_20d")
        X_te, y_te = prepare_xy(test, "ret_fwd_20d")
        fold_data.append((X_tr, y_tr, X_te, y_te, train_ms, test_ms))

    print(f"  CV folds: {len(fold_data)} (48月训练, 6月测试, 12月步长)")

    def objective(trial):
        params = {
            "num_leaves": trial.suggest_int("num_leaves", 7, 63),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        }
        ics = []
        for X_tr, y_tr, X_te, y_te, _, _ in fold_data:
            model = LightGBMRegressor(**params, random_state=42)
            model.fit(X_tr, y_tr)
            preds = model.predict(X_te)
            ic, _ = spearmanr(preds, y_te)
            ics.append(ic if not np.isnan(ic) else 0.0)
        return np.mean(ics) if ics else -1.0

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    print(f"\n  Best IC: {study.best_value:.4f}")
    print(f"  Best params: {study.best_params}")
    return study.best_params


def train_best_model(params: dict = None) -> str:
    """用最优参数训练最终模型并保存"""
    print(f"\n[训练] 最终模型...")
    df = load_all_features()
    valid = df.dropna(subset=["ret_fwd_20d"])
    X, y = prepare_xy(valid, "ret_fwd_20d")

    if params is None:
        params = {"num_leaves": 31, "learning_rate": 0.05, "n_estimators": 200}

    model = LightGBMRegressor(**params, random_state=42)
    model.fit(X, y)

    # 评估
    preds = model.predict(X)
    ic, _ = spearmanr(preds, y)
    ic = ic if not np.isnan(ic) else 0.0
    print(f"  In-sample IC: {ic:.4f}")

    # 特征重要性
    imp = model.feature_importance()
    print(f"\n  Top 10 特征:")
    for f, v in imp.head(10).items():
        print(f"    {f}: {v:.0f}")

    # 保存
    path = model.save("best")
    print(f"\n  模型已保存: {path}")

    # 保存训练元数据
    meta = {
        "ic_in_sample": round(float(ic), 4),
        "n_samples": len(X),
        "n_features": len(X.columns),
        "params": params,
        "features": list(X.columns),
        "trained_at": pd.Timestamp.now().isoformat(),
    }
    with open(MODEL_DIR / "lgbm_best_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    return path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-trials", type=int, default=50)
    ap.add_argument("--optimize", action="store_true", default=True)
    ap.add_argument("--train-only", action="store_true")
    args = ap.parse_args()

    if args.train_only:
        train_best_model()
    else:
        best_params = optimize_hyperparams(args.n_trials)
        if best_params:
            train_best_model(best_params)
        else:
            train_best_model()
