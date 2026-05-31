#!/usr/bin/env python3
"""HMM Regime Model Training Pipeline.

Trains a Student-t HMM on historical market data and evaluates it
against the current rule-based champion via walk-forward validation.

Usage:
    python scripts/train_regime_hmm.py --output reports/hmm_training/
    python scripts/train_regime_hmm.py --start 2018-01-01 --output reports/hmm_training/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("train_regime_hmm")


def _load_index_daily(symbol: str = "sh000001") -> pd.DataFrame:
    """Load benchmark index daily data."""
    try:
        from data.fetcher import _read_cache, get_index_daily

        cached = _read_cache(f"index_daily_{symbol}_default", max_age_hours=0)
        if cached is not None and len(cached) > 0:
            return cached
        return get_index_daily(symbol, force_refresh=False)
    except Exception:
        return pd.DataFrame()


def _load_breadth_history(start: str, end: str) -> pd.DataFrame:
    """Load full-market breadth history from local stock parquet."""
    try:
        from research.regime_training import load_full_market_breadth_history

        return load_full_market_breadth_history(start=start, end=end)
    except Exception as e:
        log.warning(f"Failed to load breadth history: {e}")
        return pd.DataFrame()


def _build_features_for_training(
    index_frames: dict[str, pd.DataFrame],
    breadth_history: pd.DataFrame | None,
) -> pd.DataFrame:
    """Build the feature DataFrame for HMM training."""
    from cybernetics.features import build_regime_features, load_bond_returns

    breadth_kwargs = {}
    if breadth_history is not None and not breadth_history.empty:
        # Use the latest breadth values as defaults; per-row values come from features
        latest = breadth_history.iloc[-1] if len(breadth_history) > 0 else {}
        breadth_kwargs = {
            "breadth_above_ma20": float(latest.get("above_ma20", 0.5)),
            "breadth_above_ma60": float(latest.get("above_ma60", 0.5)),
            "breadth_above_ma120": float(latest.get("above_ma120", 0.5)),
            "amount_ratio_5_20": float(latest.get("amount_ratio_5_20", 1.0)),
            "advance_ratio": float(latest.get("advance_ratio", 0.5)),
            "up_amount_ratio": float(latest.get("up_amount_ratio", 0.5)),
            "sample_size": int(latest.get("sample_size", 0)),
        }

    bond_ret = load_bond_returns()
    features = build_regime_features(index_frames, bond_returns=bond_ret, **breadth_kwargs)
    return features


def _train_single_hmm(
    X: np.ndarray,
    n_states: int = 3,
    n_init: int = 5,
    random_seed: int = 42,
    forward_returns: np.ndarray | None = None,
) -> dict:
    """Train a single HMM and return metrics."""
    from cybernetics.hmm_engine import HMMConfig, StudentTHMM, align_states

    config = HMMConfig(
        n_states=n_states,
        max_iter=100,
        tol=1e-4,
        n_init=n_init,
        random_seed=random_seed,
    )

    hmm = StudentTHMM(config)
    result = hmm.fit(X, forward_returns=forward_returns)

    return {
        "result": result,
        "hmm": hmm,
        "log_likelihood": result.log_likelihood,
        "aic": result.aic,
        "bic": result.bic,
        "n_iter": result.n_iter,
    }


def _evaluate_regime_quality(
    probs: np.ndarray,
    close: pd.Series,
    regime_labels: np.ndarray,
) -> dict:
    """Evaluate the quality of HMM regime labels."""
    # Forward returns
    fwd_ret_20 = close.pct_change(20).shift(-20)

    # Align lengths
    min_len = min(len(fwd_ret_20), len(regime_labels))
    fwd_ret_20 = fwd_ret_20.iloc[:min_len]
    regime_labels = regime_labels[:min_len]

    # Per-regime stats
    stats = {}
    regime_names = {0: "bull", 1: "sideways", 2: "bear"}
    for idx, name in regime_names.items():
        mask = regime_labels == idx
        if mask.sum() == 0:
            stats[f"{name}_count"] = 0
            stats[f"{name}_mean_fwd_20d"] = 0.0
            continue
        subset = fwd_ret_20.iloc[mask].dropna()
        stats[f"{name}_count"] = int(mask.sum())
        stats[f"{name}_mean_fwd_20d"] = float(subset.mean()) if len(subset) > 0 else 0.0

    # Return separation
    bull_ret = stats.get("bull_mean_fwd_20d", 0)
    bear_ret = stats.get("bear_mean_fwd_20d", 0)
    stats["return_separation"] = float(bull_ret - bear_ret)

    # State distribution
    total = len(regime_labels)
    for idx, name in regime_names.items():
        stats[f"{name}_ratio"] = float((regime_labels == idx).sum() / max(total, 1))

    # Stability: average dwell
    changes = np.sum(np.diff(regime_labels) != 0)
    stats["turnovers"] = int(changes)
    stats["avg_dwell"] = float(total / max(changes + 1, 1))

    # Entropy of state distribution
    probs_mean = probs.mean(axis=0)
    entropy = -sum(p * np.log(p + 1e-300) for p in probs_mean)
    stats["mean_entropy"] = float(entropy)

    return stats


def _walk_forward_hmm(
    features: pd.DataFrame,
    close: pd.Series,
    index_frames: dict | None = None,
    n_states: int = 3,
    train_years: int = 4,
    validate_years: int = 1,
) -> list[dict]:
    """Walk-forward validation for HMM."""
    from cybernetics.features import OBSERVATION_COLUMNS, build_observation_matrix
    from cybernetics.hmm_engine import StudentTHMM, HMMConfig

    results = []
    years = sorted(set(features.index.year))

    for start_idx in range(0, len(years) - train_years - validate_years + 1):
        train_years_set = set(years[start_idx : start_idx + train_years])
        validate_years_set = set(years[start_idx + train_years : start_idx + train_years + validate_years])

        train_mask = features.index.year.isin(train_years_set)
        validate_mask = features.index.year.isin(validate_years_set)

        train_features = features[train_mask]
        validate_features = features[validate_mask]

        if len(train_features) < 252 or len(validate_features) < 60:
            continue

        # Build observation matrices
        train_X, _pca = build_observation_matrix(train_features)
        validate_X, _pca2 = build_observation_matrix(validate_features)

        if len(train_X) == 0 or len(validate_X) == 0:
            continue

        # Compute forward returns for training alignment
        train_fwd = None
        if index_frames:
            bench = list(index_frames.values())[0].copy()
            if "date" in bench.columns and bench.index.name != "date":
                bench["date"] = pd.to_datetime(bench["date"], errors="coerce")
                bench = bench.dropna(subset=["date"]).set_index("date").sort_index()
            if "close" in bench.columns:
                bench_close = pd.to_numeric(bench["close"], errors="coerce")
                fwd = bench_close.pct_change(20).shift(-20)
                obs_cols = [c for c in OBSERVATION_COLUMNS if c in train_features.columns]
                obs_idx = train_features.dropna(subset=obs_cols).index
                train_fwd = np.nan_to_num(fwd.reindex(obs_idx).values, nan=0.0)

        # Train on training window
        try:
            hmm_result = _train_single_hmm(train_X, n_states=n_states, n_init=3, forward_returns=train_fwd)
            hmm = hmm_result["hmm"]
        except Exception as e:
            log.warning(f"Walk-forward train failed for {train_years_set}: {e}")
            continue

        # Predict on validation window
        validate_probs = hmm.predict_proba(validate_X)
        validate_states = hmm.predict(validate_X)

        # Evaluate
        validate_close = close[close.index.isin(validate_features.index)]
        if len(validate_close) != len(validate_states):
            validate_close = validate_close.iloc[:len(validate_states)]

        quality = _evaluate_regime_quality(validate_probs, validate_close, validate_states)

        results.append({
            "train_start": str(min(train_years_set)),
            "train_end": str(max(train_years_set)),
            "validate_start": str(min(validate_years_set)),
            "validate_end": str(max(validate_years_set)),
            "train_rows": len(train_X),
            "validate_rows": len(validate_X),
            **quality,
        })

    return results


def _compare_with_champion(
    features: pd.DataFrame,
    close: pd.Series,
    hmm_probs: np.ndarray,
    hmm_states: np.ndarray,
) -> dict:
    """Compare HMM regimes with the current rule-based champion."""
    from research.regime_training import apply_policy, CHAMPION_POLICY

    # Apply champion policy
    champion_applied = apply_policy(features, CHAMPION_POLICY)
    champion_regimes = champion_applied["regime"].values

    # Map champion regimes to numeric
    regime_map = {"bull": 0, "sideways": 1, "bear": 2}
    champion_numeric = np.array([regime_map.get(r, 1) for r in champion_regimes])

    # Ensure same length
    min_len = min(len(champion_numeric), len(hmm_states), len(close))
    champion_numeric = champion_numeric[:min_len]
    hmm_states = hmm_states[:min_len]
    close_aligned = close.iloc[:min_len]

    # Agreement rate
    agreement = float(np.mean(champion_numeric == hmm_states))

    # Per-regime comparison
    fwd_ret_20 = close_aligned.pct_change(20).shift(-20)

    comparison = {
        "agreement_rate": agreement,
        "hmm_regime_quality": _evaluate_regime_quality(hmm_probs[:min_len], close_aligned, hmm_states),
    }

    # Champion regime quality
    champion_quality = {}
    for regime_name, regime_idx in regime_map.items():
        mask = champion_numeric == regime_idx
        if mask.sum() > 0:
            subset = fwd_ret_20.iloc[mask].dropna()
            champion_quality[f"{regime_name}_mean_fwd_20d"] = float(subset.mean()) if len(subset) > 0 else 0.0
            champion_quality[f"{regime_name}_count"] = int(mask.sum())
    comparison["champion_regime_quality"] = champion_quality

    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description="Train Student-t HMM for market regime detection.")
    parser.add_argument("--start", default="2018-01-01", help="Start date")
    parser.add_argument("--end", default="auto", help="End date or 'auto'")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--n-states", type=int, default=3, help="Number of HMM states")
    parser.add_argument("--n-init", type=int, default=5, help="Number of random initialisations")
    parser.add_argument("--pca-components", type=int, default=None, help="PCA components (None=disable)")
    parser.add_argument("--symbol", default="sh000001", help="Benchmark index symbol")
    parser.add_argument("--skip-breadth", action="store_true", help="Skip full-market breadth")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    log.info(f"output={output}")
    log.info(f"start={args.start} end={args.end} n_states={args.n_states} n_init={args.n_init}")

    # Load data
    log.info("Loading index data...")
    index_df = _load_index_daily(args.symbol)
    if index_df.empty:
        log.error(f"Failed to load index data for {args.symbol}")
        return 1

    # Build index frames dict
    index_frames = {args.symbol: index_df}

    # Load breadth history
    breadth_history = None
    if not args.skip_breadth:
        log.info("Loading breadth history...")
        breadth_history = _load_breadth_history(args.start, args.end)
        log.info(f"Breadth rows: {len(breadth_history)}")

    # Build features
    log.info("Building features...")
    features = _build_features_for_training(index_frames, breadth_history)
    if features.empty:
        log.error("Feature construction returned empty DataFrame")
        return 1

    # Apply date filter
    if args.start:
        features = features[features.index >= pd.Timestamp(args.start)]
    if args.end and args.end != "auto":
        features = features[features.index <= pd.Timestamp(args.end)]

    log.info(f"Feature rows: {len(features)}")

    if len(features) < 252:
        log.error(f"Insufficient data: need at least 252 rows, got {len(features)}")
        return 1

    # Build observation matrix
    from cybernetics.features import OBSERVATION_COLUMNS, build_observation_matrix
    from cybernetics.hmm_engine import HMMConfig, StudentTHMM, save_hmm_model

    X, pca = build_observation_matrix(features, n_components=args.pca_components)
    log.info(f"Observation matrix: {X.shape}" + (f" (PCA {args.pca_components} components)" if pca else ""))

    # Compute forward returns for state alignment
    # Use 20-day forward return from the benchmark index
    bench_df = index_frames.get(args.symbol, index_frames.get("sh000001"))
    if bench_df is not None and "close" in bench_df.columns:
        bench = bench_df.copy()
        # Ensure date is the index for proper alignment
        if "date" in bench.columns and bench.index.name != "date":
            bench["date"] = pd.to_datetime(bench["date"], errors="coerce")
            bench = bench.dropna(subset=["date"]).set_index("date").sort_index()
        bench_close = pd.to_numeric(bench["close"], errors="coerce")
        fwd_ret_20 = bench_close.pct_change(20).shift(-20)
        # Align with observation matrix index
        obs_index = features.dropna(subset=[c for c in OBSERVATION_COLUMNS if c in features.columns]).index
        fwd_aligned = fwd_ret_20.reindex(obs_index).values
        fwd_aligned = np.nan_to_num(fwd_aligned, nan=0.0)
        log.info(f"Forward returns: {np.count_nonzero(fwd_aligned)} non-zero / {len(fwd_aligned)} total")
    else:
        fwd_aligned = None
        log.warning("No close column in benchmark, forward return alignment disabled")

    # Train final model on all data
    log.info("Training final HMM model...")
    train_result = _train_single_hmm(X, n_states=args.n_states, n_init=args.n_init, forward_returns=fwd_aligned)
    hmm = train_result["hmm"]
    result = train_result["result"]

    log.info(f"Log-likelihood: {result.log_likelihood:.2f}")
    log.info(f"AIC: {result.aic:.2f}, BIC: {result.bic:.2f}")
    log.info(f"Degrees of freedom: {result.df}")
    log.info(f"Transition matrix:\n{result.transmat}")

    # Save model
    model_path = output / "regime_hmm"
    save_hmm_model(result, model_path)
    log.info(f"Model saved to {model_path}")

    # Evaluate on full data
    probs = hmm.predict_proba(X)
    states = hmm.predict(X)

    # Build close series aligned with features index
    bench_data = index_df.copy()
    bench_data.columns = [str(c).lower() for c in bench_data.columns]
    if "date" in bench_data.columns:
        bench_data["date"] = pd.to_datetime(bench_data["date"], errors="coerce")
        bench_data = bench_data.dropna(subset=["date"]).set_index("date")
    bench_data["close"] = pd.to_numeric(bench_data["close"], errors="coerce")
    close = bench_data["close"].reindex(features.index).ffill().dropna()

    quality = _evaluate_regime_quality(probs, close.iloc[:len(states)], states)
    log.info(f"Regime quality: {json.dumps(quality, indent=2)}")

    # Walk-forward validation
    log.info("Running walk-forward validation...")
    wf_results = _walk_forward_hmm(features, close, index_frames=index_frames, n_states=args.n_states)
    log.info(f"Walk-forward windows: {len(wf_results)}")

    # Compare with champion
    log.info("Comparing with champion...")
    comparison = _compare_with_champion(features, close, probs, states)

    # Write report
    report = {
        "status": "ok",
        "config": result.config.to_dict(),
        "model_path": str(model_path),
        "log_likelihood": result.log_likelihood,
        "aic": result.aic,
        "bic": result.bic,
        "n_iter": result.n_iter,
        "degrees_of_freedom": result.df.tolist(),
        "transition_matrix": result.transmat.tolist(),
        "regime_quality": quality,
        "walk_forward_results": wf_results,
        "champion_comparison": comparison,
    }

    (output / "summary.json").write_text(json.dumps(report, indent=2, default=str))

    # Write markdown report
    md_lines = [
        "# HMM Regime Training Report",
        "",
        f"- States: {args.n_states}",
        f"- Training rows: {len(X)}",
        f"- Log-likelihood: {result.log_likelihood:.2f}",
        f"- AIC: {result.aic:.2f}",
        f"- BIC: {result.bic:.2f}",
        f"- Degrees of freedom: {result.df.tolist()}",
        "",
        "## Transition Matrix",
        "```",
        str(result.transmat),
        "```",
        "",
        "## Regime Quality",
    ]
    for k, v in quality.items():
        md_lines.append(f"- {k}: {v}")

    md_lines.extend(["", "## Walk-Forward Results"])
    for wf in wf_results:
        md_lines.append(
            f"- {wf['train_start']}-{wf['train_end']} → "
            f"{wf['validate_start']}-{wf['validate_end']}: "
            f"separation={wf.get('return_separation', 0):.4f}, "
            f"avg_dwell={wf.get('avg_dwell', 0):.1f}"
        )

    md_lines.extend(["", "## Champion Comparison"])
    md_lines.append(f"- Agreement rate: {comparison.get('agreement_rate', 0):.2%}")
    hmm_q = comparison.get("hmm_regime_quality", {})
    champ_q = comparison.get("champion_regime_quality", {})
    for regime in ("bull", "sideways", "bear"):
        hmm_ret = hmm_q.get(f"{regime}_mean_fwd_20d", 0)
        champ_ret = champ_q.get(f"{regime}_mean_fwd_20d", 0)
        md_lines.append(f"- {regime}: HMM={hmm_ret:.4f}, Champion={champ_ret:.4f}")

    (output / "report.md").write_text("\n".join(md_lines))

    log.info("Training complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
