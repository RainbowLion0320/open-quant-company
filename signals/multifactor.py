"""
多因子打分引擎 — 融合四维数据

质量分(40%) + 估值分(30%) + 技术分(15%) + 市场分(15%)
每月重打分, 买Top-N, 卖跌出Top-N的
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path
import yaml


def _load_config() -> dict:
    config_path = Path("~/quant-agent/config/settings.yaml").expanduser()
    with open(config_path) as f:
        return yaml.safe_load(f)


CONFIG = _load_config()
MFC = CONFIG.get("signals", {}).get("multifactor", {})


class MultiFactorScorer:
    """多因子打分器"""

    def __init__(self, regime: str = "sideways"):
        self.regime = regime

    def score(self, factors: dict) -> float:
        """
        综合打分 (0-100)
        factors = {
            "buffett_score": 0-100,   # 巴菲特综合评分
            "safety_margin": -1.0~1.0, # 安全边际%
            "roe_5y": 0.0~1.0,         # 5年平均ROE
            "roe_trend": "up/down/flat", # ROE趋势
            "momentum_1m": float,      # 1月动量
            "momentum_3m": float,      # 3月动量
            "volatility": float,       # 波动率
            "sector": str,             # 板块类型
        }
        """
        quality = self._quality_score(factors)
        valuation = self._valuation_score(factors)
        technical = self._technical_score(factors)
        market = self._market_score(factors)

        w = MFC.get("weights", {})
        total = (quality * w.get("quality", 0.40)
                 + valuation * w.get("valuation", 0.30)
                 + technical * w.get("technical", 0.15)
                 + market * w.get("market", 0.15))
        return min(100, max(0, total))

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
        volatility = f.get("volatility", tc.get("default_volatility", 0.30))

        # 动量: 正动量好但不要追涨(太高反而回调风险)
        mom_composite = mom_1m * 0.4 + mom_3m * 0.6
        mom_strong = tc.get("mom_strong", 0.15)
        if mom_composite > mom_strong:
            mom_score = 40  # 涨太多，等回调
        elif mom_composite > 0:
            mom_score = 40 + mom_composite * tc.get("mom_multiplier_strong", 400)
        elif mom_composite > -0.10:
            mom_score = 40 + mom_composite * tc.get("mom_multiplier_normal", 200)
        else:
            mom_score = 20  # 跌太多，观望

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


def compute_momentum(df: pd.DataFrame, periods: List[int]) -> Dict[int, float]:
    """计算多周期动量"""
    if len(df) < max(periods) + 1:
        return {p: 0 for p in periods}

    result = {}
    for p in periods:
        if len(df) >= p:
            result[p] = (df["close"].iloc[-1] / df["close"].iloc[-p] - 1)
        else:
            result[p] = 0
    return result


def compute_volatility(df: pd.DataFrame, window: int = 20) -> float:
    """计算年化波动率"""
    if len(df) < window + 1:
        return 0.30
    returns = df["close"].pct_change().dropna().tail(window)
    return returns.std() * np.sqrt(252)


def rank_stocks(scores: Dict[str, float], top_n: int = 10,
                max_per_sector: int = 3, sectors: Dict[str, str] = None) -> List[str]:
    """
    排名选股
    - top_n: 最多持仓数
    - max_per_sector: 每个板块最多持仓数
    """
    sorted_stocks = sorted(scores.items(), key=lambda x: -x[1])

    selected = []
    sector_counts = {}

    for symbol, score in sorted_stocks:
        if len(selected) >= top_n:
            break
        sec = sectors.get(symbol, "consumer") if sectors else "all"
        cnt = sector_counts.get(sec, 0)
        if cnt < max_per_sector:
            selected.append(symbol)
            sector_counts[sec] = cnt + 1

    return selected


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
