"""Stateful production smoothing for Market Regime transitions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from cybernetics.regime import MarketRegime, to_market_regime
from cybernetics.regime_policy import PRODUCTION_REGIME_POLICY


@dataclass(frozen=True)
class RegimeTransition:
    raw: MarketRegime
    confirmed: MarketRegime
    pending: MarketRegime | None
    pending_count: int
    min_dwell: int
    confirmed_changed: bool
    score: float
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_value": self.raw.value,
            "confirmed_value": self.confirmed.value,
            "pending_value": self.pending.value if self.pending else "",
            "pending_count": self.pending_count,
            "min_dwell": self.min_dwell,
            "confirmed_changed": self.confirmed_changed,
            "score": round(float(self.score), 1),
            "as_of": self.as_of,
        }


class RegimeTransitionTracker:
    """Require consecutive unique observations before confirming regime changes."""

    def __init__(
        self,
        *,
        min_dwell: int = PRODUCTION_REGIME_POLICY.min_dwell,
        state_path: str | Path | None = None,
    ):
        self.min_dwell = max(1, int(min_dwell or 1))
        self.state_path = Path(state_path) if state_path else None
        self.confirmed = MarketRegime.UNKNOWN
        self.pending: MarketRegime | None = None
        self.pending_count = 0
        self.last_raw = MarketRegime.UNKNOWN
        self.last_observation_key = ""
        self._load()

    def apply(
        self,
        raw_regime: MarketRegime | str,
        *,
        score: float = 50.0,
        as_of: str = "",
        min_dwell: int | None = None,
    ) -> RegimeTransition:
        if min_dwell is not None:
            self.min_dwell = max(1, int(min_dwell or 1))

        raw = to_market_regime(raw_regime, default=MarketRegime.UNKNOWN)
        observation_key = str(as_of or "")
        previous_confirmed = self.confirmed

        if raw is MarketRegime.UNKNOWN:
            self.confirmed = MarketRegime.UNKNOWN
            self.pending = None
            self.pending_count = 0
            self.last_raw = raw
            self.last_observation_key = observation_key
            transition = self._transition(raw, score, observation_key, previous_confirmed)
            self._save()
            return transition

        is_new_observation = bool(observation_key) and observation_key != self.last_observation_key
        no_observation_key = not observation_key
        countable = is_new_observation or no_observation_key

        if self.min_dwell <= 1 or self.confirmed is MarketRegime.UNKNOWN:
            self.confirmed = raw
            self.pending = None
            self.pending_count = 0
        elif raw is self.confirmed:
            self.pending = None
            self.pending_count = 0
        elif raw is not self.pending:
            if countable:
                self.pending = raw
                self.pending_count = 1
        elif countable:
            self.pending_count += 1
            if self.pending_count >= self.min_dwell:
                self.confirmed = raw
                self.pending = None
                self.pending_count = 0

        self.last_raw = raw
        if observation_key:
            self.last_observation_key = observation_key
        transition = self._transition(raw, score, observation_key, previous_confirmed)
        self._save()
        return transition

    def reset(self, *, remove_persisted: bool = False) -> None:
        self.confirmed = MarketRegime.UNKNOWN
        self.pending = None
        self.pending_count = 0
        self.last_raw = MarketRegime.UNKNOWN
        self.last_observation_key = ""
        if remove_persisted and self.state_path:
            self.state_path.unlink(missing_ok=True)

    def _transition(self, raw: MarketRegime, score: float, as_of: str, previous: MarketRegime) -> RegimeTransition:
        return RegimeTransition(
            raw=raw,
            confirmed=self.confirmed,
            pending=self.pending,
            pending_count=self.pending_count,
            min_dwell=self.min_dwell,
            confirmed_changed=self.confirmed is not previous,
            score=float(score),
            as_of=as_of,
        )

    def _load(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.confirmed = to_market_regime(data.get("confirmed"), default=MarketRegime.UNKNOWN)
            pending = data.get("pending")
            self.pending = to_market_regime(pending, default=MarketRegime.UNKNOWN) if pending else None
            if self.pending is MarketRegime.UNKNOWN:
                self.pending = None
            self.pending_count = max(0, int(data.get("pending_count", 0) or 0))
            self.last_raw = to_market_regime(data.get("last_raw"), default=MarketRegime.UNKNOWN)
            self.last_observation_key = str(data.get("last_observation_key", "") or "")
        except Exception:
            self.reset(remove_persisted=False)

    def _save(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "confirmed": self.confirmed.value,
            "pending": self.pending.value if self.pending else "",
            "pending_count": self.pending_count,
            "last_raw": self.last_raw.value,
            "last_observation_key": self.last_observation_key,
            "min_dwell": self.min_dwell,
        }
        tmp = self.state_path.with_name(f".tmp-{uuid4().hex}-{self.state_path.name}")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)
