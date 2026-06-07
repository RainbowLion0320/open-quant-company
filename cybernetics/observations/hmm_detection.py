"""Student-t HMM live regime detection helper."""
from __future__ import annotations

from typing import Any, Dict

from cybernetics.config import _load_config
from cybernetics.regime import MarketRegime
from cybernetics.regime_scoring import breadth_strength as _score_breadth_strength
from cybernetics.types import MarketBreadth, MarketVolume

def _hmm_detect(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    volume: MarketVolume,
) -> tuple[Dict[str, float], float, float, MarketRegime]:
    """Run Student-t HMM regime detection.

    Returns (regime_probs, confidence, entropy, raw_regime).
    Raises if model not available or inference fails.
    """
    import math

    import numpy as np

    from cybernetics.features import OBSERVATION_COLUMNS, build_observation_matrix, build_regime_features
    from cybernetics.hmm import StudentTHMM, apply_hmm_preprocessor, load_hmm_model

    # Check model path
    try:
        hmm_cfg = _load_config().get("hmm", {})
        model_path = hmm_cfg.get("model_path", "data/reference/models/regime_hmm")
    except Exception:
        model_path = "data/reference/models/regime_hmm"

    from pathlib import Path
    mp = Path(model_path)
    if not (mp / "params.npz").exists():
        raise FileNotFoundError(f"HMM model not found at {mp}")

    # Build features
    # Load bond returns for stock-bond correlation feature
    from cybernetics.features import load_bond_returns
    bond_ret = load_bond_returns()

    features = build_regime_features(
        index_frames,
        breadth_raw=_score_breadth_strength(
            breadth.advance_ratio, breadth.above_ma20, breadth.above_ma60, breadth.above_ma120
        ),
        breadth_above_ma20=breadth.above_ma20,
        breadth_above_ma60=breadth.above_ma60,
        breadth_above_ma120=breadth.above_ma120,
        amount_ratio_5_20=volume.amount_ratio_5_20,
        advance_ratio=breadth.advance_ratio,
        up_amount_ratio=volume.up_amount_ratio,
        sample_size=breadth.sample_size,
        bond_returns=bond_ret,
    )
    if features.empty:
        raise ValueError("Feature construction returned empty DataFrame")

    # Load model
    result = load_hmm_model(mp)

    # Build observation for latest day
    obs_cols = hmm_cfg.get("observation_columns", OBSERVATION_COLUMNS)
    obs, _pca = build_observation_matrix(features, columns=obs_cols, standardise=True)
    if len(obs) == 0:
        raise ValueError("Observation matrix is empty")

    # Use the last observation
    latest = obs[-1:]  # (1, D)
    latest = apply_hmm_preprocessor(latest, result.preprocessor)
    if latest.shape[1] != result.n_features:
        raise ValueError(f"HMM model expects {result.n_features} features, got {latest.shape[1]}")

    # Predict probabilities
    hmm = StudentTHMM(result.config)
    hmm._params = {
        "means": result.means,
        "covars": result.covars,
        "df": result.df,
        "transmat": result.transmat,
        "startprob": result.startprob,
    }
    probs = hmm.predict_proba(latest)[0]  # (3,)

    # Map to regime labels (aligned: 0=bull, 1=sideways, 2=bear)
    regime_probs = {
        "bull": float(probs[0]),
        "sideways": float(probs[1]),
        "bear": float(probs[2]),
    }
    confidence = float(max(probs))
    entropy = -sum(p * math.log(p + 1e-300) for p in probs)

    # Argmax regime
    regime_idx = int(np.argmax(probs))
    regime_map = {0: MarketRegime.BULL, 1: MarketRegime.SIDEWAYS, 2: MarketRegime.BEAR}
    raw_regime = regime_map.get(regime_idx, MarketRegime.SIDEWAYS)

    return regime_probs, confidence, entropy, raw_regime
