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
from typing import Any, List, Dict, Optional, Sequence
from enum import Enum
from datetime import datetime
import math
import os
import time

from cybernetics.regime import MarketRegime, detect_trend_regime, to_market_regime
from cybernetics.regime_policy import PRODUCTION_REGIME_POLICY
from cybernetics.regime_scoring import (
    breadth_strength as _score_breadth_strength,
    classify_regime_value,
    clamp as _score_clamp,
    compose_regime_score,
    volume_strength as _score_volume_strength,
)
from cybernetics.regime_state import RegimeTransitionTracker
from core.settings import get_section


# ----- 配置 -----
_config = None


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
        from data.datahub import get_datahub

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


def _regime_observation_key(bench, breadth: "MarketBreadth", volume: "MarketVolume") -> str:
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


# =====================================================================
# 1. 多层递阶结构 (Multi-level Hierarchy)
# =====================================================================

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
    raw_regime: MarketRegime = MarketRegime.UNKNOWN
    regime_score: float = 50.0      # 0-100 市场健康度连续评分
    index_ma_trend: str = ""        # 多指数趋势与宽度摘要
    volume_trend: str = ""          # 放量/缩量
    breadth: float = 0.0            # 全市场上涨家数占比
    breadth_detail: Dict[str, Any] = field(default_factory=dict)
    score_components: Dict[str, Any] = field(default_factory=dict)
    regime_state: Dict[str, Any] = field(default_factory=dict)
    date: str = ""

    # === HMM 概率字段 ===
    regime_probs: Dict[str, float] = field(default_factory=dict)
    # {"bull": 0.65, "sideways": 0.25, "bear": 0.10}

    detection_method: str = "rule_based"
    # "hmm" | "rule_based" | "hybrid"

    hmm_confidence: float = 0.0
    # max(regime_probs) — 状态确定性

    hmm_entropy: float = 0.0
    # -sum(p * log(p)) — 状态不确定性

    decision_reason: str = ""
    # Regime engine decision path for observability / Pipeline UI.


@dataclass(frozen=True)
class RegimeDecision:
    raw_regime: MarketRegime
    detection_method: str
    regime_probs: Dict[str, float]
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

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
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

_BREADTH_CACHE: Dict[str, Any] = {"expires_at": 0.0, "snapshot": None}
_VOLUME_CACHE: Dict[str, Any] = {"expires_at": 0.0, "snapshot": None}
_REGIME_TRACKER: Optional[RegimeTransitionTracker] = None
_REGIME_TRACKER_PATH: Optional[str] = None

def _get_regime_indexes() -> list[tuple]:
    """Read regime index weights from config, fallback to defaults."""
    from core.settings import get_section
    cfg = get_section("cybernetics.regime_indexes", {}) or {}
    _INDEX_NAMES = {
        "sh000001": "上证综指", "sh000300": "沪深300",
        "sz399001": "深证成指", "sz399006": "创业板指", "sh000905": "中证500",
    }
    defaults = {"sh000001": 0.25, "sh000300": 0.25, "sz399001": 0.20, "sz399006": 0.15, "sh000905": 0.15}
    merged = {**defaults, **cfg}
    return [(k, _INDEX_NAMES.get(k, k), v) for k, v in merged.items()]


# Module-level cache, refreshed lazily
_REGIME_INDEXES: list[tuple] | None = None


def _regime_indexes() -> list[tuple]:
    global _REGIME_INDEXES
    if _REGIME_INDEXES is None:
        _REGIME_INDEXES = _get_regime_indexes()
    return _REGIME_INDEXES


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return _score_clamp(value, lower, upper)


def _frame_close_volume(df):
    """Return a sorted OHLCV-like frame with numeric close/volume columns."""
    import pandas as pd

    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["date", "close", "volume"])

    data = df.copy()
    data.columns = [str(c).lower() for c in data.columns]
    if "close" not in data.columns and "收盘" in df.columns:
        data["close"] = df["收盘"]
    if "volume" not in data.columns and "成交量" in df.columns:
        data["volume"] = df["成交量"]

    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).sort_values("date")
    elif data.index.name:
        data = data.reset_index().rename(columns={data.index.name: "date"})
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).sort_values("date")

    data["close"] = pd.to_numeric(data.get("close"), errors="coerce")
    if "volume" in data.columns:
        data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
    return data.dropna(subset=["close"]).reset_index(drop=True)


def _stock_daily_files() -> list:
    from data.datahub import get_datahub

    daily_dir = get_datahub().store_path("stock") / "daily"
    if not daily_dir.exists():
        return []
    return sorted(daily_dir.glob("*.parquet"))


def _stock_daily_source_sql(files: Optional[Sequence[Any]] = None) -> Optional[str]:
    if files is None:
        from data.datahub import get_datahub

        daily_dir = get_datahub().store_path("stock") / "daily"
        if not daily_dir.exists():
            return None
        return "'" + str(daily_dir / "*.parquet").replace("'", "''") + "'"

    paths = [str(path).replace("'", "''") for path in files]
    if not paths:
        return None
    return "[" + ", ".join(f"'{path}'" for path in paths) + "]"


def _compute_full_market_breadth_duckdb(files: Optional[Sequence[Any]] = None) -> Optional[MarketBreadth]:
    try:
        import duckdb
    except Exception:
        return None

    source_sql = _stock_daily_source_sql(files)
    if source_sql is None:
        return MarketBreadth()

    query = f"""
    with ranked as (
      select
        filename,
        cast(date as varchar) as trade_date,
        cast(close as double) as close,
        row_number() over(partition by filename order by date desc) as rn
      from read_parquet({source_sql}, filename=true)
      where close is not null
    ), agg as (
      select
        filename,
        max(case when rn = 1 then trade_date end) as as_of,
        max(case when rn = 1 then close end) as last_close,
        max(case when rn = 2 then close end) as prev_close,
        avg(case when rn <= 20 then close end) as ma20,
        avg(case when rn <= 60 then close end) as ma60,
        avg(case when rn <= 120 then close end) as ma120,
        count(case when rn <= 20 then 1 end) as n20,
        count(case when rn <= 60 then 1 end) as n60,
        count(case when rn <= 120 then 1 end) as n120
      from ranked
      where rn <= 130
      group by filename
    )
    select
      count(*) filter(where last_close is not null and prev_close is not null and prev_close > 0) as sample_size,
      count(*) filter(where last_close > prev_close and prev_close > 0) as up_count,
      count(*) filter(where last_close < prev_close and prev_close > 0) as down_count,
      count(*) filter(where last_close = prev_close and prev_close > 0) as unchanged_count,
      count(*) filter(where n20 >= 20 and last_close > ma20) as above_ma20,
      count(*) filter(where n20 >= 20) as eligible_ma20,
      count(*) filter(where n60 >= 60 and last_close > ma60) as above_ma60,
      count(*) filter(where n60 >= 60) as eligible_ma60,
      count(*) filter(where n120 >= 120 and last_close > ma120) as above_ma120,
      count(*) filter(where n120 >= 120) as eligible_ma120,
      max(as_of) as as_of
    from agg
    """

    try:
        row = duckdb.connect(database=":memory:").execute(query).fetchone()
    except Exception:
        return None

    if not row:
        return MarketBreadth()

    (
        sample_size,
        up_count,
        down_count,
        unchanged_count,
        above_ma20,
        eligible_ma20,
        above_ma60,
        eligible_ma60,
        above_ma120,
        eligible_ma120,
        as_of,
    ) = row

    sample_size = int(sample_size or 0)
    up_count = int(up_count or 0)
    down_count = int(down_count or 0)
    unchanged_count = int(unchanged_count or 0)
    traded = up_count + down_count + unchanged_count

    return MarketBreadth(
        advance_ratio=(up_count / traded) if traded else 0.5,
        above_ma20=(int(above_ma20 or 0) / int(eligible_ma20)) if eligible_ma20 else 0.5,
        above_ma60=(int(above_ma60 or 0) / int(eligible_ma60)) if eligible_ma60 else 0.5,
        above_ma120=(int(above_ma120 or 0) / int(eligible_ma120)) if eligible_ma120 else 0.5,
        sample_size=sample_size,
        up_count=up_count,
        down_count=down_count,
        unchanged_count=unchanged_count,
        as_of=str(as_of)[:10] if as_of else "",
    )


def _read_breadth_observation(path) -> Optional[Dict[str, Any]]:
    import pandas as pd

    try:
        try:
            df = pd.read_parquet(path, columns=["date", "close"])
        except Exception:
            df = pd.read_parquet(path, columns=["close"])
    except Exception:
        return None

    data = _frame_close_volume(df)
    if len(data) < 2:
        return None

    closes = data["close"].tail(130)
    if len(closes) < 2:
        return None

    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    if not math.isfinite(last) or not math.isfinite(prev) or prev <= 0:
        return None

    result = {
        "last": last,
        "prev": prev,
        "direction": 1 if last > prev else (-1 if last < prev else 0),
        "above_ma20": False,
        "above_ma60": False,
        "above_ma120": False,
        "has_ma20": False,
        "has_ma60": False,
        "has_ma120": False,
        "as_of": "",
    }

    if "date" in data.columns and len(data):
        result["as_of"] = str(data["date"].iloc[-1])[:10]

    for window in (20, 60, 120):
        if len(closes) >= window:
            ma = float(closes.tail(window).mean())
            result[f"has_ma{window}"] = math.isfinite(ma) and ma > 0
            result[f"above_ma{window}"] = bool(result[f"has_ma{window}"] and last > ma)

    return result


def _compute_full_market_breadth(
    files: Optional[Sequence[Any]] = None,
    *,
    use_cache: bool = True,
) -> MarketBreadth:
    """
    Compute full-market A-share breadth from local stock daily parquet files.

    The dashboard calls regime endpoints frequently, so the expensive full scan
    is cached in memory for a short TTL. This still avoids implicit network
    fetches and keeps breadth tied to the local DataHub snapshot.
    """
    now = time.monotonic()
    try:
        det_cfg = _load_config()["adaptive"]["detection"]
        ttl = int(det_cfg.get("breadth_cache_ttl_seconds", 900))
        workers = int(det_cfg.get("breadth_workers", min(8, os.cpu_count() or 4)))
    except Exception:
        ttl = 900
        workers = min(8, os.cpu_count() or 4)

    if use_cache and _BREADTH_CACHE.get("snapshot") is not None and _BREADTH_CACHE.get("expires_at", 0.0) > now:
        return _BREADTH_CACHE["snapshot"]

    source_files = list(files) if files is not None else None
    if source_files is not None and not source_files:
        return MarketBreadth()

    snapshot = _compute_full_market_breadth_duckdb(source_files)
    if snapshot is not None:
        if use_cache:
            _BREADTH_CACHE["snapshot"] = snapshot
            _BREADTH_CACHE["expires_at"] = now + ttl
        return snapshot

    source_files = source_files if source_files is not None else _stock_daily_files()
    if not source_files:
        return MarketBreadth()

    from concurrent.futures import ThreadPoolExecutor

    up_count = down_count = unchanged_count = 0
    above = {20: 0, 60: 0, 120: 0}
    eligible = {20: 0, 60: 0, 120: 0}
    sample_size = 0
    as_of = ""

    max_workers = max(1, min(workers, len(source_files)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for obs in executor.map(_read_breadth_observation, source_files):
            if not obs:
                continue
            sample_size += 1
            if obs["direction"] > 0:
                up_count += 1
            elif obs["direction"] < 0:
                down_count += 1
            else:
                unchanged_count += 1
            for window in (20, 60, 120):
                if obs.get(f"has_ma{window}"):
                    eligible[window] += 1
                    if obs.get(f"above_ma{window}"):
                        above[window] += 1
            if obs.get("as_of"):
                as_of = max(as_of, str(obs["as_of"]))

    traded = up_count + down_count + unchanged_count
    snapshot = MarketBreadth(
        advance_ratio=(up_count / traded) if traded else 0.5,
        above_ma20=(above[20] / eligible[20]) if eligible[20] else 0.5,
        above_ma60=(above[60] / eligible[60]) if eligible[60] else 0.5,
        above_ma120=(above[120] / eligible[120]) if eligible[120] else 0.5,
        sample_size=sample_size,
        up_count=up_count,
        down_count=down_count,
        unchanged_count=unchanged_count,
        as_of=as_of,
    )

    if use_cache:
        _BREADTH_CACHE["snapshot"] = snapshot
        _BREADTH_CACHE["expires_at"] = now + ttl
    return snapshot


def _compute_full_market_volume_duckdb(files: Optional[Sequence[Any]] = None) -> Optional[MarketVolume]:
    try:
        import duckdb
    except Exception:
        return None

    source_sql = _stock_daily_source_sql(files)
    if source_sql is None:
        return MarketVolume()

    query = f"""
    with rows as (
      select
        filename,
        cast(date as date) as trade_date,
        cast(close as double) as close,
        cast(volume as double) as volume,
        coalesce(try_cast(amount as double), try_cast(volume as double) * try_cast(close as double)) as amount,
        lag(cast(close as double)) over(partition by filename order by cast(date as date)) as prev_close
      from read_parquet({source_sql}, filename=true, union_by_name=true)
      where date is not null and close is not null and volume is not null
    ), recent_dates as (
      select distinct trade_date
      from rows
      where amount is not null and amount > 0
      order by trade_date desc
      limit 25
    ), daily as (
      select
        r.trade_date,
        sum(r.amount) as total_amount,
        sum(case when r.close > r.prev_close then r.amount else 0 end) as up_amount,
        sum(case when r.close < r.prev_close then r.amount else 0 end) as down_amount,
        count(*) as sample_size
      from rows r
      join recent_dates d on r.trade_date = d.trade_date
      where r.amount is not null and r.amount > 0 and r.prev_close is not null and r.prev_close > 0
      group by r.trade_date
    ), ranked as (
      select
        *,
        row_number() over(order by trade_date desc) as rn
      from daily
    )
    select
      avg(total_amount) filter(where rn <= 5) as amount_5d,
      avg(total_amount) filter(where rn <= 20) as amount_20d,
      sum(up_amount) filter(where rn <= 5) as up_amount_5d,
      sum(total_amount) filter(where rn <= 5) as total_amount_5d,
      avg(sample_size) filter(where rn <= 5) as sample_size,
      max(trade_date) as as_of
    from ranked
    where rn <= 20
    """

    try:
        row = duckdb.connect(database=":memory:").execute(query).fetchone()
    except Exception:
        return None

    if not row:
        return MarketVolume()

    amount_5d, amount_20d, up_amount_5d, total_amount_5d, sample_size, as_of = row
    amount_5d = float(amount_5d or 0.0)
    amount_20d = float(amount_20d or 0.0)
    up_amount_5d = float(up_amount_5d or 0.0)
    total_amount_5d = float(total_amount_5d or 0.0)

    return MarketVolume(
        amount_ratio_5_20=(amount_5d / amount_20d) if amount_20d > 0 else 1.0,
        up_amount_ratio=(up_amount_5d / total_amount_5d) if total_amount_5d > 0 else 0.5,
        sample_size=int(sample_size or 0),
        amount_5d=amount_5d,
        amount_20d=amount_20d,
        as_of=str(as_of)[:10] if as_of else "",
    )


def _compute_full_market_volume(
    files: Optional[Sequence[Any]] = None,
    *,
    use_cache: bool = True,
) -> MarketVolume:
    now = time.monotonic()
    try:
        det_cfg = _load_config()["adaptive"]["detection"]
        ttl = int(det_cfg.get("breadth_cache_ttl_seconds", 900))
    except Exception:
        ttl = 900

    if use_cache and _VOLUME_CACHE.get("snapshot") is not None and _VOLUME_CACHE.get("expires_at", 0.0) > now:
        return _VOLUME_CACHE["snapshot"]

    source_files = list(files) if files is not None else None
    if source_files is not None and not source_files:
        return MarketVolume()

    snapshot = _compute_full_market_volume_duckdb(source_files)
    if snapshot is None:
        snapshot = MarketVolume()

    if use_cache:
        _VOLUME_CACHE["snapshot"] = snapshot
        _VOLUME_CACHE["expires_at"] = now + ttl
    return snapshot


def _index_trend_strength(df) -> Optional[float]:
    data = _frame_close_volume(df)
    if len(data) < 60:
        return None

    close = data["close"]
    current = float(close.iloc[-1])
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    ma120 = float(close.tail(120).mean()) if len(close) >= 120 else ma60

    checks = [
        current > ma20,
        current > ma60,
        ma20 > ma60,
        current > ma120,
    ]
    if len(close) >= 80:
        prev_ma20 = float(close.iloc[-40:-20].mean())
        checks.append(ma20 > prev_ma20)

    return sum(1 for ok in checks if ok) / len(checks)


def _compute_multi_index_trend(index_frames: Dict[str, Any]) -> tuple[float, Dict[str, float]]:
    weighted = 0.0
    total_weight = 0.0
    detail: Dict[str, float] = {}

    for symbol, _label, weight in _regime_indexes():
        strength = _index_trend_strength(index_frames.get(symbol))
        if strength is None:
            continue
        detail[symbol] = round(strength, 4)
        weighted += strength * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.5, detail
    return weighted / total_weight, detail


def _index_risk_metrics(df) -> Optional[Dict[str, float]]:
    data = _frame_close_volume(df)
    if len(data) < 30:
        return None

    close = data["close"]
    returns = close.pct_change().dropna()
    if len(returns) < 10:
        realized_vol = 0.0
    else:
        realized_vol = float(returns.tail(20).std() * math.sqrt(252))
        if not math.isfinite(realized_vol):
            realized_vol = 0.0

    window = close.tail(60)
    peak = float(window.max())
    current = float(close.iloc[-1])
    drawdown = (current / peak - 1.0) if peak > 0 else 0.0

    vol_score = 1.0 - _clamp((realized_vol - 0.12) / 0.28)
    drawdown_score = 1.0 - _clamp(abs(min(drawdown, 0.0)) / 0.15)
    return {
        "realized_vol_20d": realized_vol,
        "drawdown_60d": drawdown,
        "vol_score": vol_score,
        "drawdown_score": drawdown_score,
    }


def _compute_risk_strength(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
) -> tuple[float, Dict[str, float]]:
    weighted_vol_score = 0.0
    weighted_drawdown_score = 0.0
    weighted_realized_vol = 0.0
    weighted_drawdown = 0.0
    total_weight = 0.0
    worst_drawdown = 0.0
    index_detail: Dict[str, float] = {}

    for symbol, _label, weight in _regime_indexes():
        metrics = _index_risk_metrics(index_frames.get(symbol))
        if not metrics:
            continue
        weighted_vol_score += metrics["vol_score"] * weight
        weighted_drawdown_score += metrics["drawdown_score"] * weight
        weighted_realized_vol += metrics["realized_vol_20d"] * weight
        weighted_drawdown += metrics["drawdown_60d"] * weight
        worst_drawdown = min(worst_drawdown, metrics["drawdown_60d"])
        index_detail[f"risk_vol_{symbol}"] = round(metrics["realized_vol_20d"], 4)
        index_detail[f"risk_drawdown_{symbol}"] = round(metrics["drawdown_60d"], 4)
        total_weight += weight

    if total_weight <= 0:
        vol_health = 0.5
        drawdown_health = 0.5
        weighted_realized_vol = 0.0
        weighted_drawdown = 0.0
    else:
        vol_health = weighted_vol_score / total_weight
        drawdown_health = weighted_drawdown_score / total_weight
        weighted_realized_vol = weighted_realized_vol / total_weight
        weighted_drawdown = weighted_drawdown / total_weight

    traded = breadth.up_count + breadth.down_count + breadth.unchanged_count
    down_ratio = (breadth.down_count / traded) if traded else 0.5
    pressure_raw = (
        0.50 * down_ratio
        + 0.30 * (1.0 - breadth.above_ma20)
        + 0.20 * (1.0 - breadth.above_ma60)
    )
    pressure_health = 1.0 - _clamp((pressure_raw - 0.40) / 0.35)

    strength = 0.50 * drawdown_health + 0.30 * vol_health + 0.20 * pressure_health
    return strength, {
        "risk_drawdown_raw": round(drawdown_health, 4),
        "risk_volatility_raw": round(vol_health, 4),
        "risk_pressure_raw": round(pressure_health, 4),
        "market_down_pressure": round(pressure_raw, 4),
        "market_down_ratio": round(down_ratio, 4),
        "realized_vol_20d": round(weighted_realized_vol, 4),
        "drawdown_60d": round(weighted_drawdown, 4),
        "worst_drawdown_60d": round(worst_drawdown, 4),
        **index_detail,
    }


def _index_volume_confirmation(df) -> Optional[Dict[str, float]]:
    data = _frame_close_volume(df)
    if "volume" not in data.columns or len(data) < 20:
        return None

    volume = data["volume"].dropna()
    if len(volume) < 20:
        return None

    vol_5 = float(volume.tail(5).mean())
    vol_20 = float(volume.tail(20).mean())
    if vol_20 <= 0:
        return None

    vol_ratio = vol_5 / vol_20
    close = data["close"]
    ret_5 = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1.0) if len(close) >= 6 and float(close.iloc[-6]) > 0 else 0.0
    if ret_5 > 0.01:
        strength = 0.5 + (vol_ratio - 1.0) * 0.8
    elif ret_5 < -0.01:
        strength = 0.5 - (vol_ratio - 1.0) * 0.8
    else:
        strength = 0.5 + (vol_ratio - 1.0) * 0.2
    return {
        "strength": _clamp(strength),
        "volume_ratio": vol_ratio,
        "return_5d": ret_5,
    }


def _compute_multi_index_volume(index_frames: Dict[str, Any]) -> tuple[float, Dict[str, float]]:
    weighted = 0.0
    total_weight = 0.0
    detail: Dict[str, float] = {}

    for symbol, _label, weight in _regime_indexes():
        metrics = _index_volume_confirmation(index_frames.get(symbol))
        if not metrics:
            continue
        weighted += metrics["strength"] * weight
        total_weight += weight
        detail[f"volume_ratio_{symbol}"] = round(metrics["volume_ratio"], 4)
        detail[f"volume_ret5_{symbol}"] = round(metrics["return_5d"], 4)

    if total_weight <= 0:
        return 0.5, detail
    return weighted / total_weight, detail


def _compute_volume_strength(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    market_volume: MarketVolume,
) -> tuple[float, str, Dict[str, float]]:
    try:
        det_cfg = _load_config()["adaptive"]["detection"]
        vol_expand = float(det_cfg.get("volume_expansion", 1.2))
        vol_contract = float(det_cfg.get("volume_contraction", 0.8))
    except Exception:
        vol_expand = 1.2
        vol_contract = 0.8

    index_volume, index_detail = _compute_multi_index_volume(index_frames)
    return _score_volume_strength(
        amount_ratio_5_20=market_volume.amount_ratio_5_20,
        advance_ratio=breadth.advance_ratio,
        up_amount_ratio=market_volume.up_amount_ratio,
        index_volume=index_volume,
        sample_size=market_volume.sample_size,
        amount_5d=market_volume.amount_5d,
        amount_20d=market_volume.amount_20d,
        volume_expansion=vol_expand,
        volume_contraction=vol_contract,
        index_detail=index_detail,
    )


def _breadth_strength(breadth: MarketBreadth) -> float:
    return _score_breadth_strength(
        breadth.advance_ratio,
        breadth.above_ma20,
        breadth.above_ma60,
        breadth.above_ma120,
    )


def _compute_regime_score_v2(
    bench_df,
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    market_volume: Optional[MarketVolume] = None,
) -> tuple[float, Dict[str, float]]:
    """Compute validated regime score: trend 30%, breadth 30%, risk 30%, volume 10%."""
    trend_raw, index_trend = _compute_multi_index_trend(index_frames)
    risk_raw, risk_detail = _compute_risk_strength(index_frames, breadth)
    volume_snapshot = market_volume or _compute_full_market_volume()
    volume_raw, _volume_trend, volume_detail = _compute_volume_strength(index_frames, breadth, volume_snapshot)
    breadth_raw = _breadth_strength(breadth)

    return compose_regime_score(
        trend_raw=trend_raw,
        breadth_raw=breadth_raw,
        risk_raw=risk_raw,
        volume_raw=volume_raw,
        sample_size=breadth.sample_size,
        index_trend=index_trend,
        risk_detail=risk_detail,
        volume_detail=volume_detail,
    )


def _classify_regime(score: float, components: Dict[str, float], breadth: MarketBreadth) -> MarketRegime:
    try:
        det_cfg = _detection_config()
        bull_threshold = float(det_cfg.get("regime_bull_threshold", PRODUCTION_REGIME_POLICY.bull_threshold))
        bear_threshold = float(det_cfg.get("regime_bear_threshold", PRODUCTION_REGIME_POLICY.bear_threshold))
        trend_bull = float(det_cfg.get("regime_trend_confirm", PRODUCTION_REGIME_POLICY.trend_confirm))
        trend_bear = float(det_cfg.get("regime_bear_trend_breakdown", PRODUCTION_REGIME_POLICY.bear_trend_breakdown))
        breadth_bull = float(det_cfg.get("breadth_bull_threshold", PRODUCTION_REGIME_POLICY.breadth_confirm))
        breadth_bear = float(det_cfg.get("breadth_bear_threshold", PRODUCTION_REGIME_POLICY.bear_breadth_breakdown))
    except Exception:
        bull_threshold = PRODUCTION_REGIME_POLICY.bull_threshold
        bear_threshold = PRODUCTION_REGIME_POLICY.bear_threshold
        trend_bull = PRODUCTION_REGIME_POLICY.trend_confirm
        trend_bear = PRODUCTION_REGIME_POLICY.bear_trend_breakdown
        breadth_bull = PRODUCTION_REGIME_POLICY.breadth_confirm
        breadth_bear = PRODUCTION_REGIME_POLICY.bear_breadth_breakdown

    trend_raw = components.get("trend_raw", 0.5)
    breadth_raw = components.get("breadth_raw", _breadth_strength(breadth))

    return MarketRegime(
        classify_regime_value(
            score,
            trend_raw=trend_raw,
            breadth_raw=breadth_raw,
            advance_ratio=breadth.advance_ratio,
            bull_threshold=bull_threshold,
            bear_threshold=bear_threshold,
            trend_bull=trend_bull,
            trend_bear=trend_bear,
            breadth_bull=breadth_bull,
            breadth_bear=breadth_bear,
        )
    )


def _hmm_detect(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    volume: MarketVolume,
) -> tuple[Dict[str, float], float, float, MarketRegime]:
    """Run Student-t HMM regime detection.

    Returns (regime_probs, confidence, entropy, raw_regime).
    Raises if model not available or inference fails.
    """
    import math

    import numpy as np

    from cybernetics.features import OBSERVATION_COLUMNS, build_observation_matrix, build_regime_features
    from cybernetics.hmm_engine import HMMConfig, HMMResult, StudentTHMM, load_hmm_model

    # Check model path
    try:
        hmm_cfg = _load_config().get("hmm", {})
        model_path = hmm_cfg.get("model_path", "data/models/regime_hmm")
    except Exception:
        model_path = "data/models/regime_hmm"

    from pathlib import Path
    mp = Path(model_path)
    if not (mp / "params.npz").exists():
        raise FileNotFoundError(f"HMM model not found at {mp}")

    # Build features
    features = build_regime_features(
        index_frames,
        breadth_raw=_score_breadth_strength(
            breadth.advance_ratio, breadth.above_ma20, breadth.above_ma60, breadth.above_ma120
        ),
        breadth_above_ma20=breadth.above_ma20,
        breadth_above_ma60=breadth.above_ma60,
        breadth_above_ma120=breadth.above_ma120,
        amount_ratio_5_20=volume.amount_ratio_5_20,
        advance_ratio=breadth.advance_ratio,
        up_amount_ratio=volume.up_amount_ratio,
        sample_size=breadth.sample_size,
    )
    if features.empty:
        raise ValueError("Feature construction returned empty DataFrame")

    # Load model
    result = load_hmm_model(mp)

    # Build observation for latest day
    obs_cols = hmm_cfg.get("observation_columns", OBSERVATION_COLUMNS)
    obs = build_observation_matrix(features, columns=obs_cols, standardise=True)
    if len(obs) == 0:
        raise ValueError("Observation matrix is empty")

    # Use the last observation
    latest = obs[-1:]  # (1, D)

    # Predict probabilities
    hmm = StudentTHMM(result.config)
    hmm._params = {
        "means": result.means,
        "covars": result.covars,
        "df": result.df,
        "transmat": result.transmat,
        "startprob": result.startprob,
    }
    probs = hmm.predict_proba(latest)[0]  # (3,)

    # Map to regime labels (aligned: 0=bull, 1=sideways, 2=bear)
    regime_probs = {
        "bull": float(probs[0]),
        "sideways": float(probs[1]),
        "bear": float(probs[2]),
    }
    confidence = float(max(probs))
    entropy = -sum(p * math.log(p + 1e-300) for p in probs)

    # Argmax regime
    regime_idx = int(np.argmax(probs))
    regime_map = {0: MarketRegime.BULL, 1: MarketRegime.SIDEWAYS, 2: MarketRegime.BEAR}
    raw_regime = regime_map.get(regime_idx, MarketRegime.SIDEWAYS)

    return regime_probs, confidence, entropy, raw_regime


def _normalise_regime_probs(regime_probs: Dict[str, float] | None) -> Dict[str, float]:
    probs = {
        "bull": float((regime_probs or {}).get("bull", 0.0) or 0.0),
        "sideways": float((regime_probs or {}).get("sideways", 0.0) or 0.0),
        "bear": float((regime_probs or {}).get("bear", 0.0) or 0.0),
    }
    total = sum(v for v in probs.values() if v > 0)
    if total <= 0:
        return {}
    return {key: max(0.0, value) / total for key, value in probs.items()}


def _resolve_regime_decision(
    *,
    rule_raw_regime: MarketRegime,
    hmm_raw_regime: MarketRegime | None,
    regime_probs: Dict[str, float] | None,
    hmm_confidence: float,
    engine: str,
) -> RegimeDecision:
    """Resolve rule/HMM regime into a single raw decision.

    Hybrid policy:
    - rule/HMM agree: use HMM probabilities directly.
    - disagreement and HMM confidence >= 0.80: trust HMM.
    - disagreement and lower confidence: blend HMM probabilities with a rule vote.
    """
    engine = engine if engine in {"hmm", "hybrid", "rule_based"} else "rule_based"
    rule_raw_regime = to_market_regime(rule_raw_regime)
    probs = _normalise_regime_probs(regime_probs)

    if engine == "rule_based":
        return RegimeDecision(rule_raw_regime, "rule_based", {}, "rule_only")

    if not probs or hmm_raw_regime is None:
        return RegimeDecision(rule_raw_regime, "rule_based", {}, "hmm_unavailable_fallback")

    hmm_raw_regime = to_market_regime(hmm_raw_regime)
    if engine == "hmm":
        return RegimeDecision(hmm_raw_regime, "hmm", probs, "hmm_only")

    if hmm_raw_regime == rule_raw_regime:
        return RegimeDecision(hmm_raw_regime, "hmm", probs, "hmm_rule_consensus")

    from core.settings import get_section
    _hmm_override = float((get_section("cybernetics", {}) or {}).get("hmm_confidence_override", 0.80))
    if hmm_confidence >= _hmm_override:
        return RegimeDecision(hmm_raw_regime, "hmm", probs, "hmm_high_confidence_override")

    rule_weight = min(0.50, max(0.20, 1.0 - hmm_confidence))
    hmm_weight = 1.0 - rule_weight
    blended = {key: value * hmm_weight for key, value in probs.items()}
    blended[rule_raw_regime.value] = blended.get(rule_raw_regime.value, 0.0) + rule_weight
    blended = _normalise_regime_probs(blended)
    raw_regime = MarketRegime(max(blended, key=blended.get)) if blended else rule_raw_regime
    return RegimeDecision(raw_regime, "hybrid", blended, "hybrid_low_confidence_blend")


def detect_market_regime(
    index_data: dict = None,  # 指数数据 {symbol: df}，不传则自动拉取
    window: int = 60,
    symbol: str = "sh000001",
) -> MarketRegime:
    """
    市场状态检测：基于均线排列、波动率和趋势强度
    不传 index_data 时自动从 AKShare 拉取上证指数数据
    """
    return detect_trend_regime(index_data=index_data, window=window, symbol=symbol)


def adaptive_params(
    regime: MarketRegime,
    probs: Dict[str, float] | None = None,
) -> Dict[str, float]:
    """
    根据市场状态自适应调整参数。

    如果提供 probs（regime 概率向量），做概率加权：
      position_size = P(bull)*0.30 + P(sideways)*0.15 + P(bear)*0.05
    否则退化到原有的硬分类逻辑。
    """
    regime = to_market_regime(regime)

    # 硬编码的基础参数
    _HARD_PARAMS = {
        MarketRegime.BULL: {
            "position_size": 0.30,
            "stop_loss": -0.08,
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

    # 尝试从配置加载覆盖
    _CFG_PARAMS = {}
    try:
        cfg = _load_config()["adaptive"]
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
        current = float(close.iloc[-1])
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
