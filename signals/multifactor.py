"""
多因子打分引擎 — 融合五维数据

质量分(35%) + 估值分(25%) + 技术分(15%) + 市场分(10%) + 行业动量(15%)
每月重打分, 买Top-N, 卖跌出Top-N的
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from core.settings import get_settings


def _load_config() -> dict:
    return get_settings()


CONFIG = _load_config()
MFC = CONFIG.get("signals", {}).get("multifactor", {})


class MultiFactorScorer:
    """多因子打分器"""

    def __init__(self, regime: str = "sideways"):
        self.regime = regime

    @staticmethod
    def _bounded(v: float) -> float:
        return min(100.0, max(0.0, float(v)))

    def score_components(self, factors: dict) -> dict:
        """
        返回五维组件分 + 综合分 (0-100).

        factors = {
            "buffett_score": 0-100,   # 巴菲特综合评分
            "safety_margin": -1.0~1.0, # 安全边际%
            "roe_5y": 0.0~1.0,         # 5年平均ROE
            "roe_trend": "up/down/flat", # ROE趋势
            "momentum_1m": float,      # 1月动量
            "momentum_3m": float,      # 3月动量
            "volatility": float,       # 波动率
            "sector": str,             # 板块类型
            "symbol": str,             # 股票代码 (用于行业动量查表)
        }
        """
        quality = self._bounded(self._quality_score(factors))
        valuation = self._bounded(self._valuation_score(factors))
        technical = self._bounded(self._technical_score(factors))
        market = self._bounded(self._market_score(factors))
        industry = self._bounded(self._industry_score(factors))

        w = MFC.get("weights", {})
        total = (quality * w.get("quality", 0.35)
                 + valuation * w.get("valuation", 0.25)
                 + technical * w.get("technical", 0.15)
                 + market * w.get("market", 0.10)
                 + industry * w.get("industry_momentum", 0.15))
        return {
            "quality": round(quality, 2),
            "valuation": round(valuation, 2),
            "technical": round(technical, 2),
            "market": round(market, 2),
            "industry": round(industry, 2),
            "total": round(self._bounded(total), 2),
        }

    def score(self, factors: dict) -> float:
        """综合打分 (0-100)."""
        return self.score_components(factors)["total"]

    def _quality_score(self, f: dict) -> float:
        """质量分: 巴菲特基本面"""
        qc = MFC.get("quality", {})
        buffett = f.get("buffett_score", 50)
        roe = f.get("roe_5y", 0) * 100  # 转百分比

        # ROE趋势加分
        trend_bonus = 0
        trend = f.get("roe_trend", "flat")
        if trend == "up":
            trend_bonus = qc.get("trend_bonus_up", 5)
        elif trend == "down":
            trend_bonus = qc.get("trend_bonus_down", -5)

        # ROE越高越好，但边际递减
        roe_cap = qc.get("roe_cap", 30.0)
        roe_mult = qc.get("roe_multiplier", 1.2)
        roe_score = min(roe_cap, roe * roe_mult)

        buffett_w = qc.get("buffett_weight", 0.6)
        return buffett * buffett_w + roe_score * 1.0 + trend_bonus

    def _valuation_score(self, f: dict) -> float:
        """估值分: 安全边际越大越好"""
        vc = MFC.get("valuation", {})
        margin = f.get("safety_margin", 0)

        t_dv = vc.get("tier_deep_value", 0.50)
        t_mv = vc.get("tier_moderate_value", 0.30)
        t_sv = vc.get("tier_slight_value", 0.15)
        s_dv = vc.get("score_deep", 80)
        s_mv = vc.get("score_moderate", 60)
        s_sv = vc.get("score_slight", 40)

        if margin >= t_dv:
            return s_dv + (margin - t_dv) / (1.0 - t_dv) * (100 - s_dv)
        elif margin >= t_mv:
            return s_mv + (margin - t_mv) / (t_dv - t_mv) * (s_dv - s_mv)
        elif margin >= t_sv:
            return s_sv + (margin - t_sv) / (t_mv - t_sv) * (s_mv - s_sv)
        elif margin >= 0:
            return 10 + margin / t_sv * (s_sv - 10)
        else:
            # 溢价 → 扣分
            return max(0, 10 + margin * 20)

    def _technical_score(self, f: dict) -> float:
        """技术分: 动量 + 波动率"""
        tc = MFC.get("technical", {})
        mom_1m = f.get("momentum_1m", 0)
        mom_3m = f.get("momentum_3m", 0)
        # Prefer intermediate momentum with the most recent month skipped.
        # This follows the mature 3-12 month momentum convention and avoids
        # over-weighting short-term reversal noise.
        mom_3m_skip = f.get("momentum_3m_skip_1m", mom_3m)
        mom_6m_skip = f.get("momentum_6m_skip_1m", mom_3m)
        trend_strength = f.get("trend_strength", 0)
        volatility = f.get("volatility", tc.get("default_volatility", 0.30))

        # 动量: 正动量好但不要追涨(太高反而回调风险)
        mom_composite = mom_3m_skip * 0.35 + mom_6m_skip * 0.65
        mom_strong = tc.get("mom_strong", 0.15)
        if mom_composite > mom_strong:
            mom_score = 40  # 涨太多，等回调
        elif mom_composite > 0:
            mom_score = 40 + mom_composite * tc.get("mom_multiplier_strong", 400)
        elif mom_composite > -0.10:
            mom_score = 40 + mom_composite * tc.get("mom_multiplier_normal", 200)
        else:
            mom_score = 20  # 跌太多，观望

        if trend_strength < -0.05:
            mom_score *= 0.55
        elif trend_strength > 0:
            mom_score += min(10, trend_strength * 100)

        # 低波动加分
        vol_max = tc.get("vol_max_score", 30)
        vol_penalty = tc.get("vol_penalty_mult", 100)
        vol_score = max(0, vol_max - volatility * vol_penalty)

        w_mom = tc.get("weight_momentum", 0.6)
        w_vol = tc.get("weight_volatility", 0.4)
        return min(100, mom_score * w_mom + vol_score * w_vol)

    def _market_score(self, f: dict) -> float:
        """市场环境分: 当前市场状态下的板块适配"""
        mc = MFC.get("market", {})
        sector = f.get("sector", "consumer")

        # 从config读取板块加分表，回落至原始硬编码值
        if self.regime == "bull":
            cfg_bonus = mc.get("bull", {})
            sector_bonus = cfg_bonus.get(sector, {
                "bank": 15, "insurance": 10, "securities": 20
            }.get(sector, 5))
        elif self.regime == "bear":
            cfg_bonus = mc.get("bear", {})
            sector_bonus = cfg_bonus.get(sector, {
                "bank": 25, "consumer": 20
            }.get(sector, 5))
        else:
            cfg_bonus = mc.get("sideways", {})
            sector_bonus = cfg_bonus.get(sector, 10)  # 震荡均等

        return min(100, 50 + sector_bonus)

    def _industry_score(self, f: dict) -> float:
        """行业动量分: 所属申万行业近期动量映射到个股。

        从 sector_performance 快照读取行业 20d/60d 动量，
        正动量行业加分，负动量行业减分。
        """
        symbol = f.get("symbol", "")
        sector = f.get("sector", "")
        if not symbol and not sector:
            return 50.0

        # Lazy-load sector momentum data (module-level cache)
        sector_ret = _get_sector_momentum()
        if not sector_ret:
            return 50.0

        # Look up this stock's sector name
        sector_name = _lookup_sector(symbol, sector)
        if not sector_name or sector_name not in sector_ret:
            return 50.0

        ret_20d = sector_ret[sector_name].get("return_20d", 0)
        ret_60d = sector_ret[sector_name].get("return_60d", 0)

        ic = MFC.get("industry", {})
        # Composite: 20d (faster) + 60d (slower trend confirmation)
        mom = ret_20d * ic.get("weight_20d", 0.6) + ret_60d * ic.get("weight_60d", 0.4)

        # Map momentum to score: 0% → 50 base, each 1% momentum → ~2.5 points
        base = ic.get("base", 50.0)
        mult = ic.get("multiplier", 250.0)
        cap_low = ic.get("cap_low", 20.0)
        cap_high = ic.get("cap_high", 80.0)
        scored = base + mom * mult
        return max(cap_low, min(cap_high, scored))


# ── Sector momentum helpers (module-level cache) ──

_sector_ret_cache: dict | None = None
_symbol_sector_cache: dict | None = None


def _get_sector_momentum() -> dict:
    """Load latest sector performance, indexed by sector_name → {return_20d, return_60d}."""
    global _sector_ret_cache
    if _sector_ret_cache is not None:
        return _sector_ret_cache

    try:
        from data.datahub import get_datahub
        hub = get_datahub()
        candidates = []
        try:
            root = hub.dimension_root("sector_performance_snapshot")
            if root.exists():
                candidates = sorted(root.glob("*.parquet"), reverse=True)
        except Exception:
            pass
        if not candidates:
            legacy = hub.store_root / "sector"
            if legacy.exists():
                candidates = sorted(legacy.glob("sector_performance_*.parquet"), reverse=True)
        if not candidates:
            _sector_ret_cache = {}
            return _sector_ret_cache

        df = hub.read_parquet(candidates[0], default=pd.DataFrame())
        if df.empty or "sector_name" not in df.columns:
            _sector_ret_cache = {}
            return _sector_ret_cache

        _sector_ret_cache = {}
        for _, row in df.iterrows():
            _sector_ret_cache[str(row["sector_name"])] = {
                "return_1d": float(row.get("return_1d", 0)),
                "return_5d": float(row.get("return_5d", 0)),
                "return_20d": float(row.get("return_20d", 0)),
                "return_60d": float(row.get("return_60d", 0)),
            }
        return _sector_ret_cache
    except Exception:
        _sector_ret_cache = {}
        return _sector_ret_cache


def _lookup_sector(symbol: str, fallback_sector: str) -> str:
    """Map symbol → sector_name using sector_membership snapshot."""
    global _symbol_sector_cache
    if _symbol_sector_cache is not None and symbol in _symbol_sector_cache:
        return _symbol_sector_cache[symbol]
    if _symbol_sector_cache is not None:
        return fallback_sector

    try:
        from data.datahub import get_datahub
        hub = get_datahub()
        mem_path = hub.dimension_path("sector_membership")
        if not mem_path.exists():
            _symbol_sector_cache = {}
            return fallback_sector

        mem = hub.read_parquet(mem_path, default=pd.DataFrame())
        if mem.empty:
            _symbol_sector_cache = {}
            return fallback_sector

        _symbol_sector_cache = dict(zip(mem["symbol"], mem["sector_name"]))
    except Exception:
        _symbol_sector_cache = {}

    return _symbol_sector_cache.get(symbol, fallback_sector) if _symbol_sector_cache else fallback_sector


def compute_momentum(df: pd.DataFrame, periods: List[int], skip_recent: int = 0) -> Dict[int, float]:
    """计算多周期动量，可跳过最近 N 个交易日以降低短期反转噪声。"""
    if len(df) < max(periods) + skip_recent + 1:
        return {p: 0 for p in periods}

    result = {}
    for p in periods:
        if len(df) >= p + skip_recent + 1:
            end_idx = -1 - skip_recent if skip_recent else -1
            start_idx = end_idx - p
            base = df["close"].iloc[start_idx]
            result[p] = (df["close"].iloc[end_idx] / base - 1) if base else 0
        else:
            result[p] = 0
    return result


def compute_volatility(df: pd.DataFrame, window: int = 20) -> float:
    """计算年化波动率"""
    if len(df) < window + 1:
        return 0.30
    returns = df["close"].pct_change().dropna().tail(window)
    return returns.std() * np.sqrt(252)


def compute_trend_strength(df: pd.DataFrame, window: int = 120) -> float:
    """当前价格相对中长期均线的强弱。"""
    if len(df) < window:
        return 0.0
    ma = df["close"].tail(window).mean()
    return float(df["close"].iloc[-1] / ma - 1) if ma else 0.0


def compute_roe_trend(roe_history: List[float]) -> str:
    """判断ROE趋势"""
    if len(roe_history) < 3:
        return "flat"
    recent = roe_history[-3:]
    if recent[-1] > recent[0] * 1.05:
        return "up"
    elif recent[-1] < recent[0] * 0.95:
        return "down"
    return "flat"
