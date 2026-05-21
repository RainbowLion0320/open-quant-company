#!/usr/bin/env python3
"""
Cron: 周度模型重训 (每周六执行)
- 仅重训模型（不重建特征——特征每月构建一次足够）
- LightGBM + Optuna 快速重训 (20 trials)
- 自动保存 lgbm_best.pkl + meta
"""
import os, sys, time, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'


def main():
    start = time.time()
    print(f"[Retrain] {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    from scripts.tune_model import load_all_features, optimize_hyperparams, train_best_model

    df = load_all_features()
    valid = df.dropna(subset=["ret_fwd_20d"])
    print(f"  样本: {len(valid)}")

    best_params = optimize_hyperparams(n_trials=20)
    path = train_best_model(best_params) if best_params else train_best_model()

    elapsed = time.time() - start
    log = {"timestamp": datetime.now().isoformat(), "elapsed": round(elapsed, 1),
           "model": str(path), "samples": len(valid)}
    log_dir = Path(__file__).resolve().parent.parent / "data" / "models"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "retrain_log.jsonl", "a") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")

    print(f"[Retrain] 完成 {elapsed:.0f}s → {path}")
    return 0


if __name__ == "__main__":
    from data.cron_logger import cron_run
    with cron_run("weekly_retrain"):
        sys.exit(main())
