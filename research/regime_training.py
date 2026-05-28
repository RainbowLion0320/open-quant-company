"""Offline champion/challenger training helpers for market regime research."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from cybernetics.regime_policy import PRODUCTION_REGIME_POLICY
from cybernetics.regime_scoring import breadth_strength, clamp, volume_strength
from research.forward_labels import (
    build_forward_labels as _shared_build_forward_labels,
    build_profit_labels as _shared_build_profit_labels,
)
from research.performance import portfolio_metrics


class PromotionGateResult(StrEnum):
    KEEP_CHAMPION = "keep_champion"
    RECOMMEND_CHALLENGER_FOR_REVIEW = "recommend_challenger_for_review"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class RegimePolicy:
    candidate_id: str
    weights: dict[str, float]
    bull_threshold: float = 65.0
    bear_threshold: float = 35.0
    trend_confirm: float = 0.55
    breadth_confirm: float = 0.55
    bear_trend_breakdown: float = 0.40
    bear_breadth_breakdown: float = 0.40
    min_dwell: int = 1
    smoothing_window: int = 1
    complexity: int = 1


CHAMPION_POLICY = RegimePolicy(
    candidate_id="champion_current_formula",
    weights=PRODUCTION_REGIME_POLICY.normalized_weights,
    bull_threshold=PRODUCTION_REGIME_POLICY.bull_threshold,
    bear_threshold=PRODUCTION_REGIME_POLICY.bear_threshold,
    trend_confirm=PRODUCTION_REGIME_POLICY.trend_confirm,
    breadth_confirm=PRODUCTION_REGIME_POLICY.breadth_confirm,
    bear_trend_breakdown=PRODUCTION_REGIME_POLICY.bear_trend_breakdown,
    bear_breadth_breakdown=PRODUCTION_REGIME_POLICY.bear_breadth_breakdown,
    min_dwell=PRODUCTION_REGIME_POLICY.min_dwell,
    smoothing_window=1,
    complexity=1,
)

TREND_ONLY_POLICY = RegimePolicy(
    candidate_id="trend_only_baseline",
    weights={"trend": 1.0, "breadth": 0.0, "risk": 0.0, "volume": 0.0},
    complexity=1,
)

TREND_BREADTH_POLICY = RegimePolicy(
    candidate_id="trend_breadth_baseline",
    weights={"trend": 0.55, "breadth": 0.45, "risk": 0.0, "volume": 0.0},
    complexity=1,
)

BASELINE_IDS = {TREND_ONLY_POLICY.candidate_id, TREND_BREADTH_POLICY.candidate_id}

DEFAULT_EXPOSURE_MAP = {
    "risk_on": {"equity": 0.80, "defensive": 0.20},
    "neutral": {"equity": 0.40, "defensive": 0.60},
    "risk_off": {"equity": 0.10, "defensive": 0.90},
}

PROFIT_REQUIRED_BASELINES = {
    "buy_and_hold_equity",
    "fixed_60_40",
    "ma_20_60_timing",
}

PROFIT_BASELINE_NAMES = [
    "buy_and_hold_equity",
    "fixed_80_20",
    "fixed_60_40",
    "fixed_40_60",
    "cash_only",
    "ma_20_60_timing",
    "ma_60_120_timing",
    "trend_only_regime",
    "trend_breadth_regime",
    "current_champion_formula",
    "best_challenger",
]


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Return a sorted OHLCV frame with datetime index and numeric close/volume."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["close", "volume", "amount"])
    data = df.copy()
    data.columns = [str(c).lower() for c in data.columns]
    if "close" not in data.columns and "收盘" in df.columns:
        data["close"] = df["收盘"]
    if "volume" not in data.columns and "成交量" in df.columns:
        data["volume"] = df["成交量"]
    if "amount" not in data.columns and "成交额" in df.columns:
        data["amount"] = df["成交额"]

    if "date" in data.columns:
        dates = pd.to_datetime(data["date"], errors="coerce")
    elif "trade_date" in data.columns:
        dates = pd.to_datetime(data["trade_date"], errors="coerce")
    else:
        dates = pd.to_datetime(data.index, errors="coerce")

    data = data.assign(date=dates).dropna(subset=["date"])
    data["close"] = pd.to_numeric(data.get("close"), errors="coerce")
    if "volume" in data.columns:
        data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(0.0)
    elif "vol" in data.columns:
        data["volume"] = pd.to_numeric(data["vol"], errors="coerce").fillna(0.0)
    else:
        data["volume"] = 0.0
    if "amount" in data.columns:
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    else:
        data["amount"] = data["volume"] * data["close"]
    data = data.dropna(subset=["close"]).sort_values("date").set_index("date")
    return data[["close", "volume", "amount"]]


def build_forward_labels(close: pd.Series, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    """Build forward labels from rows after each feature date."""
    return _shared_build_forward_labels(close, horizons)


def _smooth(series: pd.Series, window: int) -> pd.Series:
    if window <= 1:
        return series
    return series.rolling(window, min_periods=1).mean()


def _enforce_min_dwell(raw_regimes: Sequence[str], min_dwell: int) -> list[str]:
    if min_dwell <= 1 or not raw_regimes:
        return list(raw_regimes)

    current = raw_regimes[0]
    output = [current]
    pending: str | None = None
    pending_start = 0
    pending_count = 0

    for pos, regime in enumerate(raw_regimes[1:], start=1):
        if regime == current:
            pending = None
            pending_count = 0
            output.append(current)
            continue

        if regime != pending:
            pending = regime
            pending_start = pos
            pending_count = 1
            output.append(current)
            continue

        pending_count += 1
        output.append(current)
        if pending_count >= min_dwell:
            current = regime
            for backfill_pos in range(pending_start, pos + 1):
                output[backfill_pos] = current
            pending = None
            pending_count = 0

    return output


def apply_policy(features: pd.DataFrame, policy: RegimePolicy) -> pd.DataFrame:
    """Apply an interpretable regime policy to historical feature rows."""
    data = features.sort_index().copy()
    trend = _smooth(data["trend_raw"].astype(float), policy.smoothing_window)
    breadth = _smooth(data["breadth_raw"].astype(float), policy.smoothing_window)
    risk = _smooth(data["risk_raw"].astype(float), policy.smoothing_window)
    volume = _smooth(data["volume_raw"].astype(float), policy.smoothing_window)
    score = (
        trend * policy.weights.get("trend", 0.0)
        + breadth * policy.weights.get("breadth", 0.0)
        + risk * policy.weights.get("risk", 0.0)
        + volume * policy.weights.get("volume", 0.0)
    ) * 100.0

    raw = []
    for idx, value in score.items():
        row = data.loc[idx]
        if (
            value >= policy.bull_threshold
            and trend.loc[idx] >= policy.trend_confirm
            and row.get("advance_ratio", breadth.loc[idx]) >= policy.breadth_confirm
        ):
            raw.append("bull")
        elif (
            value <= policy.bear_threshold
            or (trend.loc[idx] <= policy.bear_trend_breakdown and breadth.loc[idx] <= policy.bear_breadth_breakdown)
        ):
            raw.append("bear")
        else:
            raw.append("sideways")

    regimes = _enforce_min_dwell(raw, policy.min_dwell)
    return pd.DataFrame({"score": score.round(2), "regime": regimes}, index=data.index)


def generate_candidate_policies(max_candidates: int = 500) -> list[RegimePolicy]:
    weight_sets = [
        {"trend": 1.0, "breadth": 0.0, "risk": 0.0, "volume": 0.0},
        {"trend": 0.55, "breadth": 0.45, "risk": 0.0, "volume": 0.0},
        {"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10},
        {"trend": 0.30, "breadth": 0.40, "risk": 0.20, "volume": 0.10},
        {"trend": 0.30, "breadth": 0.30, "risk": 0.30, "volume": 0.10},
        {"trend": 0.25, "breadth": 0.45, "risk": 0.20, "volume": 0.10},
        {"trend": 0.40, "breadth": 0.25, "risk": 0.25, "volume": 0.10},
    ]
    bull_thresholds = [60.0, 65.0, 70.0]
    bear_thresholds = [30.0, 35.0, 40.0]
    smoothing_windows = [1, 3, 5, 10]
    min_dwells = [1, 3, 5, 20]
    policies = [TREND_ONLY_POLICY, TREND_BREADTH_POLICY]
    seen = {policy.candidate_id for policy in policies}
    for weights in weight_sets:
        for bull in bull_thresholds:
            for bear in bear_thresholds:
                for smoothing in smoothing_windows:
                    for dwell in min_dwells:
                        candidate_id = f"w{len(seen):04d}"
                        if candidate_id in seen:
                            continue
                        policies.append(
                            RegimePolicy(
                                candidate_id=candidate_id,
                                weights=weights,
                                bull_threshold=bull,
                                bear_threshold=bear,
                                smoothing_window=smoothing,
                                min_dwell=dwell,
                                complexity=(1 if smoothing == 1 else 2) + (1 if dwell == 1 else 2),
                            )
                        )
                        seen.add(candidate_id)
                        if len(policies) >= max_candidates:
                            return policies
    return policies


def stability_stats(regimes: pd.Series) -> dict[str, float]:
    regimes = regimes.dropna()
    if regimes.empty:
        return {"turnovers": 0.0, "avg_dwell": 0.0, "bull_ratio": 0.0, "bear_ratio": 0.0, "sideways_ratio": 0.0}
    changes = regimes.ne(regimes.shift()).sum() - 1
    counts = regimes.value_counts(normalize=True)
    runs = regimes.groupby(regimes.ne(regimes.shift()).cumsum()).size()
    return {
        "turnovers": float(max(changes, 0)),
        "avg_dwell": float(runs.mean()) if len(runs) else 0.0,
        "bull_ratio": float(counts.get("bull", 0.0)),
        "bear_ratio": float(counts.get("bear", 0.0)),
        "sideways_ratio": float(counts.get("sideways", 0.0)),
    }


def walk_forward_splits(index: pd.DatetimeIndex, train_years: int = 4, validate_years: int = 1):
    years = sorted(set(index.year))
    for start in range(0, len(years) - train_years - validate_years + 1):
        train = set(years[start : start + train_years])
        validate = set(years[start + train_years : start + train_years + validate_years])
        train_idx = index[index.year.isin(train)]
        validate_idx = index[index.year.isin(validate)]
        if len(train_idx) and len(validate_idx):
            yield train_idx, validate_idx


def decide_promotion(
    *,
    champion_score: float,
    challenger_score: float,
    challenger_maxdd_delta: float,
    challenger_turnover_delta: float,
    beats_baselines: bool,
    valid_year_win_rate: float,
    regime_diversified: bool = True,
) -> PromotionGateResult:
    if champion_score <= 0 or challenger_score <= 0:
        return PromotionGateResult.INSUFFICIENT_DATA
    if not regime_diversified:
        return PromotionGateResult.KEEP_CHAMPION
    if challenger_score < champion_score + 2.0:
        return PromotionGateResult.KEEP_CHAMPION
    if challenger_maxdd_delta < -0.02:
        return PromotionGateResult.KEEP_CHAMPION
    if challenger_turnover_delta > 0.20:
        return PromotionGateResult.KEEP_CHAMPION
    if valid_year_win_rate < 0.60:
        return PromotionGateResult.KEEP_CHAMPION
    if not beats_baselines:
        return PromotionGateResult.KEEP_CHAMPION
    return PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW


def build_regime_feature_history(
    index_df: pd.DataFrame,
    breadth_history: pd.DataFrame | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Build point-in-time regime features from benchmark and optional breadth history."""
    data = normalize_ohlcv(index_df)
    if data.empty:
        return pd.DataFrame()
    if start:
        data = data[data.index >= pd.Timestamp(start)]
    if end and end != "auto":
        data = data[data.index <= pd.Timestamp(end)]
    if len(data) < 130:
        return pd.DataFrame()

    close = data["close"]
    ret1 = close.pct_change()
    ret20 = close.pct_change(20)
    ret60 = close.pct_change(60)
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()
    ma120 = close.rolling(120, min_periods=120).mean()

    trend_raw = (
        0.25 * (close > ma20).astype(float)
        + 0.25 * (ma20 > ma60).astype(float)
        + 0.20 * (ma60 > ma120).astype(float)
        + 0.15 * (0.5 + (ret20 / 0.12)).map(clamp)
        + 0.15 * (0.5 + (ret60 / 0.25)).map(clamp)
    )

    realized_vol_20d = ret1.rolling(20, min_periods=10).std() * np.sqrt(252)
    rolling_peak = close.rolling(60, min_periods=20).max()
    drawdown_60d = close / rolling_peak - 1.0
    vol_score = 1.0 - ((realized_vol_20d - 0.12) / 0.28).map(clamp)
    drawdown_score = 1.0 - (drawdown_60d.clip(upper=0).abs() / 0.15).map(clamp)
    risk_raw = (0.60 * drawdown_score + 0.40 * vol_score).map(clamp)

    amount = data["amount"].replace(0, np.nan).fillna(data["volume"] * close)
    amount_5d = amount.rolling(5, min_periods=3).mean()
    amount_20d = amount.rolling(20, min_periods=10).mean()
    amount_ratio = (amount_5d / amount_20d).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    index_volume_raw = (0.5 + (amount_ratio - 1.0) * 0.5).map(clamp)

    proxy_advance = ret1.gt(0).rolling(20, min_periods=5).mean().fillna(0.5)
    proxy_above20 = (close > ma20).astype(float).rolling(20, min_periods=5).mean().fillna(0.5)
    proxy_above60 = (close > ma60).astype(float).rolling(60, min_periods=10).mean().fillna(0.5)
    proxy_above120 = (close > ma120).astype(float).rolling(120, min_periods=20).mean().fillna(0.5)

    features = pd.DataFrame(
        {
            "trend_raw": trend_raw,
            "risk_raw": risk_raw,
            "advance_ratio": proxy_advance,
            "above_ma20": proxy_above20,
            "above_ma60": proxy_above60,
            "above_ma120": proxy_above120,
            "sample_size": 0.0,
            "amount_ratio_5_20": amount_ratio,
            "up_amount_ratio": proxy_advance,
            "realized_vol_20d": realized_vol_20d,
            "drawdown_60d": drawdown_60d,
            "volume_raw": index_volume_raw,
        },
        index=data.index,
    )

    if breadth_history is not None and not breadth_history.empty:
        breadth = breadth_history.copy()
        breadth.index = pd.to_datetime(breadth.index)
        breadth = breadth.reindex(features.index).ffill()
        for col in [
            "advance_ratio",
            "above_ma20",
            "above_ma60",
            "above_ma120",
            "sample_size",
            "amount_ratio_5_20",
            "up_amount_ratio",
        ]:
            if col in breadth:
                features[col] = breadth[col].where(breadth[col].notna(), features[col])

    features["breadth_raw"] = [
        breadth_strength(row.advance_ratio, row.above_ma20, row.above_ma60, row.above_ma120)
        for row in features.itertuples()
    ]
    volume_values = []
    for row in features.itertuples():
        value, _trend, _detail = volume_strength(
            amount_ratio_5_20=float(row.amount_ratio_5_20),
            advance_ratio=float(row.advance_ratio),
            up_amount_ratio=float(row.up_amount_ratio),
            index_volume=float(row.volume_raw),
            sample_size=int(row.sample_size),
        )
        volume_values.append(value)
    features["volume_raw"] = volume_values
    features = features.replace([np.inf, -np.inf], np.nan).dropna(subset=["trend_raw", "breadth_raw", "risk_raw", "volume_raw"])
    return features


def load_full_market_breadth_history(
    *,
    start: str | None = None,
    end: str | None = None,
    daily_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Load historical full-market breadth from local stock daily parquet files."""
    try:
        import duckdb
    except Exception:
        return pd.DataFrame()

    if daily_dir is None:
        from data.datahub import get_datahub

        daily_dir = get_datahub().store_path("stock") / "daily"
    daily_path = Path(daily_dir)
    if not daily_path.exists():
        return pd.DataFrame()

    source_sql = "'" + str(daily_path / "*.parquet").replace("'", "''") + "'"
    warmup_start = pd.Timestamp(start) - pd.Timedelta(days=240) if start else None
    where = ["date is not null", "close is not null"]
    if warmup_start is not None:
        where.append(f"cast(date as date) >= date '{warmup_start.date()}'")
    if end and end != "auto":
        where.append(f"cast(date as date) <= date '{pd.Timestamp(end).date()}'")
    where_sql = " and ".join(where)
    query = f"""
    with rows as (
      select
        filename,
        cast(date as date) as trade_date,
        cast(close as double) as close,
        coalesce(try_cast(amount as double), try_cast(volume as double) * try_cast(close as double)) as amount
      from read_parquet({source_sql}, filename=true, union_by_name=true)
      where {where_sql}
    ), enriched as (
      select
        *,
        lag(close) over(partition by filename order by trade_date) as prev_close,
        avg(close) over(partition by filename order by trade_date rows between 19 preceding and current row) as ma20,
        avg(close) over(partition by filename order by trade_date rows between 59 preceding and current row) as ma60,
        avg(close) over(partition by filename order by trade_date rows between 119 preceding and current row) as ma120,
        count(close) over(partition by filename order by trade_date rows between 19 preceding and current row) as n20,
        count(close) over(partition by filename order by trade_date rows between 59 preceding and current row) as n60,
        count(close) over(partition by filename order by trade_date rows between 119 preceding and current row) as n120
      from rows
    ), daily as (
      select
        trade_date,
        count(*) filter(where prev_close is not null and prev_close > 0) as sample_size,
        count(*) filter(where close > prev_close and prev_close > 0) as up_count,
        count(*) filter(where close < prev_close and prev_close > 0) as down_count,
        count(*) filter(where close = prev_close and prev_close > 0) as unchanged_count,
        count(*) filter(where n20 >= 20 and close > ma20) as above_ma20,
        count(*) filter(where n20 >= 20) as eligible_ma20,
        count(*) filter(where n60 >= 60 and close > ma60) as above_ma60,
        count(*) filter(where n60 >= 60) as eligible_ma60,
        count(*) filter(where n120 >= 120 and close > ma120) as above_ma120,
        count(*) filter(where n120 >= 120) as eligible_ma120,
        sum(amount) filter(where amount is not null and amount > 0) as total_amount,
        sum(amount) filter(where amount is not null and amount > 0 and close > prev_close and prev_close > 0) as up_amount
      from enriched
      group by trade_date
      order by trade_date
    )
    select * from daily
    """
    try:
        df = duckdb.connect(database=":memory:").execute(query).df()
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("date").sort_index()
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    traded = df[["up_count", "down_count", "unchanged_count"]].sum(axis=1)
    out = pd.DataFrame(index=df.index)
    out["sample_size"] = df["sample_size"].astype(float)
    out["advance_ratio"] = (df["up_count"] / traded.replace(0, np.nan)).fillna(0.5)
    out["above_ma20"] = (df["above_ma20"] / df["eligible_ma20"].replace(0, np.nan)).fillna(0.5)
    out["above_ma60"] = (df["above_ma60"] / df["eligible_ma60"].replace(0, np.nan)).fillna(0.5)
    out["above_ma120"] = (df["above_ma120"] / df["eligible_ma120"].replace(0, np.nan)).fillna(0.5)
    total_amount = df["total_amount"].replace(0, np.nan)
    out["amount_ratio_5_20"] = (total_amount.rolling(5, min_periods=3).mean() / total_amount.rolling(20, min_periods=10).mean()).fillna(1.0)
    out["up_amount_ratio"] = (df["up_amount"] / total_amount).fillna(out["advance_ratio"]).fillna(0.5)
    return out


def _group_mean(data: pd.DataFrame, regime: str, column: str) -> float:
    subset = data.loc[data["regime"] == regime, column].dropna()
    return float(subset.mean()) if len(subset) else 0.0


def _safe_corr(left: pd.Series, right: pd.Series) -> float:
    pair = pd.concat([left, right], axis=1).dropna()
    if len(pair) < 10:
        return 0.0
    if pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
        return 0.0
    value = pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman")
    return float(value) if pd.notna(value) else 0.0


def _score_1_100(value: float) -> float:
    if not math.isfinite(value):
        return 1.0
    return max(1.0, min(100.0, value))


def evaluate_policy(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    close: pd.Series,
    policy: RegimePolicy,
) -> dict[str, float | str]:
    applied = apply_policy(features, policy)
    data = applied.join(labels, how="inner")
    stats = stability_stats(data["regime"])
    return20 = "future_20d_return"
    drawdown20 = "future_20d_max_drawdown"

    bull_ret = _group_mean(data, "bull", return20)
    sideways_ret = _group_mean(data, "sideways", return20)
    bear_ret = _group_mean(data, "bear", return20)
    bear_dd = _group_mean(data, "bear", drawdown20)
    nonbear_dd = data.loc[data["regime"] != "bear", drawdown20].dropna().mean()
    nonbear_dd = float(nonbear_dd) if pd.notna(nonbear_dd) else 0.0
    ret_separation = (bull_ret - bear_ret) * 100.0
    order_bonus = 10.0 if bull_ret >= sideways_ret >= bear_ret else 0.0
    risk_separation = max(0.0, (nonbear_dd - bear_dd) * 100.0)
    score_ic = _safe_corr(data["score"], data[return20])
    predictive_score = _score_1_100(50.0 + ret_separation * 3.0 + risk_separation * 2.0 + order_bonus + score_ic * 10.0)

    sim = simulate_regime_allocation(close, data["regime"])
    max_regime_ratio = max(stats["bull_ratio"], stats["bear_ratio"], stats["sideways_ratio"])
    collapse_penalty = max(0.0, max_regime_ratio - 0.85) * 80.0
    composite = (
        0.45 * predictive_score
        + 0.35 * sim["strategy_score"]
        + 0.10 * max(0.0, min(100.0, stats["avg_dwell"]))
        - 0.15 * stats["turnovers"]
        - 1.50 * policy.complexity
        - collapse_penalty
    )
    composite = _score_1_100(composite)
    return {
        "candidate_id": policy.candidate_id,
        "predictive_score": round(float(predictive_score), 4),
        "strategy_score": round(float(sim["strategy_score"]), 4),
        "composite_score": round(float(composite), 4),
        "bull_future_20d_return": round(bull_ret, 6),
        "sideways_future_20d_return": round(sideways_ret, 6),
        "bear_future_20d_return": round(bear_ret, 6),
        "bear_future_20d_drawdown": round(bear_dd, 6),
        "score_ic_20d": round(score_ic, 6),
        "turnovers": round(stats["turnovers"], 4),
        "avg_dwell": round(stats["avg_dwell"], 4),
        "bull_ratio": round(stats["bull_ratio"], 6),
        "bear_ratio": round(stats["bear_ratio"], 6),
        "sideways_ratio": round(stats["sideways_ratio"], 6),
        "max_regime_ratio": round(max_regime_ratio, 6),
        "collapse_penalty": round(collapse_penalty, 4),
        "complexity": float(policy.complexity),
        "cagr": sim["cagr"],
        "sharpe": sim["sharpe"],
        "max_drawdown": sim["max_drawdown"],
        "calmar": sim["calmar"],
        "turnover_proxy": sim["turnover_proxy"],
        "policy": policy,
    }


def rank_candidate_rows(rows: Sequence[dict]) -> list[dict]:
    ranked = []
    for row in rows:
        enriched = dict(row)
        if "composite_score" not in enriched:
            max_regime_ratio = max(
                float(enriched.get("bull_ratio", 0.0)),
                float(enriched.get("bear_ratio", 0.0)),
                float(enriched.get("sideways_ratio", 0.0)),
            )
            collapse_penalty = max(0.0, max_regime_ratio - 0.85) * 80.0
            enriched["composite_score"] = _score_1_100(
                0.45 * float(enriched.get("predictive_score", 0.0))
                + 0.35 * float(enriched.get("strategy_score", 0.0))
                - 0.15 * float(enriched.get("turnovers", 0.0))
                - 1.50 * float(enriched.get("complexity", 1.0))
                - collapse_penalty
            )
        ranked.append(enriched)
    return sorted(ranked, key=lambda r: (float(r.get("composite_score", 0.0)), float(r.get("predictive_score", 0.0))), reverse=True)


def simulate_regime_allocation(close: pd.Series, regimes: pd.Series | None = None, fixed_exposure: float | None = None) -> dict[str, float]:
    close = close.sort_index().astype(float)
    returns = close.pct_change().fillna(0.0)
    if fixed_exposure is not None:
        exposure = pd.Series(float(fixed_exposure), index=returns.index)
    else:
        aligned = regimes.reindex(returns.index).ffill().fillna("sideways") if regimes is not None else pd.Series("sideways", index=returns.index)
        exposure = aligned.map({"bull": 0.60, "sideways": 0.35, "bear": 0.10}).fillna(0.35)
        exposure = exposure.shift(1).fillna(0.35)
    strategy_returns = returns * exposure
    turnover_proxy = float(exposure.diff().abs().sum())
    metrics = portfolio_metrics(strategy_returns, turnover_proxy=turnover_proxy, include_series=False)
    strategy_score = _score_1_100(
        50.0
        + float(metrics["sharpe"]) * 10.0
        + float(metrics["calmar"]) * 3.0
        + float(metrics["max_drawdown"]) * 100.0
        - turnover_proxy * 0.2
    )
    return {
        "cagr": metrics["cagr"],
        "sharpe": metrics["sharpe"],
        "max_drawdown": metrics["max_drawdown"],
        "calmar": metrics["calmar"],
        "turnover_proxy": metrics["turnover_proxy"],
        "strategy_score": round(strategy_score, 4),
    }


def _public_row(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "policy"}


def _policy_by_id(policies: Sequence[RegimePolicy], candidate_id: str) -> RegimePolicy | None:
    for policy in policies:
        if policy.candidate_id == candidate_id:
            return policy
    return None


def _evaluate_many(features: pd.DataFrame, labels: pd.DataFrame, close: pd.Series, policies: Sequence[RegimePolicy]) -> list[dict]:
    return [evaluate_policy(features, labels, close, policy) for policy in policies]


def _walk_forward_rows(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    close: pd.Series,
    policies: Sequence[RegimePolicy],
) -> list[dict]:
    rows = []
    index = pd.DatetimeIndex(features.index)
    for train_idx, validate_idx in walk_forward_splits(index):
        train_features = features.loc[train_idx]
        train_labels = labels.loc[labels.index.intersection(train_idx)]
        train_close = close.loc[close.index.intersection(train_idx)]
        validate_features = features.loc[validate_idx]
        validate_labels = labels.loc[labels.index.intersection(validate_idx)]
        validate_close = close.loc[close.index.intersection(validate_idx)]
        if len(train_features) < 120 or len(validate_features) < 40:
            continue
        train_ranked = rank_candidate_rows(_evaluate_many(train_features, train_labels, train_close, policies))
        best_id = train_ranked[0]["candidate_id"] if train_ranked else ""
        best_policy = _policy_by_id(policies, best_id)
        if best_policy is None:
            continue
        champion = evaluate_policy(validate_features, validate_labels, validate_close, CHAMPION_POLICY)
        challenger = evaluate_policy(validate_features, validate_labels, validate_close, best_policy)
        rows.append(
            {
                "train_start": str(train_idx.min().date()),
                "train_end": str(train_idx.max().date()),
                "validate_start": str(validate_idx.min().date()),
                "validate_end": str(validate_idx.max().date()),
                "selected_candidate": best_id,
                "champion_score": champion["composite_score"],
                "challenger_score": challenger["composite_score"],
                "score_delta": round(float(challenger["composite_score"]) - float(champion["composite_score"]), 4),
                "winner": "challenger" if float(challenger["composite_score"]) > float(champion["composite_score"]) else "champion",
            }
        )
    return rows


def run_regime_research(
    features: pd.DataFrame,
    close: pd.Series,
    *,
    policies: Sequence[RegimePolicy] | None = None,
) -> dict:
    features = features.sort_index()
    close = close.sort_index().reindex(features.index).ffill().dropna()
    features = features.loc[features.index.intersection(close.index)]
    labels = build_forward_labels(close)
    if len(features) < 252:
        return {
            "decision": PromotionGateResult.INSUFFICIENT_DATA.value,
            "champion_score": 0.0,
            "best_challenger_score": 0.0,
            "best_challenger_id": "",
            "candidate_rows": [],
            "walk_forward_rows": [],
            "strategy_rows": [],
            "stability_rows": [],
            "component_rows": [],
            "event_rows": [],
            "notes": ["insufficient_data: need at least 252 feature rows"],
            "features": features,
            "labels": labels,
        }

    candidate_policies = list(policies) if policies is not None else generate_candidate_policies()
    policy_ids = {policy.candidate_id for policy in candidate_policies}
    for baseline in (TREND_ONLY_POLICY, TREND_BREADTH_POLICY):
        if baseline.candidate_id not in policy_ids:
            candidate_policies.insert(0, baseline)
            policy_ids.add(baseline.candidate_id)

    champion = evaluate_policy(features, labels, close, CHAMPION_POLICY)
    candidate_rows_with_policy = rank_candidate_rows(_evaluate_many(features, labels, close, candidate_policies))
    non_baseline = [row for row in candidate_rows_with_policy if row["candidate_id"] not in BASELINE_IDS]
    best = non_baseline[0] if non_baseline else (candidate_rows_with_policy[0] if candidate_rows_with_policy else champion)
    best_policy = best.get("policy", CHAMPION_POLICY)
    best_series = apply_policy(features, best_policy)["regime"] if isinstance(best_policy, RegimePolicy) else apply_policy(features, CHAMPION_POLICY)["regime"]
    champion_series = apply_policy(features, CHAMPION_POLICY)["regime"]
    trend_series = apply_policy(features, TREND_ONLY_POLICY)["regime"]
    trend_breadth_series = apply_policy(features, TREND_BREADTH_POLICY)["regime"]

    fixed = simulate_regime_allocation(close, fixed_exposure=0.35)
    strategy_rows = [
        {"strategy": "no_regime_fixed_allocation", **fixed},
        {"strategy": "champion_current_formula", **simulate_regime_allocation(close, champion_series)},
        {"strategy": "trend_only_baseline", **simulate_regime_allocation(close, trend_series)},
        {"strategy": "trend_breadth_baseline", **simulate_regime_allocation(close, trend_breadth_series)},
        {"strategy": "best_challenger", **simulate_regime_allocation(close, best_series), "candidate_id": best["candidate_id"]},
    ]

    walk_rows = _walk_forward_rows(features, labels, close, candidate_policies)
    valid_year_win_rate = (
        sum(row["winner"] == "challenger" for row in walk_rows) / len(walk_rows)
        if walk_rows
        else 0.0
    )
    baseline_scores = {
        row["strategy"]: float(row.get("strategy_score", 0.0))
        for row in strategy_rows
        if row["strategy"] in {"trend_only_baseline", "trend_breadth_baseline"}
    }
    best_strategy_score = float(strategy_rows[-1].get("strategy_score", 0.0))
    beats_baselines = best_strategy_score >= max(baseline_scores.values(), default=0.0)
    champion_strategy = strategy_rows[1]
    best_strategy = strategy_rows[-1]
    decision = decide_promotion(
        champion_score=float(champion["composite_score"]),
        challenger_score=float(best["composite_score"]),
        challenger_maxdd_delta=float(best_strategy["max_drawdown"]) - float(champion_strategy["max_drawdown"]),
        challenger_turnover_delta=float(best_strategy["turnover_proxy"]) - float(champion_strategy["turnover_proxy"]),
        beats_baselines=beats_baselines,
        valid_year_win_rate=valid_year_win_rate,
        regime_diversified=float(best.get("max_regime_ratio", 1.0)) <= 0.90,
    )

    candidate_rows = [_public_row(row) for row in candidate_rows_with_policy]
    stability_rows = [
        {"candidate_id": row["candidate_id"], **{key: row[key] for key in ("turnovers", "avg_dwell", "bull_ratio", "bear_ratio", "sideways_ratio", "max_regime_ratio")}}
        for row in candidate_rows
    ]
    component_rows = [
        row for row in candidate_rows
        if row["candidate_id"] in {TREND_ONLY_POLICY.candidate_id, TREND_BREADTH_POLICY.candidate_id, best["candidate_id"]}
    ]
    event_rows = _event_study_rows(labels, champion_series, best_series)
    notes = [
        f"rows={len(features)}",
        f"walk_forward_windows={len(walk_rows)}",
        "production_formula_not_applied",
    ]
    return {
        "decision": decision.value,
        "champion_score": round(float(champion["composite_score"]), 4),
        "best_challenger_score": round(float(best["composite_score"]), 4),
        "best_challenger_id": best["candidate_id"],
        "best_policy": best_policy if isinstance(best_policy, RegimePolicy) else None,
        "candidate_rows": candidate_rows,
        "walk_forward_rows": walk_rows,
        "strategy_rows": strategy_rows,
        "stability_rows": stability_rows,
        "component_rows": component_rows,
        "event_rows": event_rows,
        "notes": notes,
        "features": features,
        "labels": labels,
    }


def _event_study_rows(labels: pd.DataFrame, champion: pd.Series, challenger: pd.Series) -> list[dict]:
    rows = []
    for name, regimes in [("champion_current_formula", champion), ("best_challenger", challenger)]:
        data = labels.join(regimes.rename("regime"), how="inner")
        for regime in ("bull", "sideways", "bear"):
            subset = data[data["regime"] == regime]
            rows.append(
                {
                    "policy": name,
                    "regime": regime,
                    "observations": int(len(subset)),
                    "future_20d_return": round(float(subset["future_20d_return"].mean()), 6) if "future_20d_return" in subset else 0.0,
                    "future_20d_max_drawdown": round(float(subset["future_20d_max_drawdown"].mean()), 6) if "future_20d_max_drawdown" in subset else 0.0,
                }
            )
    return rows


def _csv(path: Path, rows: Sequence[dict]) -> None:
    pd.DataFrame(list(rows)).to_csv(path, index=False)


def _to_jsonable(value):
    if isinstance(value, RegimePolicy):
        return asdict(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _recommended_config(policy: RegimePolicy | None) -> str:
    if policy is None:
        return "decision: keep_champion\nrecommended_config: null\n"
    weights = "\n".join(f"    {key}: {value}" for key, value in policy.weights.items())
    return (
        "decision: recommend_challenger_for_review\n"
        "recommended_config:\n"
        f"  candidate_id: {policy.candidate_id}\n"
        "  weights:\n"
        f"{weights}\n"
        f"  bull_threshold: {policy.bull_threshold}\n"
        f"  bear_threshold: {policy.bear_threshold}\n"
        f"  trend_confirm: {policy.trend_confirm}\n"
        f"  breadth_confirm: {policy.breadth_confirm}\n"
        f"  bear_trend_breakdown: {policy.bear_trend_breakdown}\n"
        f"  bear_breadth_breakdown: {policy.bear_breadth_breakdown}\n"
        f"  smoothing_window: {policy.smoothing_window}\n"
        f"  min_dwell: {policy.min_dwell}\n"
        "  apply: false\n"
    )


def write_regime_training_report(output_dir: str | Path, result: dict) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    candidate_rows = result.get("candidate_rows", [])
    walk_rows = result.get("walk_forward_rows", [])
    strategy_rows = result.get("strategy_rows", [])
    stability_rows = result.get("stability_rows", [])
    component_rows = result.get("component_rows", [])
    event_rows = result.get("event_rows", [])

    _csv(output / "candidate_search.csv", candidate_rows)
    _csv(output / "walk_forward_results.csv", walk_rows)
    _csv(output / "strategy_ab_test.csv", strategy_rows)
    _csv(output / "stability_stats.csv", stability_rows)
    _csv(output / "component_ablation.csv", component_rows)
    _csv(output / "event_study.csv", event_rows)

    features = result.get("features")
    labels = result.get("labels")
    if isinstance(features, pd.DataFrame) and not features.empty:
        features.to_parquet(output / "regime_feature_history.parquet")
    if isinstance(labels, pd.DataFrame) and not labels.empty:
        labels.to_parquet(output / "regime_label_history.parquet")

    best_policy = result.get("best_policy")
    if result.get("decision") == PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW.value and isinstance(best_policy, RegimePolicy):
        recommended = _recommended_config(best_policy)
    else:
        recommended = _recommended_config(None)
    (output / "recommended_config.yaml").write_text(recommended, encoding="utf-8")

    markdown = _champion_markdown(result)
    (output / "champion_vs_challenger.md").write_text(markdown, encoding="utf-8")

    report_files = [
        "summary.json",
        "champion_vs_challenger.md",
        "candidate_search.csv",
        "walk_forward_results.csv",
        "component_ablation.csv",
        "strategy_ab_test.csv",
        "stability_stats.csv",
        "event_study.csv",
        "recommended_config.yaml",
    ]
    if (output / "regime_feature_history.parquet").exists():
        report_files.append("regime_feature_history.parquet")
    if (output / "regime_label_history.parquet").exists():
        report_files.append("regime_label_history.parquet")

    summary = {
        "status": "ok",
        "decision": str(result.get("decision", PromotionGateResult.KEEP_CHAMPION.value)),
        "champion_score": float(result.get("champion_score", 0.0)),
        "best_challenger_score": float(result.get("best_challenger_score", 0.0)),
        "best_challenger_id": str(result.get("best_challenger_id", "")),
        "report_files": report_files,
        "notes": list(result.get("notes", [])),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_to_jsonable), encoding="utf-8")
    return summary


def _champion_markdown(result: dict) -> str:
    decision = result.get("decision", PromotionGateResult.KEEP_CHAMPION.value)
    lines = [
        "# Market Regime Champion vs Challenger",
        "",
        f"- Decision: `{decision}`",
        f"- Champion score: `{float(result.get('champion_score', 0.0)):.4f}`",
        f"- Best challenger: `{result.get('best_challenger_id', '')}`",
        f"- Best challenger score: `{float(result.get('best_challenger_score', 0.0)):.4f}`",
        "- Production formula applied: `false`",
        "",
        "## Notes",
    ]
    for note in result.get("notes", []):
        lines.append(f"- {note}")
    lines.extend(["", "## Strategy A/B"])
    for row in result.get("strategy_rows", []):
        lines.append(
            f"- `{row.get('strategy')}`: Sharpe={float(row.get('sharpe', 0.0)):.2f}, "
            f"MaxDD={float(row.get('max_drawdown', 0.0)):.2%}, "
            f"Calmar={float(row.get('calmar', 0.0)):.2f}, "
            f"TurnoverProxy={float(row.get('turnover_proxy', 0.0)):.2f}"
        )
    return "\n".join(lines) + "\n"


def run_and_write_report(
    *,
    index_df: pd.DataFrame,
    output_dir: str | Path,
    start: str | None = None,
    end: str | None = None,
    max_candidates: int = 500,
    breadth_history: pd.DataFrame | None = None,
) -> dict:
    features = build_regime_feature_history(index_df, breadth_history, start=start, end=end)
    close = normalize_ohlcv(index_df)["close"]
    if start:
        close = close[close.index >= pd.Timestamp(start)]
    if end and end != "auto":
        close = close[close.index <= pd.Timestamp(end)]
    policies = generate_candidate_policies(max_candidates=max_candidates)
    result = run_regime_research(features, close, policies=policies)
    return write_regime_training_report(output_dir, result)


def build_tradable_asset_panel(
    equity_df: pd.DataFrame,
    defensive_df: pd.DataFrame | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    equity_source: str = "equity",
    defensive_source: str | None = None,
) -> pd.DataFrame:
    """Build a local tradable asset panel for profit-oriented regime research."""
    equity = normalize_ohlcv(equity_df)
    if start:
        equity = equity[equity.index >= pd.Timestamp(start)]
    if end and end != "auto":
        equity = equity[equity.index <= pd.Timestamp(end)]
    if equity.empty:
        panel = pd.DataFrame(columns=["equity_close", "equity_return", "cash_return", "defensive_return"])
        panel.attrs["asset_sources"] = {"equity": equity_source, "defensive": "cash_fallback", "cash": "zero_cash"}
        panel.attrs["notes"] = ["insufficient_data: equity proxy unavailable", "defensive_unavailable"]
        return panel

    panel = pd.DataFrame(index=equity.index)
    panel["equity_close"] = equity["close"].astype(float)
    panel["equity_return"] = panel["equity_close"].pct_change().fillna(0.0)
    panel["cash_return"] = 0.0
    notes: list[str] = []

    if defensive_df is not None and not defensive_df.empty:
        defensive = normalize_ohlcv(defensive_df)
        defensive_return = defensive["close"].astype(float).pct_change().reindex(panel.index).ffill().fillna(0.0)
        panel["defensive_return"] = defensive_return
        defensive_name = defensive_source or "defensive_proxy"
    else:
        panel["defensive_return"] = panel["cash_return"]
        defensive_name = "cash_fallback"
        notes.append("defensive_unavailable")

    panel = panel.replace([np.inf, -np.inf], np.nan).dropna(subset=["equity_close"])
    panel.attrs["asset_sources"] = {"equity": equity_source, "defensive": defensive_name, "cash": "zero_cash"}
    panel.attrs["notes"] = notes
    return panel[["equity_close", "equity_return", "cash_return", "defensive_return"]]


def _read_local_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def load_local_equity_ohlcv(symbol: str = "sh000001", *, data_root: str | Path = ".") -> tuple[pd.DataFrame, str, list[str]]:
    """Load a broad equity proxy from local cache/parquet without network fetches."""
    notes: list[str] = []
    if symbol.startswith(("sh", "sz")):
        try:
            from data.fetcher import _read_cache

            cached = _read_cache(f"index_daily_{symbol}_default", max_age_hours=0)
            if cached is not None and len(cached) > 0:
                return cached, f"local_cache:{symbol}", notes
        except Exception as exc:
            notes.append(f"index_cache_unavailable:{type(exc).__name__}")

    root = Path(data_root)
    fallbacks = [
        (root / "data/store/fund/daily/510300.SH.parquet", "fund_daily:510300.SH"),
        (root / "data/store/fund/daily/510500.SH.parquet", "fund_daily:510500.SH"),
        (root / "data/store/fund/daily/510050.SH.parquet", "fund_daily:510050.SH"),
    ]
    for path, source in fallbacks:
        frame = _read_local_parquet(path)
        if not frame.empty:
            notes.append(f"equity_symbol_{symbol}_not_found_used_{source}")
            return frame, source, notes
    notes.append(f"equity_proxy_unavailable:{symbol}")
    return pd.DataFrame(), "", notes


def _load_treasury_defensive_proxy(*, data_root: str | Path = ".") -> tuple[pd.DataFrame, str, list[str]]:
    path = Path(data_root) / "data/store/bond/treasury_yields.parquet"
    frame = _read_local_parquet(path)
    if frame.empty or "中国国债收益率10年" not in frame.columns:
        return pd.DataFrame(), "", ["bond_proxy_unavailable"]
    data = frame.copy()
    if "date" in data.columns:
        dates = pd.to_datetime(data["date"], errors="coerce")
    elif "日期" in data.columns:
        dates = pd.to_datetime(data["日期"], errors="coerce")
    else:
        dates = pd.to_datetime(data.index, errors="coerce")
    yld = pd.to_numeric(data["中国国债收益率10年"], errors="coerce")
    proxy = pd.DataFrame({"date": pd.Series(dates).to_numpy(), "yield": pd.Series(yld).to_numpy()}).dropna().sort_values("date")
    if proxy.empty:
        return pd.DataFrame(), "", ["bond_proxy_unavailable"]
    rate = proxy["yield"] / 100.0
    duration = 7.0
    daily_return = (rate.shift(1).fillna(rate) / 252.0) - duration * rate.diff().fillna(0.0)
    daily_return = daily_return.clip(-0.03, 0.03).fillna(0.0)
    close = (1.0 + daily_return).cumprod() * 100.0
    return pd.DataFrame({"date": proxy["date"], "close": close}), "cn_10y_treasury_proxy", []


def load_tradable_asset_panel(
    start: str | None = None,
    end: str | None = "auto",
    *,
    symbol: str = "sh000001",
    data_root: str | Path = ".",
) -> pd.DataFrame:
    """Load the best local tradable panel available; never fetches network data."""
    equity_df, equity_source, equity_notes = load_local_equity_ohlcv(symbol, data_root=data_root)
    defensive_df, defensive_source, defensive_notes = _load_treasury_defensive_proxy(data_root=data_root)
    panel = build_tradable_asset_panel(
        equity_df,
        defensive_df if not defensive_df.empty else None,
        start=start,
        end=end,
        equity_source=equity_source or symbol,
        defensive_source=defensive_source or None,
    )
    panel.attrs["notes"] = list(panel.attrs.get("notes", [])) + equity_notes + defensive_notes
    return panel


def build_profit_labels(asset_panel: pd.DataFrame, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    """Build forward money-making labels from tradable assets only."""
    return _shared_build_profit_labels(asset_panel, horizons)


def _profit_regime_series(regimes: pd.Series) -> pd.Series:
    mapping = {"bull": "risk_on", "sideways": "neutral", "bear": "risk_off"}
    return regimes.map(lambda value: mapping.get(str(value), str(value)))


def simulate_tradable_exposure(
    asset_panel: pd.DataFrame,
    regime_series: pd.Series,
    exposure_map: dict[str, dict[str, float]] | None = None,
) -> dict[str, float | pd.Series]:
    """Convert risk-on/neutral/risk-off states into tradable daily returns."""
    exposure_map = exposure_map or DEFAULT_EXPOSURE_MAP
    panel = asset_panel.sort_index().copy()
    regimes = _profit_regime_series(regime_series).reindex(panel.index).ffill().fillna("neutral")
    equity_weight = regimes.map(lambda regime: exposure_map.get(str(regime), exposure_map["neutral"])["equity"]).astype(float)
    defensive_weight = regimes.map(lambda regime: exposure_map.get(str(regime), exposure_map["neutral"])["defensive"]).astype(float)

    tradable_equity = equity_weight.shift(1).fillna(exposure_map["neutral"]["equity"])
    tradable_defensive = defensive_weight.shift(1).fillna(exposure_map["neutral"]["defensive"])
    daily_return = tradable_equity * panel["equity_return"].astype(float) + tradable_defensive * panel["defensive_return"].astype(float)
    metrics = portfolio_metrics(daily_return)
    stats = regimes.value_counts(normalize=True)
    metrics.update(
        {
            "turnover_proxy": round(float(equity_weight.diff().abs().sum()), 6),
            "risk_on_ratio": round(float(stats.get("risk_on", 0.0)), 6),
            "neutral_ratio": round(float(stats.get("neutral", 0.0)), 6),
            "risk_off_ratio": round(float(stats.get("risk_off", 0.0)), 6),
        }
    )
    return metrics


def _scalar_metrics(metrics: dict) -> dict:
    return {key: value for key, value in metrics.items() if not isinstance(value, pd.Series)}


def _max_single_profit_regime(metrics: dict) -> float:
    return max(
        float(metrics.get("risk_on_ratio", 0.0)),
        float(metrics.get("neutral_ratio", 0.0)),
        float(metrics.get("risk_off_ratio", 0.0)),
    )


def profit_score_candidate(
    metrics: dict,
    baselines: Sequence[dict] | None = None,
    regime_distribution: dict[str, float] | None = None,
    *,
    complexity: int = 1,
) -> dict[str, float]:
    """Score a candidate by tradable OOS-style portfolio quality."""
    baselines = list(baselines or [])
    regime_distribution = regime_distribution or {
        "risk_on_ratio": float(metrics.get("risk_on_ratio", 0.0)),
        "neutral_ratio": float(metrics.get("neutral_ratio", 0.0)),
        "risk_off_ratio": float(metrics.get("risk_off_ratio", 0.0)),
    }
    calmar = float(metrics.get("calmar", 0.0))
    sharpe = float(metrics.get("sharpe", 0.0))
    cagr = float(metrics.get("cagr", 0.0))
    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    turnover = float(metrics.get("turnover_proxy", 0.0))
    max_single = max(float(regime_distribution.get(key, 0.0)) for key in ("risk_on_ratio", "neutral_ratio", "risk_off_ratio"))
    collapse_penalty = max(0.0, max_single - 0.85) * 120.0
    collapse_penalty += max(0.0, 0.10 - float(regime_distribution.get("risk_on_ratio", 0.0))) * 100.0
    collapse_penalty += max(0.0, float(regime_distribution.get("risk_off_ratio", 0.0)) - 0.70) * 100.0

    baseline_bonus = 0.0
    for row in baselines:
        if calmar > float(row.get("calmar", 0.0)):
            baseline_bonus += 2.0
        if sharpe > float(row.get("sharpe", 0.0)):
            baseline_bonus += 1.0
    raw = (
        50.0
        + calmar * 8.0
        + sharpe * 10.0
        + cagr * 120.0
        + max_drawdown * 80.0
        + baseline_bonus
        - turnover * 0.15
        - complexity * 1.25
        - collapse_penalty
    )
    score = _score_1_100(raw)
    return {
        "profit_score": round(score, 4),
        "collapse_penalty": round(float(collapse_penalty), 4),
        "baseline_bonus": round(float(baseline_bonus), 4),
    }


def _fixed_allocation_metrics(asset_panel: pd.DataFrame, equity_weight: float) -> dict:
    panel = asset_panel.sort_index()
    daily = equity_weight * panel["equity_return"].astype(float) + (1.0 - equity_weight) * panel["defensive_return"].astype(float)
    metrics = portfolio_metrics(daily)
    metrics["turnover_proxy"] = 0.0
    metrics["risk_on_ratio"] = 1.0 if equity_weight >= 0.8 else 0.0
    metrics["neutral_ratio"] = 1.0 if 0.2 < equity_weight < 0.8 else 0.0
    metrics["risk_off_ratio"] = 1.0 if equity_weight <= 0.2 else 0.0
    return metrics


def _ma_timing_regime(asset_panel: pd.DataFrame, fast: int, slow: int) -> pd.Series:
    close = asset_panel["equity_close"].astype(float)
    ma_fast = close.rolling(fast, min_periods=max(5, fast // 2)).mean()
    ma_slow = close.rolling(slow, min_periods=max(10, slow // 2)).mean()
    values = []
    for idx in close.index:
        if pd.notna(ma_fast.loc[idx]) and pd.notna(ma_slow.loc[idx]) and close.loc[idx] > ma_fast.loc[idx] > ma_slow.loc[idx]:
            values.append("risk_on")
        elif pd.notna(ma_slow.loc[idx]) and close.loc[idx] < ma_slow.loc[idx]:
            values.append("risk_off")
        else:
            values.append("neutral")
    return pd.Series(values, index=close.index)


def _policy_profit_metrics(features: pd.DataFrame, asset_panel: pd.DataFrame, policy: RegimePolicy) -> dict:
    applied = apply_policy(features, policy)
    regimes = _profit_regime_series(applied["regime"])
    metrics = simulate_tradable_exposure(asset_panel, regimes, DEFAULT_EXPOSURE_MAP)
    score = profit_score_candidate(metrics, complexity=policy.complexity)
    out = {**_scalar_metrics(metrics), **score}
    out["candidate_id"] = policy.candidate_id
    out["policy"] = policy
    return out


def _profit_candidate_rows(features: pd.DataFrame, asset_panel: pd.DataFrame, policies: Sequence[RegimePolicy]) -> list[dict]:
    rows = [_policy_profit_metrics(features, asset_panel, policy) for policy in policies]
    return sorted(rows, key=lambda row: (float(row.get("profit_score", 0.0)), float(row.get("calmar", 0.0))), reverse=True)


def _baseline_row(strategy: str, metrics: dict, candidate_id: str | None = None) -> dict:
    row = {"strategy": strategy, **_scalar_metrics(metrics)}
    if candidate_id:
        row["candidate_id"] = candidate_id
    score = profit_score_candidate(row, complexity=1)
    row.update(score)
    return row


def build_profit_baseline_rows(features: pd.DataFrame, asset_panel: pd.DataFrame, best_policy: RegimePolicy) -> list[dict]:
    """Return strong profit baselines and current/best regime A/B rows."""
    rows = [
        _baseline_row("buy_and_hold_equity", _fixed_allocation_metrics(asset_panel, 1.0)),
        _baseline_row("fixed_80_20", _fixed_allocation_metrics(asset_panel, 0.80)),
        _baseline_row("fixed_60_40", _fixed_allocation_metrics(asset_panel, 0.60)),
        _baseline_row("fixed_40_60", _fixed_allocation_metrics(asset_panel, 0.40)),
        _baseline_row("cash_only", _fixed_allocation_metrics(asset_panel, 0.0)),
        _baseline_row("ma_20_60_timing", simulate_tradable_exposure(asset_panel, _ma_timing_regime(asset_panel, 20, 60), DEFAULT_EXPOSURE_MAP)),
        _baseline_row("ma_60_120_timing", simulate_tradable_exposure(asset_panel, _ma_timing_regime(asset_panel, 60, 120), DEFAULT_EXPOSURE_MAP)),
        _baseline_row(
            "trend_only_regime",
            simulate_tradable_exposure(asset_panel, _profit_regime_series(apply_policy(features, TREND_ONLY_POLICY)["regime"]), DEFAULT_EXPOSURE_MAP),
            TREND_ONLY_POLICY.candidate_id,
        ),
        _baseline_row(
            "trend_breadth_regime",
            simulate_tradable_exposure(asset_panel, _profit_regime_series(apply_policy(features, TREND_BREADTH_POLICY)["regime"]), DEFAULT_EXPOSURE_MAP),
            TREND_BREADTH_POLICY.candidate_id,
        ),
        _baseline_row(
            "current_champion_formula",
            simulate_tradable_exposure(asset_panel, _profit_regime_series(apply_policy(features, CHAMPION_POLICY)["regime"]), DEFAULT_EXPOSURE_MAP),
            CHAMPION_POLICY.candidate_id,
        ),
        _baseline_row(
            "best_challenger",
            simulate_tradable_exposure(asset_panel, _profit_regime_series(apply_policy(features, best_policy)["regime"]), DEFAULT_EXPOSURE_MAP),
            best_policy.candidate_id,
        ),
    ]
    by_name = {row["strategy"]: row for row in rows}
    return [by_name[name] for name in PROFIT_BASELINE_NAMES if name in by_name]


def _profit_walk_forward_rows(
    features: pd.DataFrame,
    asset_panel: pd.DataFrame,
    policies: Sequence[RegimePolicy],
) -> list[dict]:
    rows: list[dict] = []
    index = pd.DatetimeIndex(features.index)
    for train_idx, validate_idx in walk_forward_splits(index):
        train_features = features.loc[train_idx]
        train_panel = asset_panel.loc[asset_panel.index.intersection(train_idx)]
        validate_features = features.loc[validate_idx]
        validate_panel = asset_panel.loc[asset_panel.index.intersection(validate_idx)]
        if len(train_features) < 252 or len(validate_features) < 60 or len(train_panel) < 252 or len(validate_panel) < 60:
            continue
        ranked = _profit_candidate_rows(train_features, train_panel, policies)
        ranked = [row for row in ranked if row["candidate_id"] not in BASELINE_IDS]
        if not ranked:
            continue
        selected_policy = ranked[0]["policy"]
        champion = _policy_profit_metrics(validate_features, validate_panel, CHAMPION_POLICY)
        challenger = _policy_profit_metrics(validate_features, validate_panel, selected_policy)
        rows.append(
            {
                "train_start": str(train_idx.min().date()),
                "train_end": str(train_idx.max().date()),
                "validate_start": str(validate_idx.min().date()),
                "validate_end": str(validate_idx.max().date()),
                "selected_candidate": selected_policy.candidate_id,
                "champion_profit_score": champion["profit_score"],
                "challenger_profit_score": challenger["profit_score"],
                "profit_score_delta": round(float(challenger["profit_score"]) - float(champion["profit_score"]), 4),
                "champion_calmar": champion["calmar"],
                "challenger_calmar": challenger["calmar"],
                "champion_sharpe": champion["sharpe"],
                "challenger_sharpe": challenger["sharpe"],
                "champion_cagr": champion["cagr"],
                "challenger_cagr": challenger["cagr"],
                "winner": "challenger" if float(challenger["profit_score"]) > float(champion["profit_score"]) else "champion",
            }
        )
    return rows


def _beats_required_profit_baselines(challenger_metrics: dict, baseline_rows: Sequence[dict]) -> bool:
    by_name = {row.get("strategy"): row for row in baseline_rows}
    for name in PROFIT_REQUIRED_BASELINES:
        baseline = by_name.get(name)
        if not baseline:
            return False
        challenger_calmar = float(challenger_metrics.get("calmar", 0.0))
        challenger_sharpe = float(challenger_metrics.get("sharpe", 0.0))
        challenger_cagr = float(challenger_metrics.get("cagr", 0.0))
        baseline_calmar = float(baseline.get("calmar", 0.0))
        baseline_sharpe = float(baseline.get("sharpe", 0.0))
        baseline_cagr = float(baseline.get("cagr", 0.0))
        if challenger_calmar <= baseline_calmar and challenger_sharpe <= baseline_sharpe:
            return False
        if challenger_cagr < baseline_cagr - 0.02:
            return False
    return True


def _as_reason_text(values: Sequence[str]) -> str:
    return "|".join(values)


def _finite_metric_set(row: dict, keys: Sequence[str]) -> bool:
    for key in keys:
        try:
            value = float(row.get(key, 0.0))
        except (TypeError, ValueError):
            return False
        if not math.isfinite(value):
            return False
    return True


def _validation_summary_by_id(validation_rows: Sequence[dict]) -> dict[str, dict]:
    return {str(row.get("candidate_id", "")): dict(row) for row in validation_rows}


def build_profit_gate_diagnostics(
    candidate_rows: Sequence[dict],
    champion_metrics: dict,
    baseline_rows: Sequence[dict],
    validation_summary_rows: Sequence[dict] | None = None,
    *,
    min_oos_windows: int = 3,
    min_oos_win_rate: float = 0.50,
    max_single_regime_ratio: float = 0.90,
    max_risk_off_ratio: float = 0.85,
    min_abs_risk_on_ratio: float = 0.01,
) -> list[dict]:
    """Evaluate champion and candidate formulas under the same V3 diagnostics."""
    validation_by_id = _validation_summary_by_id(validation_summary_rows or [])
    champion_turnover = float(champion_metrics.get("turnover_proxy", 0.0))
    turnover_limit = max(80.0, champion_turnover * 1.25)
    champion_risk_on = float(champion_metrics.get("risk_on_ratio", 0.0))
    rows: list[dict] = []

    for row in candidate_rows:
        candidate_id = str(row.get("candidate_id", ""))
        role = "champion" if candidate_id == CHAMPION_POLICY.candidate_id else "candidate"
        failed: list[str] = []
        warnings: list[str] = []
        metrics_finite = _finite_metric_set(row, ["cagr", "sharpe", "calmar", "max_drawdown", "turnover_proxy"])
        if not metrics_finite:
            failed.append("nonfinite_metrics")

        risk_on = float(row.get("risk_on_ratio", 0.0))
        neutral = float(row.get("neutral_ratio", 0.0))
        risk_off = float(row.get("risk_off_ratio", 0.0))
        max_single = max(risk_on, neutral, risk_off)
        turnover = float(row.get("turnover_proxy", 0.0))

        if max_single > max_single_regime_ratio:
            failed.append("permanent_regime_collapse")
        if risk_on <= min_abs_risk_on_ratio:
            failed.append("no_risk_on_participation")
        elif champion_risk_on > 0 and risk_on < champion_risk_on * 0.50:
            warnings.append("low_risk_on_participation")
        if risk_off > max_risk_off_ratio:
            failed.append("excessive_risk_off_dominance")
        if role != "champion" and turnover > turnover_limit:
            failed.append("excessive_turnover_vs_champion")

        if role != "champion" and not _beats_required_profit_baselines(row, baseline_rows):
            failed.append("fails_required_baselines")

        validation = validation_by_id.get(candidate_id, {})
        oos_windows = int(validation.get("oos_windows", 0))
        oos_win_rate = float(validation.get("oos_win_rate_vs_champion", 0.0))
        oos_delta = float(validation.get("oos_profit_score_delta_mean", 0.0))
        if role != "champion":
            if oos_windows < min_oos_windows:
                failed.append("insufficient_oos_evidence")
            if oos_windows >= min_oos_windows and oos_win_rate < min_oos_win_rate and oos_delta <= 0:
                failed.append("weak_oos_vs_champion")

        rows.append(
            {
                "candidate_id": candidate_id,
                "role": role,
                "passes_validation": len(failed) == 0,
                "failed_gates": _as_reason_text(failed),
                "warnings": _as_reason_text(warnings),
                "turnover_limit": round(turnover_limit, 6),
                "risk_on_ratio": round(risk_on, 6),
                "neutral_ratio": round(neutral, 6),
                "risk_off_ratio": round(risk_off, 6),
                "max_single_regime_ratio": round(max_single, 6),
                "oos_windows": oos_windows,
                "oos_win_rate_vs_champion": round(oos_win_rate, 6),
                "oos_profit_score_delta_mean": round(oos_delta, 6),
            }
        )
    return rows


def select_best_validated_formula(
    candidate_rows: Sequence[dict],
    gate_rows: Sequence[dict],
    validation_summary_rows: Sequence[dict] | None = None,
) -> dict:
    """Select the highest ranked formula that passed V3 validation gates."""
    gate_by_id = {str(row.get("candidate_id", "")): row for row in gate_rows}
    validation_by_id = _validation_summary_by_id(validation_summary_rows or [])

    def sort_key(row: dict) -> tuple[float, float, float, float, float]:
        candidate_id = str(row.get("candidate_id", ""))
        validation = validation_by_id.get(candidate_id, {})
        return (
            float(validation.get("oos_profit_score_delta_mean", 0.0)),
            float(validation.get("oos_calmar_mean", 0.0)),
            float(validation.get("oos_sharpe_mean", 0.0)),
            float(row.get("profit_score", 0.0)),
            float(row.get("calmar", 0.0)),
        )

    ranked = sorted(
        [dict(row) for row in candidate_rows],
        key=sort_key if validation_by_id else lambda row: (float(row.get("profit_score", 0.0)), float(row.get("calmar", 0.0)), float(row.get("sharpe", 0.0))),
        reverse=True,
    )
    for row in ranked:
        gate = gate_by_id.get(str(row.get("candidate_id", "")), {})
        if bool(gate.get("passes_validation", False)):
            return row
    return {}


def _profit_candidate_validation_summary_rows(
    features: pd.DataFrame,
    asset_panel: pd.DataFrame,
    policies: Sequence[RegimePolicy],
) -> list[dict]:
    """Evaluate every formula across validation windows against the champion."""
    rows: list[dict] = []
    index = pd.DatetimeIndex(features.index)
    for _train_idx, validate_idx in walk_forward_splits(index):
        validate_features = features.loc[validate_idx]
        validate_panel = asset_panel.loc[asset_panel.index.intersection(validate_idx)]
        if len(validate_features) < 60 or len(validate_panel) < 60:
            continue
        champion = _policy_profit_metrics(validate_features, validate_panel, CHAMPION_POLICY)
        for policy in policies:
            metrics = _policy_profit_metrics(validate_features, validate_panel, policy)
            rows.append(
                {
                    "candidate_id": policy.candidate_id,
                    "oos_window_start": str(validate_idx.min().date()),
                    "oos_window_end": str(validate_idx.max().date()),
                    "oos_profit_score": metrics["profit_score"],
                    "oos_profit_score_delta": round(float(metrics["profit_score"]) - float(champion["profit_score"]), 6),
                    "oos_calmar": metrics["calmar"],
                    "oos_sharpe": metrics["sharpe"],
                    "oos_cagr": metrics["cagr"],
                    "oos_max_drawdown": metrics["max_drawdown"],
                    "winner_vs_champion": "candidate" if float(metrics["profit_score"]) > float(champion["profit_score"]) else "champion",
                }
            )

    if not rows:
        return []
    frame = pd.DataFrame(rows)
    summary = []
    for candidate_id, group in frame.groupby("candidate_id", sort=False):
        summary.append(
            {
                "candidate_id": str(candidate_id),
                "oos_windows": int(len(group)),
                "oos_win_rate_vs_champion": round(float((group["winner_vs_champion"] == "candidate").mean()), 6),
                "oos_profit_score_mean": round(float(group["oos_profit_score"].mean()), 6),
                "oos_profit_score_delta_mean": round(float(group["oos_profit_score_delta"].mean()), 6),
                "oos_calmar_mean": round(float(group["oos_calmar"].mean()), 6),
                "oos_sharpe_mean": round(float(group["oos_sharpe"].mean()), 6),
                "oos_cagr_mean": round(float(group["oos_cagr"].mean()), 6),
                "oos_max_drawdown_mean": round(float(group["oos_max_drawdown"].mean()), 6),
            }
        )
    return sorted(summary, key=lambda row: (float(row["oos_profit_score_delta_mean"]), float(row["oos_calmar_mean"])), reverse=True)


def _profit_decision_v3(best_validated: dict, champion_metrics: dict, walk_rows: Sequence[dict]) -> tuple[PromotionGateResult, str]:
    if not walk_rows:
        return PromotionGateResult.INSUFFICIENT_DATA, "insufficient_oos_windows"
    if not best_validated:
        return PromotionGateResult.KEEP_CHAMPION, "no_validated_formula_keep_current_temporarily"
    if str(best_validated.get("candidate_id")) == CHAMPION_POLICY.candidate_id:
        return PromotionGateResult.KEEP_CHAMPION, "champion_is_best_validated_formula"
    calmar_delta = float(best_validated.get("calmar", 0.0)) - float(champion_metrics.get("calmar", 0.0))
    sharpe_delta = float(best_validated.get("sharpe", 0.0)) - float(champion_metrics.get("sharpe", 0.0))
    cagr_delta = float(best_validated.get("cagr", 0.0)) - float(champion_metrics.get("cagr", 0.0))
    maxdd_delta = float(best_validated.get("max_drawdown", 0.0)) - float(champion_metrics.get("max_drawdown", 0.0))
    if calmar_delta >= 0.05 and sharpe_delta >= 0.02 and cagr_delta >= -0.005 and maxdd_delta >= -0.02:
        return PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW, "validated_challenger_beats_champion"
    return PromotionGateResult.KEEP_CHAMPION, "validated_candidate_does_not_clear_replacement_margin"


def decide_profit_promotion(
    *,
    champion_metrics: dict,
    challenger_metrics: dict,
    baseline_rows: Sequence[dict],
    walk_forward_rows: Sequence[dict],
    min_risk_on_ratio: float = 0.10,
    max_risk_off_ratio: float = 0.70,
    max_single_regime_ratio: float = 0.85,
    max_turnover_proxy: float = 80.0,
    min_validation_win_rate: float = 0.60,
) -> PromotionGateResult:
    if not walk_forward_rows:
        return PromotionGateResult.INSUFFICIENT_DATA
    if float(challenger_metrics.get("risk_on_ratio", 0.0)) < min_risk_on_ratio:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("risk_off_ratio", 0.0)) > max_risk_off_ratio:
        return PromotionGateResult.KEEP_CHAMPION
    if _max_single_profit_regime(challenger_metrics) > max_single_regime_ratio:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("turnover_proxy", 0.0)) > max_turnover_proxy:
        return PromotionGateResult.KEEP_CHAMPION
    wins = sum(row.get("winner") == "challenger" for row in walk_forward_rows)
    win_rate = wins / len(walk_forward_rows)
    if win_rate < min_validation_win_rate:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("calmar", 0.0)) <= float(champion_metrics.get("calmar", 0.0)) + 0.05:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("sharpe", 0.0)) <= float(champion_metrics.get("sharpe", 0.0)) + 0.02:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("cagr", 0.0)) < float(champion_metrics.get("cagr", 0.0)) - 0.01:
        return PromotionGateResult.KEEP_CHAMPION
    if float(challenger_metrics.get("max_drawdown", 0.0)) < float(champion_metrics.get("max_drawdown", 0.0)) - 0.02:
        return PromotionGateResult.KEEP_CHAMPION
    if not _beats_required_profit_baselines(challenger_metrics, baseline_rows):
        return PromotionGateResult.KEEP_CHAMPION
    return PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW


def _select_oos_best_policy(walk_rows: Sequence[dict], policies: Sequence[RegimePolicy], fallback: RegimePolicy) -> RegimePolicy:
    if not walk_rows:
        return fallback
    scores = pd.DataFrame(list(walk_rows))
    if scores.empty or "selected_candidate" not in scores:
        return fallback
    grouped = scores.groupby("selected_candidate")["challenger_profit_score"].mean().sort_values(ascending=False)
    for candidate_id in grouped.index:
        policy = _policy_by_id(policies, str(candidate_id))
        if policy is not None:
            return policy
    return fallback


def _profit_regime_distribution_rows(features: pd.DataFrame, policies: Sequence[RegimePolicy]) -> list[dict]:
    rows = []
    for policy in policies:
        regimes = _profit_regime_series(apply_policy(features, policy)["regime"])
        stats = regimes.value_counts(normalize=True)
        rows.append(
            {
                "candidate_id": policy.candidate_id,
                "risk_on_ratio": round(float(stats.get("risk_on", 0.0)), 6),
                "neutral_ratio": round(float(stats.get("neutral", 0.0)), 6),
                "risk_off_ratio": round(float(stats.get("risk_off", 0.0)), 6),
                "max_single_regime_ratio": round(float(stats.max()) if len(stats) else 0.0, 6),
            }
        )
    return rows


def _profit_event_study_rows(labels: pd.DataFrame, policies: Sequence[RegimePolicy], features: pd.DataFrame) -> list[dict]:
    rows = []
    for policy in policies:
        regimes = _profit_regime_series(apply_policy(features, policy)["regime"])
        data = labels.join(regimes.rename("regime"), how="inner")
        for regime in ("risk_on", "neutral", "risk_off"):
            subset = data[data["regime"] == regime]
            rows.append(
                {
                    "candidate_id": policy.candidate_id,
                    "regime": regime,
                    "observations": int(len(subset)),
                    "future_20d_equity_return": round(float(subset["future_20d_equity_return"].mean()), 6) if "future_20d_equity_return" in subset and len(subset) else 0.0,
                    "future_20d_equity_max_drawdown": round(float(subset["future_20d_equity_max_drawdown"].mean()), 6) if "future_20d_equity_max_drawdown" in subset and len(subset) else 0.0,
                    "risk_on_profitable_rate": round(float(subset["risk_on_profitable_next_20d"].mean()), 6) if "risk_on_profitable_next_20d" in subset and len(subset) else 0.0,
                    "risk_off_preferred_rate": round(float(subset["risk_off_preferred_next_20d"].mean()), 6) if "risk_off_preferred_next_20d" in subset and len(subset) else 0.0,
                }
            )
    return rows


def run_regime_profit_training(
    features: pd.DataFrame,
    asset_panel: pd.DataFrame,
    *,
    policies: Sequence[RegimePolicy] | None = None,
) -> dict:
    """Run profit-oriented Market Regime champion/challenger training."""
    features = features.sort_index().replace([np.inf, -np.inf], np.nan).dropna(subset=["trend_raw", "breadth_raw", "risk_raw", "volume_raw"])
    panel = asset_panel.sort_index().copy()
    common_index = features.index.intersection(panel.index)
    features = features.loc[common_index]
    panel = panel.loc[common_index]
    labels = build_profit_labels(panel)
    notes = list(panel.attrs.get("notes", []))
    if len(features) < 504 or len(panel) < 504:
        return {
            "decision": PromotionGateResult.INSUFFICIENT_DATA.value,
            "best_challenger_id": "",
            "champion_metrics": {},
            "best_challenger_metrics": {},
            "candidate_rows": [],
            "walk_forward_rows": [],
            "baseline_rows": [],
            "regime_exposure_rows": [],
            "regime_distribution_rows": [],
            "event_rows": [],
            "features": features,
            "labels": labels,
            "asset_panel": panel,
            "notes": notes + ["insufficient_data: need at least 504 aligned rows"],
        }

    candidate_policies = list(policies) if policies is not None else generate_candidate_policies()
    policy_ids = {policy.candidate_id for policy in candidate_policies}
    for required in (CHAMPION_POLICY, TREND_ONLY_POLICY, TREND_BREADTH_POLICY):
        if required.candidate_id not in policy_ids:
            candidate_policies.insert(0, required)
            policy_ids.add(required.candidate_id)

    full_rows_with_policy = _profit_candidate_rows(features, panel, candidate_policies)
    full_best = full_rows_with_policy[0] if full_rows_with_policy else {}
    full_best_policy = full_best.get("policy", CHAMPION_POLICY) if full_best else CHAMPION_POLICY
    walk_rows = _profit_walk_forward_rows(features, panel, candidate_policies)
    champion_metrics = _policy_profit_metrics(features, panel, CHAMPION_POLICY)
    preliminary_baseline_rows = build_profit_baseline_rows(features, panel, full_best_policy)
    validation_summary_rows = _profit_candidate_validation_summary_rows(features, panel, candidate_policies)
    candidate_rows = [_public_row(row) for row in full_rows_with_policy]
    gate_rows = build_profit_gate_diagnostics(candidate_rows, champion_metrics, preliminary_baseline_rows, validation_summary_rows)
    best_validated = select_best_validated_formula(candidate_rows, gate_rows, validation_summary_rows)
    best_validated_policy = _policy_by_id(candidate_policies, str(best_validated.get("candidate_id", ""))) if best_validated else None
    if best_validated_policy is None:
        best_validated_policy = CHAMPION_POLICY
        best_validated = _public_row(champion_metrics)
    best_metrics = _policy_profit_metrics(features, panel, best_validated_policy)
    baseline_rows = build_profit_baseline_rows(features, panel, best_validated_policy)

    decision, decision_reason = _profit_decision_v3(best_validated, champion_metrics, walk_rows)
    if not walk_rows:
        notes.append("insufficient_data: no valid walk-forward windows")
    notes.extend(
        [
            f"rows={len(features)}",
            f"walk_forward_windows={len(walk_rows)}",
            "objective=profit_oriented_tradable_beta_exposure",
            "selection=v3_best_validated_formula",
            f"decision_reason={decision_reason}",
            "production_formula_not_applied",
        ]
    )

    best_unconstrained_id = str(full_best.get("candidate_id", "")) if full_best else ""
    best_validated_id = str(best_validated.get("candidate_id", best_validated_policy.candidate_id))
    champion_gate = next((row for row in gate_rows if row["candidate_id"] == CHAMPION_POLICY.candidate_id), {})
    distribution_policies = [CHAMPION_POLICY, TREND_ONLY_POLICY, TREND_BREADTH_POLICY, full_best_policy, best_validated_policy]
    seen: set[str] = set()
    distribution_policies = [policy for policy in distribution_policies if not (policy.candidate_id in seen or seen.add(policy.candidate_id))]
    event_rows = _profit_event_study_rows(labels, distribution_policies, features)
    distribution_rows = _profit_regime_distribution_rows(features, distribution_policies)
    return {
        "decision": decision.value,
        "decision_reason": decision_reason,
        "best_challenger_id": best_validated_id,
        "best_unconstrained_id": best_unconstrained_id,
        "best_validated_id": best_validated_id,
        "best_policy": best_validated_policy,
        "best_validated_policy": best_validated_policy,
        "champion_metrics": _public_row(champion_metrics),
        "best_unconstrained_metrics": _public_row(full_best) if full_best else {},
        "best_challenger_metrics": _public_row(best_metrics),
        "best_validated_metrics": _public_row(best_metrics),
        "champion_gate_diagnostics": champion_gate,
        "candidate_rows": candidate_rows,
        "walk_forward_rows": walk_rows,
        "candidate_validation_summary_rows": validation_summary_rows,
        "candidate_gate_rows": gate_rows,
        "baseline_rows": baseline_rows,
        "regime_exposure_rows": baseline_rows,
        "regime_distribution_rows": distribution_rows,
        "event_rows": event_rows,
        "features": features,
        "labels": labels,
        "asset_panel": panel,
        "asset_sources": dict(panel.attrs.get("asset_sources", {})),
        "notes": notes,
    }


def _recommended_profit_config(result: dict) -> str:
    policy = result.get("best_validated_policy") or result.get("best_policy")
    decision = str(result.get("decision", PromotionGateResult.KEEP_CHAMPION.value))
    lines = [
        f"decision: {decision}",
        f"decision_reason: {result.get('decision_reason', '')}",
        "apply: false",
        "objective: profit_oriented_tradable_beta_exposure",
        f"best_unconstrained_id: {result.get('best_unconstrained_id', '')}",
        f"best_validated_id: {result.get('best_validated_id', '')}",
    ]
    if (
        decision == PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW.value
        and isinstance(policy, RegimePolicy)
        and policy.candidate_id != CHAMPION_POLICY.candidate_id
    ):
        lines.extend(
            [
                "recommended_config:",
                f"  candidate_id: {policy.candidate_id}",
                "  validated: true",
                "  weights:",
            ]
        )
        for key, value in policy.weights.items():
            lines.append(f"    {key}: {value}")
        lines.extend(
            [
                f"  bull_threshold: {policy.bull_threshold}",
                f"  bear_threshold: {policy.bear_threshold}",
                f"  trend_confirm: {policy.trend_confirm}",
                f"  breadth_confirm: {policy.breadth_confirm}",
                f"  bear_trend_breakdown: {policy.bear_trend_breakdown}",
                f"  bear_breadth_breakdown: {policy.bear_breadth_breakdown}",
                f"  smoothing_window: {policy.smoothing_window}",
                f"  min_dwell: {policy.min_dwell}",
            ]
        )
    else:
        lines.append("recommended_config: null")
    return "\n".join(lines) + "\n"


def _profit_markdown(result: dict) -> str:
    champion = result.get("champion_metrics", {})
    validated = result.get("best_validated_metrics") or result.get("best_challenger_metrics", {})
    unconstrained = result.get("best_unconstrained_metrics", {})
    champion_gate = result.get("champion_gate_diagnostics", {})
    lines = [
        "# Market Regime Profit Champion vs Challenger",
        "",
        f"- Decision: `{result.get('decision', PromotionGateResult.KEEP_CHAMPION.value)}`",
        f"- Decision reason: `{result.get('decision_reason', '')}`",
        f"- Best unconstrained: `{result.get('best_unconstrained_id', '')}`",
        f"- Best validated: `{result.get('best_validated_id', '')}`",
        "- Objective: `profit_oriented_tradable_beta_exposure`",
        "- Production formula applied: `false`",
        "",
        "## Metrics",
        (
            f"- Champion: CAGR={float(champion.get('cagr', 0.0)):.2%}, "
            f"Sharpe={float(champion.get('sharpe', 0.0)):.2f}, "
            f"Calmar={float(champion.get('calmar', 0.0)):.2f}, "
            f"MaxDD={float(champion.get('max_drawdown', 0.0)):.2%}"
        ),
        (
            f"- Best unconstrained: CAGR={float(unconstrained.get('cagr', 0.0)):.2%}, "
            f"Sharpe={float(unconstrained.get('sharpe', 0.0)):.2f}, "
            f"Calmar={float(unconstrained.get('calmar', 0.0)):.2f}, "
            f"MaxDD={float(unconstrained.get('max_drawdown', 0.0)):.2%}"
        ),
        (
            f"- Best validated: CAGR={float(validated.get('cagr', 0.0)):.2%}, "
            f"Sharpe={float(validated.get('sharpe', 0.0)):.2f}, "
            f"Calmar={float(validated.get('calmar', 0.0)):.2f}, "
            f"MaxDD={float(validated.get('max_drawdown', 0.0)):.2%}"
        ),
        "",
        "## Champion Gate Diagnostics",
        f"- Passes validation: `{champion_gate.get('passes_validation', '')}`",
        f"- Failed gates: `{champion_gate.get('failed_gates', '')}`",
        f"- Warnings: `{champion_gate.get('warnings', '')}`",
        "",
        "## Baselines",
    ]
    for row in result.get("baseline_rows", []):
        lines.append(
            f"- `{row.get('strategy')}`: CAGR={float(row.get('cagr', 0.0)):.2%}, "
            f"Sharpe={float(row.get('sharpe', 0.0)):.2f}, "
            f"Calmar={float(row.get('calmar', 0.0)):.2f}, "
            f"MaxDD={float(row.get('max_drawdown', 0.0)):.2%}"
        )
    lines.extend(["", "## Notes"])
    for note in result.get("notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def write_regime_profit_report(output_dir: str | Path, result: dict) -> dict:
    """Write the v2 profit-oriented regime research report."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    _csv(output / "candidate_profit_search.csv", result.get("candidate_rows", []))
    _csv(output / "walk_forward_profit_results.csv", result.get("walk_forward_rows", []))
    _csv(output / "baseline_comparison.csv", result.get("baseline_rows", []))
    _csv(output / "regime_exposure_ab_test.csv", result.get("regime_exposure_rows", []))
    _csv(output / "regime_distribution.csv", result.get("regime_distribution_rows", []))
    _csv(output / "candidate_gate_diagnostics.csv", result.get("candidate_gate_rows", []))
    _csv(output / "candidate_validation_summary.csv", result.get("candidate_validation_summary_rows", []))
    _csv(output / "event_study.csv", result.get("event_rows", []))

    asset_panel = result.get("asset_panel")
    features = result.get("features")
    labels = result.get("labels")
    if isinstance(asset_panel, pd.DataFrame):
        asset_panel.to_parquet(output / "tradable_asset_panel.parquet")
    if isinstance(features, pd.DataFrame):
        features.to_parquet(output / "regime_feature_history.parquet")
    if isinstance(labels, pd.DataFrame):
        labels.to_parquet(output / "regime_label_history.parquet")

    (output / "recommended_profit_config.yaml").write_text(_recommended_profit_config(result), encoding="utf-8")
    (output / "profit_champion_vs_challenger.md").write_text(_profit_markdown(result), encoding="utf-8")
    run_log = output / "run.log"
    if not run_log.exists():
        run_log.write_text("market_regime_profit_training_report_written=true\n", encoding="utf-8")

    report_files = [
        "summary.json",
        "profit_champion_vs_challenger.md",
        "tradable_asset_panel.parquet",
        "regime_feature_history.parquet",
        "regime_label_history.parquet",
        "candidate_profit_search.csv",
        "walk_forward_profit_results.csv",
        "baseline_comparison.csv",
        "regime_exposure_ab_test.csv",
        "regime_distribution.csv",
        "candidate_gate_diagnostics.csv",
        "candidate_validation_summary.csv",
        "event_study.csv",
        "recommended_profit_config.yaml",
        "run.log",
    ]
    champion = result.get("champion_metrics", {})
    challenger = result.get("best_challenger_metrics", {})
    summary = {
        "status": "ok",
        "decision": str(result.get("decision", PromotionGateResult.KEEP_CHAMPION.value)),
        "decision_reason": str(result.get("decision_reason", "")),
        "best_challenger_id": str(result.get("best_challenger_id", "")),
        "best_unconstrained_id": str(result.get("best_unconstrained_id", "")),
        "best_validated_id": str(result.get("best_validated_id", "")),
        "champion_metrics": champion,
        "best_challenger_metrics": challenger,
        "best_unconstrained_metrics": result.get("best_unconstrained_metrics", {}),
        "best_validated_metrics": result.get("best_validated_metrics", {}),
        "champion_gate_diagnostics": result.get("champion_gate_diagnostics", {}),
        "oos_walk_forward_windows": len(result.get("walk_forward_rows", [])),
        "asset_sources": result.get("asset_sources", {}),
        "report_files": report_files,
        "notes": list(result.get("notes", [])),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_to_jsonable), encoding="utf-8")
    return summary


def run_and_write_profit_report(
    *,
    index_df: pd.DataFrame,
    asset_panel: pd.DataFrame,
    output_dir: str | Path,
    start: str | None = None,
    end: str | None = None,
    max_candidates: int = 1000,
    breadth_history: pd.DataFrame | None = None,
) -> dict:
    features = build_regime_feature_history(index_df, breadth_history, start=start, end=end)
    policies = generate_candidate_policies(max_candidates=max_candidates)
    result = run_regime_profit_training(features, asset_panel, policies=policies)
    return write_regime_profit_report(output_dir, result)
