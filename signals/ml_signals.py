"""
ML 信号计算 — 用训练好的 LightGBM 模型生成每日买卖信号

集成到 compute_signals.py: 跟巴菲特/多因子/控制论并列运行
"""
from pathlib import Path
from typing import List, Dict

import pandas as pd
import numpy as np


from data.symbols import CIRCLE_STOCKS, SYMBOL_NAME, SYMBOL_INDUSTRY
from data.price_service import get_stock_prices
from data.price_types import PriceUseCase
from signals.expression import alpha_factors
from signals.selection import apply_ranked_buys
from models import MODEL_DIR
from models.lgbm_runtime import global_model_candidates, load_lgbm_bundle, regime_model_candidates
from data.feature_store import feature_date_key, feature_key_to_date, latest_feature_file
from core.settings import get_settings


def _load_settings() -> dict:
    return get_settings()


def _current_regime() -> tuple[str, dict[str, float]]:
    """Return (regime_string, regime_probs)."""
    try:
        from cybernetics.orchestrator import QuantOrchestrator
        snapshot = QuantOrchestrator().detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
        regime = regime if regime in {"bull", "bear", "sideways"} else "sideways"
        probs = getattr(snapshot, "regime_probs", {})
        return regime, probs if probs else {regime: 1.0}
    except Exception:
        return "sideways", {"sideways": 1.0}


def _load_model_bundle(model_version: str = "best") -> tuple[object | None, list[str], dict, str]:
    """Load regime-aware model when available, falling back to lgbm_best."""
    cfg = _load_settings().get("ml", {})
    regime, _probs = _current_regime()
    use_regime = cfg.get("use_regime_models", True)

    candidates = []
    if use_regime and model_version == "best" and regime in {"bull", "bear", "sideways"}:
        candidates.extend(regime_model_candidates(MODEL_DIR, regime))
    candidates.extend(global_model_candidates(MODEL_DIR, model_version))

    bundle = load_lgbm_bundle(candidates)
    meta = dict(bundle.meta)
    meta["selected_regime"] = regime
    meta["selected_model"] = bundle.selected_model
    meta["load_errors"] = bundle.errors
    if bundle.model is not None:
        return bundle.model, bundle.feature_names, meta, bundle.selected_model
    return None, [], meta, "missing"


def _feature_age_months(month: str) -> int:
    try:
        feature_period = pd.Period(month, freq="M")
        current_period = pd.Timestamp.today().to_period("M")
        return int(current_period.ordinal - feature_period.ordinal)
    except Exception:
        return 9999


def _latest_feature_file(cfg: dict) -> tuple[Path | None, str]:
    latest = latest_feature_file(as_of=pd.Timestamp.today())
    if latest is None:
        return None, "missing"

    latest_month = latest.stem
    age = _feature_age_months(latest_month)
    max_age = int(cfg.get("max_feature_age_months", 3))
    allow_stale = bool(cfg.get("allow_stale_features", False))
    if age > max_age and not allow_stale:
        return None, f"stale:{latest_month}:{age}m>{max_age}m"
    return latest, latest_month


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
    cfg = _load_settings().get("ml", {})
    model, feature_names, meta, selected_model = _load_model_bundle(model_version)

    if model is None:
        print("[ML] ⚠️ 模型未训练, 跳过")
        return []

    ic_val = meta.get("ic_in_sample", meta.get("ic", 0))
    print(f"[ML] 模型已加载 ({selected_model}, IC={ic_val:.4f}, {len(feature_names)} 特征)")


    # 2. 准备股票池
    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    # 3. 加载最新的特征文件 (最近一个月)
    latest_feature_path, feature_status = _latest_feature_file(cfg)
    if latest_feature_path is None:
        print(f"[ML] ⚠️ PIT 特征不可用 ({feature_status}), 请先运行 build_features.py")
        return []

    latest_key = latest_feature_path.stem
    inferred_as_of = feature_key_to_date(latest_key)
    feature_as_of = feature_date_key(inferred_as_of) if inferred_as_of is not None else latest_key
    print(f"[ML] 使用特征: {latest_key}")
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
    live_fallback = bool(cfg.get("allow_live_factor_fallback", False))
    missing_feature_rows = 0
    fallback_rows = 0

    for i, sym in enumerate(symbols):
        try:
            features = {}
            used_fallback = False
            feature_month_detail = feature_as_of[:7]
            feature_asof_detail = feature_as_of
            if sym in feature_df.index:
                row = feature_df.loc[sym]
                feature_month_detail = row.get("month", feature_month_detail)
                feature_asof_detail = row.get("as_of_date", feature_asof_detail)
                for name in feature_names:
                    val = row.get(name, 0.0)
                    try:
                        num = float(val)
                    except (TypeError, ValueError):
                        num = 0.0
                    features[name] = num if np.isfinite(num) else 0.0
            else:
                missing_feature_rows += 1
                if not live_fallback:
                    continue
                fallback_rows += 1
                used_fallback = True
                df = get_stock_prices(sym, use_case=PriceUseCase.SIGNAL)
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
            signals.append({
                "symbol": sym,
                "name": SYMBOL_NAME.get(sym, sym),
                "industry": SYMBOL_INDUSTRY.get(sym, "待分类"),
                "score": round(score, 1),
                "signal": "hold",
                "detail": {
                    "pred_raw": round(float(pred), 4),
                    "model": selected_model,
                    "regime": meta.get("selected_regime", ""),
                    "feature_month": feature_month_detail,
                    "feature_as_of_date": feature_asof_detail,
                    "feature_source": "live_fallback" if used_fallback else "feature_store",
                },
            })

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"ML score failed for {sym}: {e}")

        if (i + 1) % 100 == 0:
            buys = sum(1 for s in signals if s["signal"] == "buy")
            print(f"  ML [{i+1}/{total}] {buys} buys")

    if missing_feature_rows:
        print(
            f"[ML] 特征覆盖: {len(signals)} scored, "
            f"{missing_feature_rows} symbols missing store rows, {fallback_rows} live fallback"
        )

    score_scale = cfg.get("score_scale", 5.0)
    if score_scale != 5.0:
        for s in signals:
            pred = float((s.get("detail") or {}).get("pred_raw", 0.0))
            s["score"] = round(max(0.0, min(100.0, 50.0 + 50.0 * np.tanh(pred * float(score_scale)))), 1)

    signals = apply_ranked_buys(signals, "ml_lgbm", default_min_score=52.0)
    buys = sum(1 for s in signals if s["signal"] == "buy")
    print(f"  ML 完成: {len(signals)} stocks, {buys} buys")
    return signals
