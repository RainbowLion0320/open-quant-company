"""
控制论运行机制层 — 钱学森工程控制论在量化系统中的应用.

This facade keeps the historical ``cybernetics.orchestrator`` API stable while
runtime policy, observations, and decision helpers live in focused modules.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from cybernetics import adaptive_params as adaptive_policy
from cybernetics import config as runtime_config
from cybernetics import hybrid_decision, market_observations
from cybernetics.regime import MarketRegime, detect_trend_regime
from cybernetics.types import (
    FeedbackReport,
    MarketBreadth,
    MarketContext,
    MarketVolume,
    StockSignal,
    TradeRecord,
)


def _load_config():
    return runtime_config._load_config()


def _detection_config() -> Dict[str, Any]:
    return runtime_config._detection_config()


def _regime_min_dwell() -> int:
    return runtime_config._regime_min_dwell()


def _regime_transition_state_path() -> Optional[str]:
    return runtime_config._regime_transition_state_path()


def _get_regime_transition_tracker():
    return runtime_config._get_regime_transition_tracker()


def reset_regime_transition_state(*, remove_persisted: bool = True) -> None:
    runtime_config.reset_regime_transition_state(remove_persisted=remove_persisted)


def _regime_observation_key(bench, breadth: MarketBreadth, volume: MarketVolume) -> str:
    return runtime_config._regime_observation_key(bench, breadth, volume)


def generate_feedback(trades: List[TradeRecord], current_positions: List[StockSignal]) -> FeedbackReport:
    return adaptive_policy.generate_feedback(trades, current_positions, config_loader=_load_config)


_REGIME_INDEXES: list[tuple] | None = None


def _get_regime_indexes() -> list[tuple]:
    return market_observations._get_regime_indexes()


def _regime_indexes() -> list[tuple]:
    return market_observations._regime_indexes()


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return market_observations._clamp(value, lower, upper)


def _frame_close_volume(df):
    return market_observations._frame_close_volume(df)


_stock_daily_files = market_observations._stock_daily_files
_stock_daily_source_sql = market_observations._stock_daily_source_sql
_compute_full_market_breadth_duckdb = market_observations._compute_full_market_breadth_duckdb
_read_breadth_observation = market_observations._read_breadth_observation


def _compute_full_market_breadth(files: Optional[Sequence[Any]] = None, *, use_cache: bool = True) -> MarketBreadth:
    return market_observations._compute_full_market_breadth(files, use_cache=use_cache)


_compute_full_market_volume_duckdb = market_observations._compute_full_market_volume_duckdb


def _compute_full_market_volume(files: Optional[Sequence[Any]] = None, *, use_cache: bool = True) -> MarketVolume:
    return market_observations._compute_full_market_volume(files, use_cache=use_cache)


def _index_trend_strength(df) -> Optional[float]:
    return market_observations._index_trend_strength(df)


def _compute_multi_index_trend(index_frames: Dict[str, Any]) -> tuple[float, Dict[str, float]]:
    return market_observations._compute_multi_index_trend(index_frames)


def _index_risk_metrics(df) -> Optional[Dict[str, float]]:
    return market_observations._index_risk_metrics(df)


def _compute_risk_strength(index_frames: Dict[str, Any], breadth: MarketBreadth) -> tuple[float, Dict[str, float]]:
    overrides = {
        "_load_config": _load_config,
        "_regime_indexes": _regime_indexes,
        "_index_risk_metrics": _index_risk_metrics,
    }
    previous = {name: getattr(market_observations, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(market_observations, name, value)
        return market_observations._compute_risk_strength(index_frames, breadth)
    finally:
        for name, value in previous.items():
            setattr(market_observations, name, value)


def _index_volume_confirmation(df) -> Optional[Dict[str, float]]:
    return market_observations._index_volume_confirmation(df)


def _compute_multi_index_volume(index_frames: Dict[str, Any]) -> tuple[float, Dict[str, float]]:
    return market_observations._compute_multi_index_volume(index_frames)


def _compute_volume_strength(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    market_volume: MarketVolume,
) -> tuple[float, str, Dict[str, float]]:
    return market_observations._compute_volume_strength(index_frames, breadth, market_volume)


def _breadth_strength(breadth: MarketBreadth) -> float:
    return market_observations._breadth_strength(breadth)


def _compute_regime_score_v2(
    bench_df,
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    market_volume: Optional[MarketVolume] = None,
) -> tuple[float, Dict[str, float]]:
    return market_observations._compute_regime_score_v2(bench_df, index_frames, breadth, market_volume)


def _classify_regime(score: float, components: Dict[str, float], breadth: MarketBreadth) -> MarketRegime:
    return market_observations._classify_regime(score, components, breadth)


def _hmm_detect(index_frames: Dict[str, Any], breadth: MarketBreadth, volume: MarketVolume):
    return market_observations._hmm_detect(index_frames, breadth, volume)


def _normalise_regime_probs(regime_probs: Dict[str, float] | None) -> Dict[str, float]:
    return hybrid_decision._normalise_regime_probs(regime_probs)


def _resolve_regime_decision(
    *,
    rule_raw_regime: MarketRegime,
    hmm_raw_regime: MarketRegime | None,
    regime_probs: Dict[str, float] | None,
    hmm_confidence: float,
    engine: str,
):
    return hybrid_decision._resolve_regime_decision(
        rule_raw_regime=rule_raw_regime,
        hmm_raw_regime=hmm_raw_regime,
        regime_probs=regime_probs,
        hmm_confidence=hmm_confidence,
        engine=engine,
    )


def detect_market_regime(
    index_data: dict = None,
    window: int = 60,
    symbol: str = "sh000001",
) -> MarketRegime:
    """
    市场状态检测：基于均线排列、波动率和趋势强度
    不传 index_data 时自动从 AKShare 拉取上证指数数据
    """
    return detect_trend_regime(index_data=index_data, window=window, symbol=symbol)


def adaptive_params(regime: MarketRegime, probs: Dict[str, float] | None = None) -> Dict[str, float]:
    return adaptive_policy.adaptive_params(regime, probs=probs, config_loader=_load_config)


# =====================================================================
# 协调器 (Orchestrator)
# =====================================================================

class QuantOrchestrator:
    """连接巴菲特约束层和控制论运行层的量化系统协调器。"""

    def __init__(self):
        self.regime = MarketRegime.UNKNOWN
        self.params = {}
        self.trade_history: List[TradeRecord] = []
        self.market_snapshot: MarketContext = None

    def set_regime(self, index_data: dict = None):
        """设置当前市场状态。不传 index_data 时自动拉取真实数据。"""
        if index_data is None:
            snapshot = self.detect()
            self.regime = snapshot.regime
        else:
            self.regime = detect_market_regime(index_data)
            self.params = adaptive_params(self.regime)

    def detect(self) -> MarketContext:
        """
        运行完整市场检测，返回 MarketContext 快照。
        自动拉取真实指数数据，计算多指数趋势、全市场宽度、风险和量能确认。

        如果配置 regime_engine=hmm 且模型可用，使用 Student-t HMM 做概率推断；
        否则退化到规则评分。
        """
        import math
        from datetime import datetime

        from data.fetcher import get_index_daily

        index_frames: Dict[str, Any] = {}
        for symbol, _label, _weight in _regime_indexes():
            try:
                index_frames[symbol] = get_index_daily(symbol, force_refresh=False)
            except Exception:
                index_frames[symbol] = None

        df = index_frames.get("sh000001")
        bench = _frame_close_volume(df)
        if bench is None or len(bench) < 60:
            transition = _get_regime_transition_tracker().apply(
                MarketRegime.UNKNOWN,
                score=50.0,
                as_of=datetime.now().strftime("%Y-%m-%d"),
            )
            self.market_snapshot = MarketContext(
                regime=transition.confirmed,
                raw_regime=transition.raw,
                regime_state=transition.to_dict(),
                date=datetime.now().strftime("%Y-%m-%d"),
            )
            return self.market_snapshot

        close = bench["close"]
        ma5 = float(close.tail(5).mean())
        ma20 = float(close.tail(20).mean())
        ma60 = float(close.tail(60).mean())

        breadth_snapshot = _compute_full_market_breadth()
        volume_snapshot = _compute_full_market_volume()
        score, components = _compute_regime_score_v2(bench, index_frames, breadth_snapshot, volume_snapshot)
        rule_raw_regime = _classify_regime(score, components, breadth_snapshot)
        observation_key = _regime_observation_key(bench, breadth_snapshot, volume_snapshot)

        # --- HMM detection path ---
        regime_probs: Dict[str, float] = {}
        detection_method = "rule_based"
        hmm_confidence = 0.0
        hmm_entropy = 0.0
        raw_regime = rule_raw_regime
        decision_reason = "rule_only"

        try:
            hmm_cfg = _load_config().get("hmm", {})
            engine = hmm_cfg.get("regime_engine", _load_config().get("regime_engine", "rule_based"))
        except Exception:
            engine = "rule_based"

        hmm_raw = None
        if engine in ("hmm", "hybrid"):
            try:
                regime_probs, hmm_confidence, hmm_entropy, hmm_raw = _hmm_detect(
                    index_frames, breadth_snapshot, volume_snapshot
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"HMM detection failed, falling back to rules: {e}")

        decision = _resolve_regime_decision(
            rule_raw_regime=rule_raw_regime,
            hmm_raw_regime=hmm_raw,
            regime_probs=regime_probs,
            hmm_confidence=hmm_confidence,
            engine=engine,
        )
        raw_regime = decision.raw_regime
        detection_method = decision.detection_method
        regime_probs = decision.regime_probs
        decision_reason = decision.decision_reason

        # --- Smoothing ---
        transition = _get_regime_transition_tracker().apply(
            raw_regime,
            score=score,
            as_of=observation_key,
        )
        self.regime = transition.confirmed

        # --- Adaptive params (probability-weighted if HMM) ---
        if regime_probs and detection_method in {"hmm", "hybrid"}:
            self.params = adaptive_params(self.regime, probs=regime_probs)
        else:
            self.params = adaptive_params(self.regime)

        _volume_strength, vol_trend, _volume_detail = _compute_volume_strength(
            index_frames,
            breadth_snapshot,
            volume_snapshot,
        )

        trend_raw = components.get("trend_raw", 0.5)
        breadth_detail = breadth_snapshot.to_dict()
        ma_trend = (
            f"MA5:{ma5:.0f} MA20:{ma20:.0f} MA60:{ma60:.0f} · "
            f"多指数趋势 {trend_raw:.0%} · 全A上涨 {breadth_snapshot.advance_ratio:.0%} · "
            f"MA20上方 {breadth_snapshot.above_ma20:.0%} · 样本 {breadth_snapshot.sample_size}"
        )

        self.market_snapshot = MarketContext(
            regime=self.regime,
            raw_regime=raw_regime,
            regime_score=score,
            index_ma_trend=ma_trend,
            volume_trend=vol_trend,
            breadth=breadth_snapshot.advance_ratio,
            breadth_detail=breadth_detail,
            score_components=components,
            regime_state=transition.to_dict(),
            date=datetime.now().strftime("%Y-%m-%d"),
            regime_probs=regime_probs,
            detection_method=detection_method,
            hmm_confidence=hmm_confidence,
            hmm_entropy=hmm_entropy,
            decision_reason=decision_reason,
        )
        return self.market_snapshot

    def get_params(self) -> Dict[str, float]:
        """获取当前自适应参数"""
        return self.params or adaptive_params(MarketRegime.SIDEWAYS)

    def status(self) -> Dict:
        """系统状态快照"""
        return {
            "regime": self.regime.value,
            "params": self.params,
            "total_trades": len(self.trade_history),
            "timestamp": datetime.now().isoformat(),
        }
