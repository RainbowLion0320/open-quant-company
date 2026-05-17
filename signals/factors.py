"""
因子表达式引擎 — 借鉴 Microsoft/qlib 的 operator overloading DSL
⚠️ DEPRECATED: 已被 signals/expression.py 取代。保留仅用于向后兼容测试。
新代码请使用 signals/expression.py。

设计理念:
  因子 = 可组合的表达式树
  RawFactor("roe") > 0.15  →  BinaryOp(RawFactor("roe"), Const(0.15), gt)
  Rolling(Ref("close", 1), 20, "mean") → 20日均线

优势:
  1. 声明式: 因子定义 = 可读的Python表达式, 不需要手写numpy
  2. 可复用: 滚动窗口/滞后/交叉算子天然支持
  3. 可序列化: 表达式树可存入配置
  4. 零依赖: 纯Python + numpy, 不依赖qlib

用法:
  from signals.factors import RawFactor as F, Factor

  roe = F("roe")
  pe = F("pe_ttm")
  gross_margin = F("gross_margin")

  # 优质公司因子: ROE > 15% AND PE < 20 AND 毛利率 > 30%
  quality = (roe > 0.15) & (pe < 20) & (gross_margin > 0.30)

  # 动量因子: 1个月收益率
  close = F("close")
  momentum_1m = (close / Factor.ref(close, 21)) - 1

  # 加载数据
  df = pd.read_parquet("data/cache/...")
  result = quality.load(df)  # pd.Series of bool
"""

import numpy as np
import pandas as pd
from typing import Union, Optional, Callable
from functools import reduce


class Factor:
    """因子基类 — operator overloading 实现表达式树"""

    def load(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    # ── 算术运算 ──
    def __add__(self, other): return BinaryOp(self, _ensure_factor(other), np.add, "+")
    def __radd__(self, other): return BinaryOp(_ensure_factor(other), self, np.add, "+")
    def __sub__(self, other): return BinaryOp(self, _ensure_factor(other), np.subtract, "-")
    def __rsub__(self, other): return BinaryOp(_ensure_factor(other), self, np.subtract, "-")
    def __mul__(self, other): return BinaryOp(self, _ensure_factor(other), np.multiply, "*")
    def __rmul__(self, other): return BinaryOp(_ensure_factor(other), self, np.multiply, "*")
    def __truediv__(self, other): return BinaryOp(self, _ensure_factor(other), np.divide, "/")
    def __rtruediv__(self, other): return BinaryOp(_ensure_factor(other), self, np.divide, "/")
    def __neg__(self): return UnaryOp(self, np.negative, "-")

    # ── 比较运算 ──
    def __gt__(self, other): return BinaryOp(self, _ensure_factor(other), np.greater, ">")
    def __lt__(self, other): return BinaryOp(self, _ensure_factor(other), np.less, "<")
    def __ge__(self, other): return BinaryOp(self, _ensure_factor(other), np.greater_equal, ">=")
    def __le__(self, other): return BinaryOp(self, _ensure_factor(other), np.less_equal, "<=")
    def __eq__(self, other): return BinaryOp(self, _ensure_factor(other), np.equal, "==")

    # ── 逻辑运算 ──
    def __and__(self, other): return BinaryOp(self, _ensure_factor(other), np.logical_and, "&")
    def __or__(self, other): return BinaryOp(self, _ensure_factor(other), np.logical_or, "|")
    def __invert__(self): return UnaryOp(self, np.logical_not, "~")

    # ── 聚合方法 ──
    @staticmethod
    def ref(f: "Factor", n: int) -> "Factor":
        """前值引用: Ref(close, 1) = 昨收"""
        return Ref(f, n)

    @staticmethod
    def rolling(f: "Factor", window: int, method: str) -> "Factor":
        """滚动聚合: Rolling(close, 20, 'mean') = 20日均线"""
        return Rolling(f, window, method)

    @staticmethod
    def delta(f: "Factor", n: int) -> "Factor":
        """N日变化: close - Ref(close, n)"""
        return BinaryOp(f, Factor.ref(f, n), np.subtract, f"delta_{n}")

    @staticmethod
    def pct_change(f: "Factor", n: int) -> "Factor":
        """N日涨跌幅"""
        return BinaryOp(
            BinaryOp(f, Factor.ref(f, n), np.subtract, "diff"),
            Factor.ref(f, n), np.divide, f"pct_{n}"
        )

    @staticmethod
    def slope(f: "Factor", n: int) -> "Factor":
        """N日线性回归斜率"""
        return CrossSectional(f, n, _slope, f"slope_{n}")

    @staticmethod
    def if_else(cond: "Factor", true_val: "Factor", false_val: "Factor") -> "Factor":
        """三元条件"""
        return IfElse(cond, true_val, false_val)

    @staticmethod
    def rank(f: "Factor") -> "Factor":
        """截面排名 (0~1)"""
        return CrossSectional(f, None, lambda x: x.rank(pct=True), "rank")

    @staticmethod
    def zscore(f: "Factor") -> "Factor":
        """截面标准化"""
        return CrossSectional(f, None, lambda x: (x - x.mean()) / x.std(), "zscore")


class RawFactor(Factor):
    """原始因子 — 直接从DataFrame取列"""
    def __init__(self, col: str):
        self.col = col

    def load(self, df: pd.DataFrame) -> pd.Series:
        if self.col not in df.columns:
            raise KeyError(f"Column '{self.col}' not in DataFrame. Available: {list(df.columns)[:20]}")
        return df[self.col]

    def __repr__(self):
        return f"F('{self.col}')"


class Const(Factor):
    """常数因子"""
    def __init__(self, value: Union[float, int]):
        self.value = value

    def load(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(self.value, index=df.index)

    def __repr__(self):
        return str(self.value)


class BinaryOp(Factor):
    """二元运算: left op right"""
    def __init__(self, left: Factor, right: Factor, op: Callable, name: str = ""):
        self.left = left
        self.right = right
        self._op = op
        self._name = name

    def load(self, df: pd.DataFrame) -> pd.Series:
        l = self.left.load(df)
        r = self.right.load(df)
        # 对齐索引
        common = l.index.intersection(r.index)
        return self._op(l.loc[common], r.loc[common])

    def __repr__(self):
        return f"({self.left} {self._name} {self.right})"


class UnaryOp(Factor):
    """一元运算"""
    def __init__(self, factor: Factor, op: Callable, name: str = ""):
        self.factor = factor
        self._op = op
        self._name = name

    def load(self, df: pd.DataFrame) -> pd.Series:
        return self._op(self.factor.load(df))

    def __repr__(self):
        return f"{self._name}({self.factor})"


class Ref(Factor):
    """滞后算子: Ref(close, 5) = 5天前的收盘价"""
    def __init__(self, factor: Factor, n: int):
        self.factor = factor
        self.n = n

    def load(self, df: pd.DataFrame) -> pd.Series:
        return self.factor.load(df).shift(self.n)

    def __repr__(self):
        return f"Ref({self.factor}, {self.n})"


class Rolling(Factor):
    """滚动聚合"""
    _methods = {
        "mean": lambda r: r.mean(),
        "std": lambda r: r.std(),
        "sum": lambda r: r.sum(),
        "min": lambda r: r.min(),
        "max": lambda r: r.max(),
        "median": lambda r: r.median(),
        "skew": lambda r: r.skew(),
        "kurt": lambda r: r.kurt(),
    }

    def __init__(self, factor: Factor, window: int, method: str):
        self.factor = factor
        self.window = window
        self.method = method
        if method not in self._methods:
            raise ValueError(f"Unknown method '{method}'. Available: {list(self._methods)}")

    def load(self, df: pd.DataFrame) -> pd.Series:
        data = self.factor.load(df)
        return self._methods[self.method](data.rolling(self.window, min_periods=max(1, self.window // 2)))

    def __repr__(self):
        return f"Rolling({self.factor}, {self.window}, '{self.method}')"


class CrossSectional(Factor):
    """截面运算（按日期分组处理）"""
    def __init__(self, factor: Factor, window: Optional[int], func: Callable, name: str = ""):
        self.factor = factor
        self.window = window
        self._func = func
        self._name = name

    def load(self, df: pd.DataFrame) -> pd.Series:
        data = self.factor.load(df)
        if self.window:
            return data.groupby(level=0).transform(
                lambda x: x.rolling(self.window, min_periods=1).apply(self._func, raw=False)
            )
        return data.groupby(level=0).transform(self._func)

    def __repr__(self):
        return f"{self._name}({self.factor})"


class IfElse(Factor):
    """三元条件"""
    def __init__(self, cond: Factor, true_val: Factor, false_val: Factor):
        self.cond = cond
        self.true_val = true_val
        self.false_val = false_val

    def load(self, df: pd.DataFrame) -> pd.Series:
        c = self.cond.load(df)
        t = self.true_val.load(df)
        f = self.false_val.load(df)
        return pd.Series(np.where(c, t, f), index=c.index)

    def __repr__(self):
        return f"if({self.cond}, {self.true_val}, {self.false_val})"


def _ensure_factor(x) -> Factor:
    """将标量转为Const, 保持Factor不变"""
    if isinstance(x, Factor):
        return x
    return Const(x)


def _slope(series: pd.Series) -> float:
    """线性回归斜率"""
    if len(series) < 2:
        return np.nan
    x = np.arange(len(series))
    y = series.values
    mask = ~np.isnan(y)
    if mask.sum() < 2:
        return np.nan
    return np.polyfit(x[mask], y[mask], 1)[0]


# ── 内置因子工厂 ──

def make_momentum_factor(days: int = 21) -> Factor:
    """N日动量因子"""
    close = RawFactor("close")
    return Factor.pct_change(close, days)


def make_volatility_factor(days: int = 60) -> Factor:
    """N日波动率因子（低波动=低分）"""
    ret = Factor.pct_change(RawFactor("close"), 1)
    return Factor.rolling(ret, days, "std")


def make_ma_cross_factor(short: int = 5, long: int = 20) -> Factor:
    """均线交叉信号: MA_short > MA_long"""
    close = RawFactor("close")
    ma_short = Factor.rolling(close, short, "mean")
    ma_long = Factor.rolling(close, long, "mean")
    return ma_short > ma_long
