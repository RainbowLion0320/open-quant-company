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

from cybernetics.regime_scoring import breadth_strength, clamp, volume_strength


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
    weights={"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10},
    bull_threshold=65.0,
    bear_threshold=35.0,
    trend_confirm=0.55,
    breadth_confirm=0.55,
    bear_trend_breakdown=0.40,
    bear_breadth_breakdown=0.40,
    min_dwell=1,
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
    data["volume"] = pd.to_numeric(data.get("volume", 0.0), errors="coerce").fillna(0.0)
    if "amount" in data.columns:
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    else:
        data["amount"] = data["volume"] * data["close"]
    data = data.dropna(subset=["close"]).sort_values("date").set_index("date")
    return data[["close", "volume", "amount"]]


def build_forward_labels(close: pd.Series, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    """Build forward labels from rows after each feature date."""
    close = close.sort_index().astype(float)
    out = pd.DataFrame(index=close.index)
    for horizon in horizons:
        future = close.shift(-horizon)
        out[f"future_{horizon}d_return"] = (future - close) / close
        drawdowns = []
        volatilities = []
        for pos in range(len(close)):
            window = close.iloc[pos + 1 : pos + horizon + 1]
            if len(window) < horizon:
                drawdowns.append(np.nan)
                volatilities.append(np.nan)
                continue
            start = close.iloc[pos]
            path = window / start - 1.0
            drawdowns.append(float(min(0.0, path.min())))
            returns = window.pct_change().dropna()
            volatilities.append(float(returns.std() * np.sqrt(252)) if len(returns) else np.nan)
        out[f"future_{horizon}d_max_drawdown"] = drawdowns
        out[f"future_{horizon}d_volatility"] = volatilities
    if "future_20d_max_drawdown" in out:
        out["bear_event_next_20d"] = out["future_20d_max_drawdown"] <= -0.08
    if "future_20d_return" in out:
        out["bull_continuation_next_20d"] = out["future_20d_return"] >= 0.03
    return out


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
    n = len(strategy_returns.dropna())
    if n < 10:
        return {"cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "calmar": 0.0, "turnover_proxy": 0.0, "strategy_score": 0.0}

    total = float((1.0 + strategy_returns).prod())
    cagr = total ** (252.0 / n) - 1.0 if total > 0 else -1.0
    vol = float(strategy_returns.std(ddof=1) * np.sqrt(252))
    sharpe = float(strategy_returns.mean() * 252 / vol) if vol > 0 else 0.0
    equity = (1.0 + strategy_returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else 0.0
    turnover_proxy = float(exposure.diff().abs().sum())
    strategy_score = _score_1_100(50.0 + sharpe * 10.0 + calmar * 3.0 + max_drawdown * 100.0 - turnover_proxy * 0.2)
    return {
        "cagr": round(cagr, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "calmar": round(calmar, 6),
        "turnover_proxy": round(turnover_proxy, 6),
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
