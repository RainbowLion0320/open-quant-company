"""
ML 信号计算 — 用训练好的 LightGBM 模型生成每日买卖信号

集成到 compute_signals.py: 跟巴菲特/多因子/控制论并列运行
"""
import sys, os, pickle, json
from pathlib import Path
from typing import List, Dict

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.symbols import CIRCLE_STOCKS, SYMBOL_NAME, SYMBOL_INDUSTRY
from data.fetcher import get_stock_daily
from signals.expression import alpha_factors
from models import MODEL_DIR
from data.feature_store import FEATURES_DIR


def compute_ml_signals(limit: int = 0, model_version: str = "best") -> List[dict]:
    """
    用训练好的 LightGBM 模型计算全量 ML 信号。

    Args:
        limit: 限制股票数 (0=全量)
        model_version: 模型版本 ("best" 或日期标签)

    Returns:
        信号列表 [{symbol, name, industry, score, signal, detail}]
    """
    # 1. 加载模型
    model_path = MODEL_DIR / f"lgbm_{model_version}.pkl"
    meta_path = MODEL_DIR / "lgbm_best_meta.json"

    model = None
    feature_names = []
    meta = {}
    if model_path.exists():
        with open(model_path, "rb") as f:
            model = pickle.load(f)
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
            feature_names = meta.get("features", [])
    if not feature_names:
        feature_names = list(getattr(model, "_feature_names", []) or [])

    if model is None:
        print("[ML] ⚠️ 模型未训练, 跳过")
        return []

    ic_val = meta.get('ic_in_sample', 0)
    print(f"[ML] 模型已加载 (IC={ic_val:.4f}, {len(feature_names)} 特征)")


    # 2. 准备股票池
    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    # 3. 加载最新的特征文件 (最近一个月)
    pq_files = sorted(FEATURES_DIR.glob("*.parquet"))
    if not pq_files:
        print("[ML] ⚠️ 无 PIT 特征文件, 请先运行 build_features.py")
        return []

    latest_feature_path = pq_files[-1]
    latest_month = latest_feature_path.stem
    print(f"[ML] 使用特征: {latest_month}")
    try:
        feature_df = pd.read_parquet(latest_feature_path)
    except Exception as e:
        print(f"[ML] ⚠️ 特征文件读取失败: {e}")
        return []
    if "symbol" not in feature_df.columns:
        print("[ML] ⚠️ 特征文件缺少 symbol 列")
        return []

    feature_df = feature_df.drop_duplicates("symbol", keep="last").set_index("symbol")
    skip_cols = {"symbol", "date", "month", "name", "ret_fwd_20d", "ts_code"}
    if not feature_names:
        feature_names = [
            c for c in feature_df.columns
            if c not in skip_cols and pd.api.types.is_numeric_dtype(feature_df[c])
        ]

    # 4. 对每只股票生成预测
    factors = alpha_factors()
    signals = []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        try:
            features = {}
            if sym in feature_df.index:
                row = feature_df.loc[sym]
                for name in feature_names:
                    val = row.get(name, 0.0)
                    try:
                        num = float(val)
                    except (TypeError, ValueError):
                        num = 0.0
                    features[name] = num if np.isfinite(num) else 0.0
            else:
                df = get_stock_daily(sym)
                if df is None or len(df) < 60:
                    continue
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                idx = len(df) - 1

                for name, factor in factors.items():
                    if feature_names and name not in feature_names:
                        continue
                    val = factor.compute(df, idx)
                    features[name] = val if not (isinstance(val, float) and np.isnan(val)) else 0.0

            # 预测
            X = pd.DataFrame([features])
            if feature_names:
                X = X.reindex(columns=feature_names, fill_value=0)
            X = X.fillna(0)

            pred = float(model.predict(X)[0])

            # 评分: sigmoid 映射
            score = 50.0 + 50.0 * np.tanh(pred * 5)
            score = max(0.0, min(100.0, score))
            signal = "buy" if score >= 50 else "hold"

            signals.append({
                "symbol": sym,
                "name": SYMBOL_NAME.get(sym, sym),
                "industry": SYMBOL_INDUSTRY.get(sym, "待分类"),
                "score": round(score, 1),
                "signal": signal,
                "detail": {
                    "pred_raw": round(float(pred), 4),
                    "model": model_version,
                },
            })

        except Exception:
            pass

        if (i + 1) % 100 == 0:
            buys = sum(1 for s in signals if s["signal"] == "buy")
            print(f"  ML [{i+1}/{total}] {buys} buys")

    buys = sum(1 for s in signals if s["signal"] == "buy")
    print(f"  ML 完成: {len(signals)} stocks, {buys} buys")
    return signals
