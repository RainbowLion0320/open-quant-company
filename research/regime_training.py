"""Compatibility facade for modular Market Regime research helpers."""
from research.forward_labels import build_forward_labels, future_compound_return  # noqa: F401
from research.performance import portfolio_metrics  # noqa: F401
from research.regime.core import *  # noqa: F401,F403
from research.regime.assets import _load_treasury_defensive_proxy  # noqa: F401
from research.regime_types import PromotionGateResult, RegimePolicy  # noqa: F401
