"""
策略基类 + 接口定义

借鉴 Qlib BaseStrategy 设计:
  - score(): 对单只股票在当前时刻打分
  - should_rebalance(): 判断当前是否调仓日
  - get_positions(): 从评分 + 当前持仓生成目标仓位

所有策略必须继承 BaseStrategy，统一注册、测试、对比。
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pandas as pd


class BaseStrategy(ABC):
    """量化策略基类"""

    # ── 元数据 ──
    name: str = "base"
    label: str = "Base Strategy"
    description: str = ""

    def __init__(self):
        self._last_rebalance_month: int = -1

    # ── 核心接口 ──

    @abstractmethod
    def score(
        self,
        symbol: str,
        prices: pd.Series,
        idx: int,
        regime: str,
        **kwargs,
    ) -> float:
        """
        对单只股票在当前时刻打分 (0-100).

        Args:
            symbol: 股票代码
            prices: OHLCV 价格序列 (DateTimeIndex)
            idx: 当前日期的位置索引
            regime: 市场状态 ("bull"/"bear"/"sideways")
            **kwargs: 策略特定参数

        Returns:
            评分 (0-100), 0 表示不推荐
        """
        ...

    def should_rebalance(
        self,
        dt: datetime,
        regime: str,
        last_regime: Optional[str] = None,
        *args, **kwargs,
    ) -> bool:
        """
        判断是否调仓日。默认每月初调仓。

        子类可覆写实现自定义频率。
        """
        if dt.month != self._last_rebalance_month:
            self._last_rebalance_month = dt.month
            return True
        return False

    def get_positions(
        self,
        scores: Dict[str, float],
        current_holdings: Dict[str, int],
        prices: pd.Series,
        capital: float,
        max_positions: int = 8,
        position_ratio: float = 0.30,
    ) -> Tuple[Dict[str, int], float]:
        """
        从评分生成目标仓位。

        Args:
            scores: {symbol: score} 评分表
            current_holdings: {symbol: shares} 当前持仓
            prices: 当前价格 Series
            capital: 可用资金
            max_positions: 最大持仓数
            position_ratio: 单次调仓资金占比

        Returns:
            (target_holdings, remaining_capital)
        """
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:max_positions]
        target = {s for s, _ in ranked}

        # 卖出不在目标中的
        for sym in list(current_holdings):
            if sym not in target and sym in prices.index:
                capital += current_holdings[sym] * prices[sym]
                del current_holdings[sym]

        # 买入目标中未持有的
        val_per = capital * position_ratio / max(1, len(target))
        for sym in target:
            if sym not in current_holdings and sym in prices.index:
                p = prices[sym]
                if p <= 0:
                    continue
                shares = int(val_per / p // 100) * 100
                if shares >= 100 and shares * p <= capital:
                    current_holdings[sym] = shares
                    capital -= shares * p

        return current_holdings, capital

    # ── 元数据 ──

    @classmethod
    def get_metadata(cls) -> dict:
        return {
            "name": cls.name,
            "label": cls.label,
            "description": cls.description,
        }

    def to_registry_entry(self) -> dict:
        """生成策略注册表条目"""
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "enabled": True,
        }


class StrategyRegistry:
    """策略注册表 — 管理所有已注册策略"""

    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy):
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> Optional[BaseStrategy]:
        return self._strategies.get(name)

    def get_enabled(self) -> List[BaseStrategy]:
        return [s for s in self._strategies.values()]

    def list_names(self) -> List[str]:
        return list(self._strategies.keys())

    def list_metadata(self) -> List[dict]:
        return [s.to_registry_entry() for s in self._strategies.values()]
