"""
控制论运行机制层 — 钱学森工程控制论在量化系统中的应用

核心理念：
1. 多层递阶 (Hierarchy): 市场环境→板块轮动→个股筛选
2. 反馈回路 (Feedback Loop): 信号→执行→评估→调整
3. 自适应 (Adaptive): 系统根据市场状态自动调整参数

这两个层正交不冲突：
- 巴菲特层 = "做什么" (What) —— 决策的边界和原则
- 控制论层 = "怎么做" (How) —— 执行的机制和流程
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from enum import Enum
from datetime import datetime, timedelta
import yaml
import os


# ----- 配置 -----
_config = None


def _load_config():
    global _config
    if _config is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
        with open(path) as f:
            _config = yaml.safe_load(f)["cybernetics"]
    return _config


# =====================================================================
# 1. 多层递阶结构 (Multi-level Hierarchy)
# =====================================================================

class MarketRegime(Enum):
    """市场状态 — 顶层判断"""
    BULL = "bull"           # 牛市：积极
    SIDEWAYS = "sideways"   # 震荡：谨慎
    BEAR = "bear"           # 熊市：防御
    UNKNOWN = "unknown"


class SectorStrength(Enum):
    """板块强度"""
    LEADING = "leading"      # 领涨
    ROTATING_IN = "rotating_in"
    NEUTRAL = "neutral"
    ROTATING_OUT = "rotating_out"
    LAGGING = "lagging"      # 领跌


@dataclass
class MarketContext:
    """市场环境快照 — 顶层"""
    regime: MarketRegime = MarketRegime.UNKNOWN
    index_ma_trend: str = ""        # 均线排列（多头/空头）
    volume_trend: str = ""          # 放量/缩量
    breadth: float = 0.0            # 市场宽度（涨跌比）
    date: str = ""


@dataclass
class SectorSnapshot:
    """板块快照 — 中层"""
    name: str = ""
    strength: SectorStrength = SectorStrength.NEUTRAL
    momentum_5d: float = 0.0        # 5日动量
    money_flow: str = ""            # 资金流向方向
    signal_count: int = 0           # 板块内信号数


@dataclass
class StockSignal:
    """个股信号 — 底层"""
    symbol: str = ""
    name: str = ""
    signal_type: str = ""           # buy / sell / hold
    confidence: float = 0.0         # 0-1 置信度
    trigger_reason: str = ""        # 触发原因
    buffett_verdict: str = ""       # 巴菲特层判断
    timestamp: str = ""


# =====================================================================
# 2. 反馈回路 (Feedback Loop)
# =====================================================================

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
    issues: List[str] = field(default_factory=list)
    adjustments: List[str] = field(default_factory=list)
    # 是否触发熔断
    circuit_breaker: bool = False
    circuit_reason: str = ""


def generate_feedback(
    trades: List[TradeRecord],
    current_positions: List[StockSignal],
) -> FeedbackReport:
    """
    反馈回路核心：分析交易结果，生成调整建议
    """
    cfg = _load_config()["feedback"]
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
        fb_cfg = _load_config()["feedback"]
        min_win_rate = float(fb_cfg.get("min_win_rate", 0.35))
        min_trades_for_review = int(fb_cfg.get("min_trades_for_review", 10))
    except Exception:
        min_win_rate = 0.35
        min_trades_for_review = 10

    if report.win_rate < min_win_rate and report.total_trades >= min_trades_for_review:
        report.adjustments.append(f"胜率{report.win_rate:.1%}过低，建议调高置信度阈值")

    return report


# =====================================================================
# 3. 自适应机制 (Adaptive)
# =====================================================================

def detect_market_regime(
    index_data: dict = None,  # 指数数据 {symbol: df}，不传则自动拉取
    window: int = 60,
    symbol: str = "sh000001",
) -> MarketRegime:
    """
    市场状态检测：基于均线排列、波动率和趋势强度
    不传 index_data 时自动从 AKShare 拉取上证指数数据
    """
    import pandas as pd

    # 自动拉取真实数据
    if index_data is None or symbol not in index_data:
        try:
            import sys, os
            from data.fetcher import get_index_daily
            df = get_index_daily(symbol, force_refresh=False)
        except Exception:
            return MarketRegime.UNKNOWN
    else:
        df = index_data.get(symbol)

    if df is None or len(df) < max(window, 60):
        return MarketRegime.UNKNOWN

    recent = df.tail(window)
    close = recent["close"].values if "close" in df.columns else recent["收盘"].values

    # 均线计算
    ma5 = close[-5:].mean()
    ma10 = close[-10:].mean() if len(close) >= 10 else close.mean()
    ma20 = close[-20:].mean()
    ma60 = close[-60:].mean() if len(close) >= 60 else close.mean()

    # MA200 用于长期趋势
    ma200 = close.mean() if len(close) >= 200 else close[-window:].mean()

    # 多头排列: price > ma5 > ma10 > ma20 > ma60
    # 空头排列: price < ma5 < ma10 < ma20 < ma60
    current = close[-1]
    if current > ma5 > ma20 > ma60:
        return MarketRegime.BULL
    elif current < ma5 < ma20 < ma60:
        return MarketRegime.BEAR
    else:
        return MarketRegime.SIDEWAYS


def adaptive_params(regime: MarketRegime) -> Dict[str, float]:
    """
    根据市场状态自适应调整参数
    优先从 config/settings.yaml → cybernetics.adaptive.{regime} 读取
    """
    # 尝试从配置加载
    try:
        cfg = _load_config()["adaptive"]
        regime_key = regime.value  # "bull", "sideways", "bear"
        if regime_key in cfg:
            entry = cfg[regime_key]
            return {
                "position_size": float(entry["position_size"]),
                "stop_loss": float(entry["stop_loss"]),
                "confidence_threshold": float(entry["confidence_threshold"]),
                "max_positions": int(entry["max_positions"]),
            }
    except Exception:
        pass

    # 配置不可用时的硬编码回退
    params = {
        MarketRegime.BULL: {
            "position_size": 0.30,      # 牛市：单票可到30%
            "stop_loss": -0.08,         # 止损：-8%
            "confidence_threshold": 0.60,
            "max_positions": 8,
        },
        MarketRegime.SIDEWAYS: {
            "position_size": 0.15,
            "stop_loss": -0.05,
            "confidence_threshold": 0.75,
            "max_positions": 5,
        },
        MarketRegime.BEAR: {
            "position_size": 0.05,
            "stop_loss": -0.03,
            "confidence_threshold": 0.85,
            "max_positions": 2,
        },
    }
    return params.get(regime, params[MarketRegime.SIDEWAYS])


# =====================================================================
# 4. 协调器 (Orchestrator)
# =====================================================================

class QuantOrchestrator:
    """
    量化系统协调器 — 连接巴菲特约束层和控制论运行层

    运行流程:
    1. 检测市场状态（控制论-多层递阶）
    2. 加载自适应参数（控制论-自适应）
    3. 股票池过滤（巴菲特-能力圈）
    4. 基本面筛选（巴菲特-护城河+安全边际）
    5. 技术信号生成（信号系统）
    6. 反馈评估（控制论-反馈回路）
    """

    def __init__(self):
        self.regime = MarketRegime.UNKNOWN
        self.params = {}
        self.trade_history: List[TradeRecord] = []
        self.market_snapshot: MarketContext = None

    def set_regime(self, index_data: dict = None):
        """设置当前市场状态。不传 index_data 时自动拉取真实数据。"""
        self.regime = detect_market_regime(index_data)
        self.params = adaptive_params(self.regime)

    def detect(self) -> MarketContext:
        """
        运行完整市场检测，返回 MarketContext 快照。
        自动拉取真实上证指数数据，计算均线排列和趋势。
        """
        import pandas as pd
        from datetime import datetime
        import sys, os

        # 获取真实指数数据
        from data.fetcher import get_index_daily
        df = get_index_daily("sh000001", force_refresh=False)

        if df is None or len(df) < 60:
            self.market_snapshot = MarketContext(regime=MarketRegime.UNKNOWN, date=datetime.now().strftime("%Y-%m-%d"))
            return self.market_snapshot

        close = df["close"].values if "close" in df.columns else df["收盘"].values
        volume = df["volume"].values if "volume" in df.columns else None

        current = close[-1]
        ma5 = close[-5:].mean()
        ma10 = close[-10:].mean()
        ma20 = close[-20:].mean()
        ma60 = close[-60:].mean() if len(close) >= 60 else close.mean()

        # 趋势判断
        if current > ma5 > ma20 > ma60:
            ma_trend = "多头排列 ↑"
            self.regime = MarketRegime.BULL
        elif current < ma5 < ma20 < ma60:
            ma_trend = "空头排列 ↓"
            self.regime = MarketRegime.BEAR
        else:
            ma_trend = "震荡/横盘 ↔"
            self.regime = MarketRegime.SIDEWAYS

        self.params = adaptive_params(self.regime)

        # 量能趋势 — 阈值从 config 读取，fallback 1.2/0.8
        vol_5 = volume[-5:].mean() if volume is not None else 0
        vol_20 = volume[-20:].mean() if volume is not None and len(volume) >= 20 else vol_5

        try:
            det_cfg = _load_config()["adaptive"]["detection"]
            vol_expand = float(det_cfg.get("volume_expansion", 1.2))
            vol_contract = float(det_cfg.get("volume_contraction", 0.8))
            breadth_w = int(det_cfg.get("breadth_window", 20))
        except Exception:
            vol_expand = 1.2
            vol_contract = 0.8
            breadth_w = 20

        vol_trend = "放量" if vol_5 > vol_20 * vol_expand else ("缩量" if vol_5 < vol_20 * vol_contract else "正常")

        # 涨跌比（从OHLC近似: 收盘>开盘为涨）
        lookback = min(breadth_w, len(close))
        start = max(1, len(close) - lookback)
        up_count = sum(1 for i in range(start, len(close)) if close[i] > close[i-1])
        breadth = up_count / (len(close) - start) if (len(close) - start) > 0 else 0.5

        self.market_snapshot = MarketContext(
            regime=self.regime,
            index_ma_trend=f"MA5:{ma5:.0f} MA20:{ma20:.0f} MA60:{ma60:.0f} → {ma_trend}",
            volume_trend=vol_trend,
            breadth=breadth,
            date=datetime.now().strftime("%Y-%m-%d"),
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
