"""Shared LightGBM model artifact loading for signals and backtests."""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LoadedModelBundle:
    model: object | None = None
    feature_names: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    selected_model: str = "missing"
    errors: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return self.model is not None and getattr(self.model, "_model", None) is not None


def regime_model_candidates(model_dir: Path, regime: str) -> list[tuple[Path, Path, str]]:
    """Return canonical plus legacy regime-aware artifact names."""
    return [
        (model_dir / f"lgbm_{regime}.pkl", model_dir / f"lgbm_{regime}_meta.json", f"regime:{regime}"),
        (
            model_dir / f"lgbm_lgbm_{regime}.pkl",
            model_dir / f"lgbm_{regime}_meta.json",
            f"regime:{regime}:legacy",
        ),
    ]


def global_model_candidates(model_dir: Path, model_version: str = "best") -> list[tuple[Path, Path, str]]:
    return [(model_dir / f"lgbm_{model_version}.pkl", model_dir / "lgbm_best_meta.json", model_version)]


def _load_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_lgbm_bundle(candidates: list[tuple[Path, Path, str]]) -> LoadedModelBundle:
    errors: list[str] = []
    for model_path, meta_path, label in candidates:
        if not model_path.exists():
            continue
        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)
        except Exception as exc:
            errors.append(f"{model_path.name}: {exc}")
            continue
        meta = _load_meta(meta_path)
        feature_names = list(meta.get("features", []) or getattr(model, "_feature_names", []) or [])
        return LoadedModelBundle(
            model=model,
            feature_names=feature_names,
            meta=meta,
            selected_model=label,
            errors=errors,
        )
    return LoadedModelBundle(errors=errors)
