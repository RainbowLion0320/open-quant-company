"""Runtime data structures for cybernetics orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cybernetics.regime import MarketRegime


class SectorStrength(Enum):
    """板块强度"""

    LEADING = "leading"
    ROTATING_IN = "rotating_in"
    NEUTRAL = "neutral"
    ROTATING_OUT = "rotating_out"
    LAGGING = "lagging"


@dataclass
class MarketContext:
    """市场环境快照 — 顶层"""

    regime: MarketRegime = MarketRegime.UNKNOWN
    raw_regime: MarketRegime = MarketRegime.UNKNOWN
    regime_score: float = 50.0
    index_ma_trend: str = ""
    volume_trend: str = ""
    breadth: float = 0.0
    breadth_detail: dict[str, Any] = field(default_factory=dict)
    score_components: dict[str, Any] = field(default_factory=dict)
    regime_state: dict[str, Any] = field(default_factory=dict)
    date: str = ""

    regime_probs: dict[str, float] = field(default_factory=dict)
    detection_method: str = "rule_based"
    hmm_confidence: float = 0.0
    hmm_entropy: float = 0.0
    decision_reason: str = ""


@dataclass(frozen=True)
class RegimeDecision:
    raw_regime: MarketRegime
    detection_method: str
    regime_probs: dict[str, float]
    decision_reason: str


@dataclass
class MarketBreadth:
    """全市场宽度快照。所有比例均为 0-1。"""

    advance_ratio: float = 0.5
    above_ma20: float = 0.5
    above_ma60: float = 0.5
    above_ma120: float = 0.5
    sample_size: int = 0
    up_count: int = 0
    down_count: int = 0
    unchanged_count: int = 0
    as_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "advance_ratio": round(self.advance_ratio, 4),
            "above_ma20": round(self.above_ma20, 4),
            "above_ma60": round(self.above_ma60, 4),
            "above_ma120": round(self.above_ma120, 4),
            "sample_size": self.sample_size,
            "up_count": self.up_count,
            "down_count": self.down_count,
            "unchanged_count": self.unchanged_count,
            "as_of": self.as_of,
        }


@dataclass
class MarketVolume:
    """全市场成交额确认快照。"""

    amount_ratio_5_20: float = 1.0
    up_amount_ratio: float = 0.5
    sample_size: int = 0
    amount_5d: float = 0.0
    amount_20d: float = 0.0
    as_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount_ratio_5_20": round(self.amount_ratio_5_20, 4),
            "up_amount_ratio": round(self.up_amount_ratio, 4),
            "sample_size": self.sample_size,
            "amount_5d": round(self.amount_5d, 2),
            "amount_20d": round(self.amount_20d, 2),
            "as_of": self.as_of,
        }


@dataclass
class SectorSnapshot:
    """板块快照 — 中层"""

    name: str = ""
    strength: SectorStrength = SectorStrength.NEUTRAL
    momentum_5d: float = 0.0
    money_flow: str = ""
    signal_count: int = 0


@dataclass
class StockSignal:
    """个股信号 — 底层"""

    symbol: str = ""
    name: str = ""
    signal_type: str = ""
    confidence: float = 0.0
    trigger_reason: str = ""
    buffett_verdict: str = ""
    timestamp: str = ""


@dataclass
class TradeRecord:
    """交易记录"""

    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str = ""
    exit_price: float = 0.0
    return_pct: float = 0.0
    reason: str = ""


@dataclass
class FeedbackReport:
    """反馈报告"""

    date: str
    total_trades: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    max_drawdown: float = 0.0
    consecutive_losses: int = 0
    issues: list[str] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)
    circuit_breaker: bool = False
    circuit_reason: str = ""
