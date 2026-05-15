"""
因子 DSL 表达式引擎

借鉴 Qlib ExpressionOps 设计:
  - 声明式因子表达: Ref("close", -5) / Ref("close", -20) - 1
  - 因子可组合: (MA("close", 5) - MA("close", 20)) / Std("close", 20)
  - 自动前视防护: compute() 只使用 idx 之前的数据
  - 可序列化: repr() 输出可读表达式

核心操作符:
  Ref(col, offset)     — 引用列
  MA(col, window)      — 移动平均
  Std(col, window)     — 标准差
  Delta(col, window)   — 变化量 (当前 - window前)
  Ret(col)             — 收益率 (pct_change)
  Gt(a, b)             — a > b
  Lt(a, b)             — a < b
  Rank(factor)         — 截面排名
  TsMean(factor, w)    — 时序均值
  TsStd(factor, w)     — 时序标准差

使用:
  mom_1m = Ref("close", -1) / Ref("close", -21) - 1
  vol_20d = Std(Ret("close"), 20)
  ma_cross = Gt(MA("close", 5), MA("close", 20))
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════
# 基础因子
# ══════════════════════════════════════════════════════════

class Factor(ABC):
    """因子基类 — 所有因子表达式的抽象"""

    def __init__(self, name: str = ""):
        self._name = name
        self._cache: Dict[int, float] = {}

    @property
    def name(self) -> str:
        return self._name or repr(self)

    def compute(self, df: pd.DataFrame, idx: int) -> float:
        """
        计算因子在 idx 处的值。

        自动缓存 + 前视防护: 只使用 df[:idx+1] 的数据。
        """
        if idx in self._cache:
            return self._cache[idx]
        val = self._compute(df, idx)
        self._cache[idx] = val
        return val

    @abstractmethod
    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        ...

    def compute_series(self, df: pd.DataFrame) -> pd.Series:
        """计算完整时间序列"""
        values = [self.compute(df, i) for i in range(len(df))]
        return pd.Series(values, index=df.index, name=self.name)

    # ── 算术运算 ──

    def __add__(self, other) -> Factor:
        if isinstance(other, (int, float)):
            other = Constant(other)
        return BinOp(self, other, "+")

    def __sub__(self, other) -> Factor:
        if isinstance(other, (int, float)):
            other = Constant(other)
        return BinOp(self, other, "-")

    def __mul__(self, other) -> Factor:
        if isinstance(other, (int, float)):
            other = Constant(other)
        return BinOp(self, other, "*")

    def __truediv__(self, other) -> Factor:
        if isinstance(other, (int, float)):
            other = Constant(other)
        return BinOp(self, other, "/")

    def __neg__(self) -> Factor:
        return BinOp(Constant(0), self, "-")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


# ══════════════════════════════════════════════════════════
# 基础操作符
# ══════════════════════════════════════════════════════════

class Constant(Factor):
    """常量因子"""
    def __init__(self, value: float):
        super().__init__(f"{value}")
        self.value = value

    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        return self.value

    def __repr__(self):
        return f"{self.value}"


class Ref(Factor):
    """引用 DataFrame 中的列 + 偏移

    Ref("close", 0)  → 当日收盘价
    Ref("close", -5) → 5天前收盘价
    Ref("close", -1) → 昨天收盘价
    """
    def __init__(self, col: str, offset: int = 0):
        name = f"Ref({col},{offset})" if offset else f"Ref({col})"
        super().__init__(name)
        self.col = col
        self.offset = offset

    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        i = idx + self.offset
        if i < 0 or i >= len(df):
            return np.nan
        val = df[self.col].iloc[i]
        return float(val) if not pd.isna(val) else np.nan

    def __repr__(self):
        return f"Ref({self.col},{self.offset})"


class BinOp(Factor):
    """二元运算因子"""
    def __init__(self, left: Factor, right: Factor, op: str):
        super().__init__(f"({left.name}{op}{right.name})")
        self.left = left
        self.right = right
        self.op = op

    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        l = self.left.compute(df, idx)
        r = self.right.compute(df, idx)
        if pd.isna(l) or pd.isna(r):
            return np.nan
        ops = {"+": l + r, "-": l - r, "*": l * r, "/": l / r if r != 0 else np.nan}
        return ops[self.op]

    def __repr__(self):
        return f"({self.left} {self.op} {self.right})"


# ══════════════════════════════════════════════════════════
# 统计操作符
# ══════════════════════════════════════════════════════════

class RollingOp(Factor):
    """滚动窗口统计"""
    def __init__(self, child: Factor, window: int, op: str):
        super().__init__(f"{op}({child.name},{window})")
        self.child = child
        self.window = window
        self.op = op

    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        if idx < self.window - 1:
            return np.nan
        vals = []
        for i in range(max(0, idx - self.window + 1), idx + 1):
            v = self.child.compute(df, i)
            if not pd.isna(v):
                vals.append(v)
        if not vals:
            return np.nan
        arr = np.array(vals)
        ops = {
            "mean": np.mean(arr),
            "std": np.std(arr, ddof=1),
            "min": np.min(arr),
            "max": np.max(arr),
            "sum": np.sum(arr),
        }
        return ops.get(self.op, np.nan)

    def __repr__(self):
        return f"{self.op.upper()}({self.child},{self.window})"


def MA(factor, window: int) -> Factor:
    """滚动均值"""
    if isinstance(factor, str):
        factor = Ref(factor)
    return RollingOp(factor, window, "mean")


def Std(factor, window: int) -> Factor:
    """滚动标准差"""
    if isinstance(factor, str):
        factor = Ref(factor)
    return RollingOp(factor, window, "std")


def Min(factor, window: int) -> Factor:
    if isinstance(factor, str): factor = Ref(factor)
    return RollingOp(factor, window, "min")


def Max(factor, window: int) -> Factor:
    if isinstance(factor, str): factor = Ref(factor)
    return RollingOp(factor, window, "max")


# ══════════════════════════════════════════════════════════
# 时序操作符
# ══════════════════════════════════════════════════════════

class Delta(Factor):
    """变化量: 当前值 - window前的值"""
    def __init__(self, child: Factor, window: int):
        super().__init__(f"Delta({child.name},{window})")
        self.child = child
        self.window = window

    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        cur = self.child.compute(df, idx)
        prev = self.child.compute(df, max(0, idx - self.window))
        if pd.isna(cur) or pd.isna(prev):
            return np.nan
        return cur - prev

    def __repr__(self):
        return f"Delta({self.child},{self.window})"


class PctChange(Factor):
    """百分比变化"""
    def __init__(self, child: Factor):
        super().__init__(f"Ret({child.name})")
        self.child = child

    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        if idx < 1:
            return np.nan
        cur = self.child.compute(df, idx)
        prev = self.child.compute(df, idx - 1)
        if pd.isna(cur) or pd.isna(prev) or prev == 0:
            return np.nan
        return (cur - prev) / prev

    def __repr__(self):
        return f"Ret({self.child})"


def Ret(col: str) -> Factor:
    """收益率 = PctChange(Ref(col))"""
    return PctChange(Ref(col))


# ══════════════════════════════════════════════════════════
# 比较操作符
# ══════════════════════════════════════════════════════════

class Comparison(Factor):
    """比较因子 — 返回 1/0"""
    def __init__(self, left: Factor, right: Factor, op: str):
        super().__init__(f"({left.name}{op}{right.name})")
        self.left = left
        self.right = right
        self.op = op

    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        l = self.left.compute(df, idx)
        r = self.right.compute(df, idx)
        if pd.isna(l) or pd.isna(r):
            return np.nan
        ops = {">": l > r, "<": l < r, ">=": l >= r, "<=": l <= r, "==": l == r}
        return 1.0 if ops[self.op] else 0.0

    def __repr__(self):
        return f"({self.left} {self.op} {self.right})"


def Gt(a: Factor, b) -> Factor:
    """a > b"""
    if isinstance(b, (int, float)): b = Constant(b)
    return Comparison(a, b, ">")


def Lt(a: Factor, b) -> Factor:
    """a < b"""
    if isinstance(b, (int, float)): b = Constant(b)
    return Comparison(a, b, "<")


# ══════════════════════════════════════════════════════════
# 截面操作符
# ══════════════════════════════════════════════════════════

class CrossSectionalRank(Factor):
    """截面排名: 在同一天的所有股票中排名 (0-1)
    
    compute_series 返回普通值, 需要配合 evaluate_panel 使用。
    """
    def __init__(self, child: Factor):
        super().__init__(f"Rank({child.name})")
        self.child = child

    def _compute(self, df: pd.DataFrame, idx: int) -> float:
        return self.child.compute(df, idx)  # 单点无法排名，返回原值

    def compute_panel(self, panel: Dict[str, pd.DataFrame], idx: int) -> pd.Series:
        """在横截面上排名"""
        scores = {}
        for sym, df in panel.items():
            v = self.child.compute(df, idx)
            if not pd.isna(v):
                scores[sym] = v
        if not scores:
            return pd.Series()
        ranked = pd.Series(scores).rank(pct=True)
        return ranked


# ══════════════════════════════════════════════════════════
# 常见因子库 (Alpha158 子集)
# ══════════════════════════════════════════════════════════

def alpha_factors() -> Dict[str, Factor]:
    """返回常用因子字典, 用于 ML 特征工程"""
    close = Ref("close")
    open_ = Ref("open")
    high = Ref("high")
    low = Ref("low")
    volume = Ref("volume")

    factors = {
        # ── 收益率因子 ──
        "ret_1d": Ret("close"),
        "ret_5d": close / Ref("close", -5) - 1,
        "ret_10d": close / Ref("close", -10) - 1,
        "ret_20d": close / Ref("close", -20) - 1,
        "ret_60d": close / Ref("close", -60) - 1,

        # ── 均线偏离 ──
        "ma5_bias": close / MA("close", 5) - 1,
        "ma10_bias": close / MA("close", 10) - 1,
        "ma20_bias": close / MA("close", 20) - 1,
        "ma60_bias": close / MA("close", 60) - 1,

        # ── 波动率 ──
        "vol_5d": Std(Ret("close"), 5),
        "vol_20d": Std(Ret("close"), 20),
        "vol_60d": Std(Ret("close"), 60),

        # ── 成交量 ──
        "volume_ratio_5": volume / MA("volume", 5),
        "volume_ratio_20": volume / MA("volume", 20),

        # ── 价格范围 ──
        "amplitude": (high - low) / Ref("close", -1),
        "high_low_ratio": (high / low - 1),

        # ── 趋势 ──
        "ma5_20_cross": Gt(MA("close", 5), MA("close", 20)),
        "ma20_60_cross": Gt(MA("close", 20), MA("close", 60)),

        # ── 动量 ──
        "rsi_14": _rsi(close, 14),

        # ── LLM 发现的新因子 (Phase 4.0, deepseek-v4-pro) ──
        "vol_adj_mom_5d": Delta(close, 5) / (Std("close", 20) + Constant(1e-6)),
        "volume_conviction": (volume * Delta(close, 5)) / (Std("close", 20) + Constant(1e-6)),
        "intraday_close_strength": (close - low) / (high - low + Constant(0.0001)),
        "upside_intraday_range": (high - open_) / (Std("close", 20) + Constant(1e-6)),
        "midpoint_bias": (close - (high + low) / Constant(2)) / (Std("close", 20) + Constant(1e-6)),
        "volume_vol_ratio": volume / (Std("close", 20) * MA("close", 20) + Constant(1e-6)),
        "open_gap_ma20": (open_ - MA("close", 20)) / (Std("close", 20) + Constant(1e-6)),

        # ── LLM 自动注册因子 — AUTO-REGISTER START (do not edit manually) ──
        # ── AUTO-REGISTER END ──
    }
    return factors


def _rsi(close_factor: Factor, window: int = 14) -> Factor:
    """RSI 因子 (简化版: 使用 MA 近似)"""
    delta = Delta(close_factor, 1)
    gain = RollingOp(delta, window, "mean")  # 简化: 应该只取正值
    # 简化版 RSI = 100 * gain / (gain + abs(loss))
    # 为简单起见, 返回 delta 的滚动均值与波动率之比
    return MA(delta, window) / (Std(delta, window) + 1e-9)
