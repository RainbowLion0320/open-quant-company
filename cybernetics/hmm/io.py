"""HMM model persistence helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from cybernetics.hmm.core import HMMConfig, HMMResult
from cybernetics.hmm.preprocessing import _normalise_hmm_preprocessor

def save_hmm_model(result: HMMResult, path: str | Path, preprocessor: Any | None = None) -> None:
    """Save model parameters to disk."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    preprocessor_data = _normalise_hmm_preprocessor(preprocessor or result.preprocessor)

    # Save arrays
    np.savez(
        path / "params.npz",
        means=result.means,
        covars=result.covars,
        df=result.df,
        transmat=result.transmat,
        startprob=result.startprob,
    )

    # Save metadata
    meta = {
        "log_likelihood": result.log_likelihood,
        "n_iter": result.n_iter,
        "aic": result.aic,
        "bic": result.bic,
        "n_samples": result.n_samples,
        "n_features": result.n_features,
        "config": result.config.to_dict(),
    }
    if preprocessor_data:
        meta["preprocessor"] = {
            "kind": preprocessor_data["kind"],
            "n_components": int(np.asarray(preprocessor_data["components"]).shape[0]),
            "n_features_in": int(np.asarray(preprocessor_data["mean"]).shape[0]),
            "whiten": bool(preprocessor_data.get("whiten", False)),
        }
        np.savez(
            path / "preprocessor.npz",
            kind=np.array(preprocessor_data["kind"]),
            components=preprocessor_data["components"],
            mean=preprocessor_data["mean"],
            explained_variance=preprocessor_data["explained_variance"],
            whiten=np.array(bool(preprocessor_data.get("whiten", False))),
        )
    else:
        stale_preprocessor = path / "preprocessor.npz"
        if stale_preprocessor.exists():
            stale_preprocessor.unlink()
    (path / "meta.json").write_text(json.dumps(meta, indent=2))


def load_hmm_model(path: str | Path, config: HMMConfig | None = None) -> HMMResult:
    """Load model parameters from disk."""
    path = Path(path)

    data = np.load(path / "params.npz")
    meta = json.loads((path / "meta.json").read_text())
    preprocessor = None
    preprocessor_path = path / "preprocessor.npz"
    if preprocessor_path.exists():
        pre_data = np.load(preprocessor_path)
        preprocessor = {
            "kind": str(pre_data["kind"].item()),
            "components": pre_data["components"],
            "mean": pre_data["mean"],
            "explained_variance": pre_data["explained_variance"],
            "whiten": bool(pre_data["whiten"].item()),
        }

    cfg = config or HMMConfig(**meta.get("config", {}))

    return HMMResult(
        state_probs=np.array([]),  # not persisted; recompute via predict_proba
        viterbi_states=np.array([]),
        means=data["means"],
        covars=data["covars"],
        df=data["df"],
        transmat=data["transmat"],
        startprob=data["startprob"],
        log_likelihood=meta["log_likelihood"],
        n_iter=meta["n_iter"],
        aic=meta["aic"],
        bic=meta["bic"],
        n_samples=meta["n_samples"],
        n_features=meta["n_features"],
        config=cfg,
        preprocessor=preprocessor,
    )
