"""Configuration and live regime-transition state for cybernetics runtime."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from cybernetics.regime_policy import PRODUCTION_REGIME_POLICY
from cybernetics.regime_state import RegimeTransitionTracker
from cybernetics.types import MarketBreadth, MarketVolume
from core.settings import get_section


_config = None
_REGIME_TRACKER: Optional[RegimeTransitionTracker] = None
_REGIME_TRACKER_PATH: Optional[str] = None


def _load_config():
    global _config
    if _config is None:
        _config = get_section("cybernetics", {})
    return _config


def _detection_config() -> Dict[str, Any]:
    try:
        return _load_config().get("adaptive", {}).get("detection", {})
    except Exception:
        return {}


def _regime_min_dwell() -> int:
    det_cfg = _detection_config()
    return max(1, int(det_cfg.get("regime_min_dwell", PRODUCTION_REGIME_POLICY.min_dwell) or 1))


def _regime_transition_state_path() -> Optional[str]:
    try:
        from data.storage.datahub import get_datahub

        return str(get_datahub().cache_root / "runtime" / "market_regime_state.json")
    except Exception:
        return None


def _get_regime_transition_tracker() -> RegimeTransitionTracker:
    global _REGIME_TRACKER, _REGIME_TRACKER_PATH
    state_path = _regime_transition_state_path()
    if _REGIME_TRACKER is None or state_path != _REGIME_TRACKER_PATH:
        _REGIME_TRACKER = RegimeTransitionTracker(min_dwell=_regime_min_dwell(), state_path=state_path)
        _REGIME_TRACKER_PATH = state_path
    else:
        _REGIME_TRACKER.min_dwell = _regime_min_dwell()
    return _REGIME_TRACKER


def reset_regime_transition_state(*, remove_persisted: bool = True) -> None:
    """Reset the process-level live regime dwell tracker, mainly for tests/tools."""
    global _REGIME_TRACKER
    tracker = _get_regime_transition_tracker()
    tracker.reset(remove_persisted=remove_persisted)
    _REGIME_TRACKER = tracker


def _regime_observation_key(bench, breadth: MarketBreadth, volume: MarketVolume) -> str:
    candidates = []
    try:
        if "date" in bench.columns and len(bench):
            candidates.append(str(bench["date"].iloc[-1])[:10])
    except Exception:
        pass
    for value in (getattr(breadth, "as_of", ""), getattr(volume, "as_of", "")):
        if value:
            candidates.append(str(value)[:10])
    return max(candidates) if candidates else datetime.now().strftime("%Y-%m-%d")
