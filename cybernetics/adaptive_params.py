"""Feedback loop and market-regime adaptive parameter policy."""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List

from cybernetics.config import _load_config as _default_load_config
from cybernetics.regime import MarketRegime, to_market_regime
from cybernetics.types import FeedbackReport, StockSignal, TradeRecord

ConfigLoader = Callable[[], dict]


def generate_feedback(
    trades: List[TradeRecord],
    current_positions: List[StockSignal],
    *,
    config_loader: ConfigLoader | None = None,
) -> FeedbackReport:
    """
    反馈回路核心：分析交易结果，生成调整建议
    """
    load_config = config_loader or _default_load_config
    cfg = load_config()["feedback"]
    max_losses = cfg["max_consecutive_losses"]
    report = FeedbackReport(date=datetime.now().strftime("%Y-%m-%d"))

    if not trades:
        return report

    report.total_trades = len(trades)
    wins = [t for t in trades if t.return_pct > 0]
    report.win_rate = len(wins) / len(trades)
    report.avg_return = sum(t.return_pct for t in trades) / len(trades)

    # 最大回撤
    cumulative = 1.0
    peak = 1.0
    for t in trades:
        cumulative *= (1 + t.return_pct / 100)
        peak = max(peak, cumulative)
        dd = (peak - cumulative) / peak
        report.max_drawdown = max(report.max_drawdown, dd)

    # 检测连续亏损
    consec = 0
    for t in sorted(trades, key=lambda x: x.entry_date):
        if t.return_pct <= 0:
            consec += 1
        else:
            consec = 0
        report.consecutive_losses = max(report.consecutive_losses, consec)

    # 熔断检查
    if report.consecutive_losses >= max_losses:
        report.circuit_breaker = True
        report.circuit_reason = f"连续亏损{report.consecutive_losses}次，触发熔断"
        report.adjustments.append("暂停新开仓，审查策略")

    # 胜率过低 — 阈值从 config 读取，fallback 0.35/10
    try:
        fb_cfg = load_config()["feedback"]
        min_win_rate = float(fb_cfg.get("min_win_rate", 0.35))
        min_trades_for_review = int(fb_cfg.get("min_trades_for_review", 10))
    except Exception:
        min_win_rate = 0.35
        min_trades_for_review = 10

    if report.win_rate < min_win_rate and report.total_trades >= min_trades_for_review:
        report.adjustments.append(f"胜率{report.win_rate:.1%}过低，建议调高置信度阈值")

    return report


def adaptive_params(
    regime: MarketRegime,
    probs: Dict[str, float] | None = None,
    *,
    config_loader: ConfigLoader | None = None,
) -> Dict[str, float]:
    """
    根据市场状态自适应调整参数。

    如果提供 probs（regime 概率向量），做概率加权：
      position_size = P(bull)*0.15 + P(sideways)*0.20 + P(bear)*0.30
    否则退化到原有的硬分类逻辑。
    """
    load_config = config_loader or _default_load_config
    regime = to_market_regime(regime)

    # 基础默认参数；config/settings.yaml 的 cybernetics.adaptive 会覆盖这些值。
    # 注意：HMM 的 bear 状态 = 已经大跌（底部），bull 状态 = 接近顶部
    # 因此 bear 时应更激进（底部机会），bull 时应更保守（顶部风险）
    # 参见 2010-2026 回测：bear 20d forward return +2.51%, bull +1.33%
    _HARD_PARAMS = {
        MarketRegime.BULL: {
            "position_size": 0.15,
            "stop_loss": -0.05,
            "confidence_threshold": 0.75,
            "max_positions": 5,
        },
        MarketRegime.SIDEWAYS: {
            "position_size": 0.20,
            "stop_loss": -0.06,
            "confidence_threshold": 0.70,
            "max_positions": 6,
        },
        MarketRegime.BEAR: {
            "position_size": 0.30,
            "stop_loss": -0.08,
            "confidence_threshold": 0.60,
            "max_positions": 8,
        },
    }

    # 尝试从配置加载覆盖
    _CFG_PARAMS = {}
    try:
        cfg = load_config()["adaptive"]
        for r in (MarketRegime.BULL, MarketRegime.SIDEWAYS, MarketRegime.BEAR):
            if r.value in cfg:
                entry = cfg[r.value]
                _CFG_PARAMS[r] = {
                    "position_size": float(entry["position_size"]),
                    "stop_loss": float(entry["stop_loss"]),
                    "confidence_threshold": float(entry["confidence_threshold"]),
                    "max_positions": int(entry["max_positions"]),
                }
    except Exception:
        pass

    # 合并：配置覆盖硬编码
    merged = {}
    for r in _HARD_PARAMS:
        merged[r] = {**_HARD_PARAMS[r], **(_CFG_PARAMS.get(r, {}))}

    # 概率加权路径
    if probs and sum(probs.values()) > 0.95:
        regime_map = {
            "bull": MarketRegime.BULL,
            "sideways": MarketRegime.SIDEWAYS,
            "bear": MarketRegime.BEAR,
        }
        result = {}
        for key in merged[MarketRegime.BULL]:
            val = sum(
                probs.get(r_str, 0) * merged[r_enum].get(key, 0)
                for r_str, r_enum in regime_map.items()
            )
            result[key] = val
        result["max_positions"] = round(result["max_positions"])
        return result

    return merged.get(regime, merged[MarketRegime.SIDEWAYS])
