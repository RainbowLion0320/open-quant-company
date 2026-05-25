"""Factor research diagnostics for strategy development."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FactorDiagnostics:
    mean_ic: float
    icir: float
    positive_ic_ratio: float
    quantile_spread: float
    monotonicity: float
    observations: int
    periods: int


def rank_ic_by_period(factor: pd.DataFrame, fwd_returns: pd.DataFrame, min_obs: int = 5) -> pd.Series:
    """Compute per-period Spearman rank IC from wide date x symbol matrices."""
    aligned_factor, aligned_returns = factor.align(fwd_returns, join="inner", axis=0)
    aligned_factor, aligned_returns = aligned_factor.align(aligned_returns, join="inner", axis=1)
    rows = []
    for dt in aligned_factor.index:
        pair = pd.concat(
            [aligned_factor.loc[dt].rename("factor"), aligned_returns.loc[dt].rename("return")],
            axis=1,
        ).dropna()
        if len(pair) < min_obs:
            continue
        value = pair["factor"].rank().corr(pair["return"].rank())
        if pd.notna(value):
            rows.append((dt, float(value)))
    return pd.Series(dict(rows), dtype=float)


def _quantile_return_table(factor: pd.DataFrame, fwd_returns: pd.DataFrame, quantiles: int) -> pd.Series:
    aligned_factor, aligned_returns = factor.align(fwd_returns, join="inner", axis=0)
    aligned_factor, aligned_returns = aligned_factor.align(aligned_returns, join="inner", axis=1)
    period_tables = []
    for dt in aligned_factor.index:
        data = pd.concat(
            [aligned_factor.loc[dt].rename("factor"), aligned_returns.loc[dt].rename("return")],
            axis=1,
        ).dropna()
        bucket_count = min(quantiles, len(data))
        if bucket_count < 2:
            continue
        ranks = data["factor"].rank(method="first")
        data["bucket"] = pd.qcut(ranks, q=bucket_count, labels=False, duplicates="drop")
        period_tables.append(data.groupby("bucket")["return"].mean())
    if not period_tables:
        return pd.Series(dtype=float)
    return pd.concat(period_tables, axis=1).mean(axis=1).sort_index()


def factor_diagnostics(
    factor: pd.DataFrame,
    fwd_returns: pd.DataFrame,
    quantiles: int = 5,
    min_obs: int = 5,
) -> FactorDiagnostics:
    """Summarize IC, ICIR, quantile spread and monotonicity for one factor."""
    ic = rank_ic_by_period(factor, fwd_returns, min_obs=min_obs)
    mean_ic = float(ic.mean()) if len(ic) else 0.0
    ic_std = float(ic.std(ddof=1)) if len(ic) > 1 else 0.0
    icir = mean_ic / ic_std if ic_std > 0 else (float("inf") if mean_ic > 0 else 0.0)
    positive_ic_ratio = float((ic > 0).mean()) if len(ic) else 0.0

    qret = _quantile_return_table(factor, fwd_returns, quantiles)
    if len(qret) >= 2:
        quantile_spread = float(qret.iloc[-1] - qret.iloc[0])
        diffs = qret.diff().dropna()
        monotonicity = float((diffs >= 0).mean()) if len(diffs) else 0.0
    else:
        quantile_spread = 0.0
        monotonicity = 0.0

    obs_factor, obs_returns = factor.align(fwd_returns, join="inner", axis=0)
    obs_factor, obs_returns = obs_factor.align(obs_returns, join="inner", axis=1)
    observations = int(obs_factor.where(obs_returns.notna()).count().sum())
    return FactorDiagnostics(
        mean_ic=round(mean_ic, 6),
        icir=round(icir, 6) if np.isfinite(icir) else float("inf"),
        positive_ic_ratio=round(positive_ic_ratio, 6),
        quantile_spread=round(quantile_spread, 6),
        monotonicity=round(monotonicity, 6),
        observations=observations,
        periods=int(len(ic)),
    )


def factor_correlation_clusters(factors: pd.DataFrame, threshold: float = 0.85) -> list[list[str]]:
    """Group highly correlated factor columns for redundancy review."""
    if factors.empty:
        return []
    corr = factors.corr(method="spearman").abs().fillna(0.0)
    remaining = set(corr.columns)
    clusters: list[list[str]] = []
    for col in corr.columns:
        if col not in remaining:
            continue
        cluster = {col}
        for other in list(remaining):
            if other != col and corr.loc[col, other] >= threshold:
                cluster.add(other)
        remaining -= cluster
        clusters.append(sorted(cluster))
    return clusters
