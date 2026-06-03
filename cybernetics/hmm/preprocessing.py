"""HMM input preprocessor helpers."""
from __future__ import annotations

from typing import Any

import numpy as np

def _normalise_hmm_preprocessor(preprocessor: Any | None) -> dict[str, Any] | None:
    """Convert supported preprocessors to a small numpy-serialisable dict."""
    if preprocessor is None:
        return None
    if isinstance(preprocessor, dict):
        if preprocessor.get("kind") != "pca":
            raise ValueError(f"Unsupported HMM preprocessor: {preprocessor.get('kind')}")
        return preprocessor
    if hasattr(preprocessor, "components_") and hasattr(preprocessor, "mean_"):
        return {
            "kind": "pca",
            "components": np.asarray(preprocessor.components_, dtype=np.float64),
            "mean": np.asarray(preprocessor.mean_, dtype=np.float64),
            "explained_variance": np.asarray(preprocessor.explained_variance_, dtype=np.float64),
            "whiten": bool(getattr(preprocessor, "whiten", False)),
        }
    raise ValueError(f"Unsupported HMM preprocessor type: {type(preprocessor).__name__}")


def apply_hmm_preprocessor(X: np.ndarray, preprocessor: dict[str, Any] | None) -> np.ndarray:
    """Apply a persisted HMM input preprocessor to raw observation rows."""
    X = np.asarray(X, dtype=np.float64)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    if preprocessor is None:
        return X
    if preprocessor.get("kind") != "pca":
        raise ValueError(f"Unsupported HMM preprocessor: {preprocessor.get('kind')}")

    mean = np.asarray(preprocessor["mean"], dtype=np.float64)
    components = np.asarray(preprocessor["components"], dtype=np.float64)
    if X.shape[1] != mean.shape[0]:
        raise ValueError(f"HMM preprocessor expects {mean.shape[0]} features, got {X.shape[1]}")

    transformed = (X - mean) @ components.T
    if preprocessor.get("whiten", False):
        scale = np.sqrt(np.asarray(preprocessor["explained_variance"], dtype=np.float64))
        scale = np.where(scale > np.finfo(float).eps, scale, 1.0)
        transformed = transformed / scale
    return transformed
