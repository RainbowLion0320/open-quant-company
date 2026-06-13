"""
AlphaModel — strategy alpha signal generation.

Each strategy produces a list[AlphaSignal]: direction + confidence + score.
No buy/hold decisions here — that's the portfolio constructor's job.

Adapters wrap the 4 existing scorer functions so they plug into the pipeline
without being rewritten.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Callable, Optional

import pandas as pd

from pipeline.types import AlphaSignal


class AlphaModel(ABC):
    """Abstract alpha signal generator."""

    name: str = "base"
    label: str = "Base Alpha"

    @abstractmethod
    def generate_alpha(
        self,
        universe: list[str],
        prices: pd.DataFrame,
        date_idx: int,
        regime: str,
    ) -> list[AlphaSignal]:
        """Produce alpha signals for all symbols in the universe at a given date."""
        ...

    def generate_score_panel(
        self,
        universe: list[str],
        prices: pd.DataFrame,
        date_idx: int,
        regime: str,
    ) -> list[dict]:
        """Produce full cross-sectional scores for evidence calculations."""
        return []

    def rebalance_trigger(
        self,
        dt: date,
        regime: str,
        holdings: dict[str, int],
    ) -> bool:
        """Optional per-strategy rebalance hook.  Return True to force rebalance."""
        return False


# ── Adapter: wraps per-stock scorer function ──

ScorerFn = Callable[[str, pd.Series, int, str], float]


class StrategyAlphaAdapter(AlphaModel):
    """Adapt a per-stock scorer(sym, series, idx, regime) → float into AlphaModel."""

    def __init__(
        self,
        name: str,
        label: str,
        scorer: ScorerFn,
        min_score: float = 30.0,
        horizon_days: int = 20,
        rebalance_trigger: Optional[Callable[[date, str, dict[str, int]], bool]] = None,
    ):
        self.name = name
        self.label = label
        self._scorer = scorer
        self.min_score = min_score
        self.horizon_days = horizon_days
        self._rebalance_trigger = rebalance_trigger
        self._score_cache_key: tuple | None = None
        self._score_cache_rows: tuple[dict, ...] | None = None

    def _cache_key(
        self,
        universe: list[str],
        prices: pd.DataFrame,
        date_idx: int,
        regime: str,
    ) -> tuple:
        as_of = prices.index[date_idx] if 0 <= date_idx < len(prices.index) else None
        return (
            id(prices),
            len(prices),
            str(as_of),
            int(date_idx),
            str(regime),
            tuple(universe),
        )

    def _score_rows(
        self,
        universe: list[str],
        prices: pd.DataFrame,
        date_idx: int,
        regime: str,
    ) -> list[dict]:
        key = self._cache_key(universe, prices, date_idx, regime)
        if self._score_cache_key == key and self._score_cache_rows is not None:
            return [dict(row) for row in self._score_cache_rows]

        rows: list[dict] = []
        ts = datetime.now().isoformat()
        for sym in universe:
            if sym not in prices.columns:
                continue
            try:
                score = float(self._scorer(sym, prices[sym], date_idx, regime))
                rows.append(
                    {
                        "symbol": sym,
                        "strategy": self.name,
                        "score": round(score, 6),
                        "horizon_days": self.horizon_days,
                        "timestamp": ts,
                        "data_quality": "ok",
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "symbol": sym,
                        "strategy": self.name,
                        "score": None,
                        "horizon_days": self.horizon_days,
                        "timestamp": ts,
                        "data_quality": f"score_error:{type(exc).__name__}",
                    }
                )

        self._score_cache_key = key
        self._score_cache_rows = tuple(dict(row) for row in rows)
        return rows

    def generate_alpha(
        self,
        universe: list[str],
        prices: pd.DataFrame,
        date_idx: int,
        regime: str,
    ) -> list[AlphaSignal]:
        signals: list[AlphaSignal] = []
        for row in self._score_rows(universe, prices, date_idx, regime):
            score = row["score"]
            if score is None:
                continue

            if score < self.min_score:
                continue

            direction = "buy" if score >= 50 else "hold"
            signals.append(AlphaSignal(
                symbol=row["symbol"],
                strategy=self.name,
                direction=direction,
                confidence=min(1.0, max(0.0, score / 100)),
                score=round(float(score), 1),
                horizon_days=self.horizon_days,
                reason=f"{self.label} score={score:.1f} regime={regime}",
                timestamp=row["timestamp"],
            ))

        signals.sort(key=lambda s: s.score, reverse=True)
        return signals

    def generate_score_panel(
        self,
        universe: list[str],
        prices: pd.DataFrame,
        date_idx: int,
        regime: str,
    ) -> list[dict]:
        return self._score_rows(universe, prices, date_idx, regime)

    def rebalance_trigger(self, dt, regime, holdings):
        if self._rebalance_trigger:
            return self._rebalance_trigger(dt, regime, holdings)
        return False


# ── AlphaModel from signal parquet (for paper trading) ──

class SignalParquetAlphaModel(AlphaModel):
    """Read pre-computed alpha signals from signal parquet files.

    This is used by paper trading when signals have already been computed
    by the daily cron scan (compute_signals.py).
    """

    def __init__(self, name: str, label: str, signal_path, max_signals: int = 10):
        self.name = name
        self.label = label
        self._signal_path = signal_path
        self.max_signals = max_signals

    def generate_alpha(self, universe, prices, date_idx, regime):
        from data.storage.datahub import get_datahub

        hub = get_datahub()
        path = hub.resolve_path(self._signal_path) if isinstance(self._signal_path, str) else self._signal_path
        df = hub.latest_batch(path)
        if df is None or df.empty:
            return []

        signals: list[AlphaSignal] = []
        ts = datetime.now().isoformat()

        rows = df.sort_values("score", ascending=False) if "score" in df.columns else df
        for _, row in rows.head(self.max_signals).iterrows():
            sym = str(row.get("symbol", row.get("code", "")))
            sym = sym.split(".")[0] if "." in sym else sym
            score = float(row.get("score", 0) or 0)
            sig = str(row.get("signal", "hold")).lower()
            direction = sig if sig in ("buy", "sell") else "hold"

            signals.append(AlphaSignal(
                symbol=sym,
                strategy=self.name,
                direction=direction,
                confidence=min(1.0, score / 100),
                score=round(score, 1),
                horizon_days=20,
                reason=f"cron signal: {direction}",
                timestamp=ts,
            ))

        return signals
