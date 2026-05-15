"""
数据清洗层 — Data Cleaner

在数据采集和特征构建之间的质量关卡。
所有进入 PIT 特征存储的数据必须经过清洗验证。

设计理念:
  - 可插拔规则，类似 RiskRule 模式
  - 每条规则有独立的 enabled 开关和参数
  - 清洗报告可追溯（什么数据被丢弃、为什么）

清洗规则:
  1. OHLCV 完整性验证 (价格合理性、high>=low 等)
  2. 异常值检测 (日涨跌幅 > N 标准差, 成交量暴增)
  3. 停牌/退市检测 (价格连续不变 > N 天)
  4. 缺失值处理 (前向填充, 最多 N 天)
  5. 基本面合理性 (ROE > -100%, PE > 0, D/E >= 0)
  6. 特征缩尾 (Winsorize 1%/99%)

用法:
  from data.cleaner import DataCleaner
  cleaner = DataCleaner()
  df_clean, report = cleaner.clean_ohlcv(df)
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class CleanReport:
    """单次清洗报告"""
    total_rows: int = 0
    removed_rows: int = 0
    filled_values: int = 0
    capped_outliers: int = 0
    flagged_suspended: int = 0
    details: List[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return (self.total_rows - self.removed_rows) / max(self.total_rows, 1)

    def summary(self) -> str:
        lines = [
            f"CleanReport: {self.total_rows} rows → {self.total_rows - self.removed_rows} kept "
            f"({self.pass_rate:.1%})"
        ]
        if self.removed_rows > 0:
            lines.append(f"  removed: {self.removed_rows}")
        if self.filled_values > 0:
            lines.append(f"  filled: {self.filled_values}")
        if self.capped_outliers > 0:
            lines.append(f"  capped: {self.capped_outliers}")
        for detail in self.details:
            lines.append(f"  {detail}")
        return "\n".join(lines)


class CleanRule:
    """单个清洗规则"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.enabled = config.get("enabled", True)
        self._config = config

    def apply(self, df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
        """子类重写。返回清洗后的 DataFrame。"""
        return df


class OHLCVIntegrityRule(CleanRule):
    """OHLCV 完整性验证"""

    REQUIRED_COLS = ["open", "high", "low", "close", "volume"]

    def apply(self, df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
        original = len(df)

        # 必须有必需列
        missing_cols = [c for c in self.REQUIRED_COLS if c not in df.columns]
        if missing_cols:
            report.details.append(f"OHLCV: missing columns {missing_cols}")
            return df

        # 复制避免 SettingWithCopyWarning
        df = df.copy()

        # high >= low
        mask_hl = df["high"] < df["low"]
        if mask_hl.any():
            n = mask_hl.sum()
            report.details.append(f"OHLCV: high<low {n} rows — swapping")
            df.loc[mask_hl, ["high", "low"]] = df.loc[mask_hl, ["low", "high"]].values

        # close 在 [low, high] 范围内
        mask_cl = (df["close"] < df["low"]) | (df["close"] > df["high"])
        if mask_cl.any():
            n = mask_cl.sum()
            report.details.append(f"OHLCV: close out of [low,high] {n} rows — clamping")
            df.loc[df["close"] < df["low"], "close"] = df.loc[df["close"] < df["low"], "low"]
            df.loc[df["close"] > df["high"], "close"] = df.loc[df["close"] > df["high"], "high"]

        # close > 0, volume >= 0
        mask_bad = (df["close"] <= 0) | (df["volume"] < 0)
        if mask_bad.any():
            n = mask_bad.sum()
            df = df[~mask_bad]
            report.removed_rows += n
            report.details.append(f"OHLCV: negative price/volume {n} rows — removed")

        # open 合理性
        mask_open = df["open"] <= 0
        if mask_open.any():
            df.loc[mask_open, "open"] = df.loc[mask_open, "close"]

        return df


class OutlierDetectionRule(CleanRule):
    """异常值检测"""

    def apply(self, df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
        if "close" not in df.columns or len(df) < 20:
            return df

        df = df.copy()
        sigma = self._config.get("sigma", 5)
        max_change = self._config.get("max_daily_change_pct", 0.20)
        max_vol_ratio = self._config.get("max_volume_ratio", 15)

        # 日收益率
        df["_ret"] = df["close"].pct_change()
        mean_ret = df["_ret"].mean()
        std_ret = df["_ret"].std()

        capped = 0

        # 收益率极端值 → 缩尾
        if std_ret > 0:
            upper = mean_ret + sigma * std_ret
            lower = mean_ret - sigma * std_ret
            mask_upper = df["_ret"] > upper
            mask_lower = df["_ret"] < lower
            n = mask_upper.sum() + mask_lower.sum()
            if n > 0:
                df.loc[mask_upper, "close"] = df.loc[mask_upper, "close"].shift(1) * (1 + upper)
                df.loc[mask_lower, "close"] = df.loc[mask_lower, "close"].shift(1) * (1 + lower)
                capped += n

        # 单日涨跌幅超过 max_change；保留常见涨跌停幅度附近的真实行情。
        abs_ret = df["_ret"].abs()
        limit_like = (
            abs_ret.between(0.095, 0.105)
            | abs_ret.between(0.195, 0.205)
            | abs_ret.between(0.295, 0.305)
        )
        mask_big = (abs_ret > max_change) & ~limit_like
        if mask_big.any():
            n = mask_big.sum()
            df.loc[mask_big, "close"] = df.loc[mask_big, "close"].shift(1)
            capped += n

        # 成交量暴增
        if "volume" in df.columns and len(df) > 20:
            med_vol = df["volume"].rolling(20).median()
            mask_vol = df["volume"] > med_vol * max_vol_ratio
            if mask_vol.any():
                df.loc[mask_vol, "volume"] = med_vol[mask_vol]

        report.capped_outliers += capped
        if capped > 0:
            report.details.append(f"Outlier: {capped} values capped (sigma={sigma})")

        df.drop(columns=["_ret"], inplace=True, errors="ignore")
        return df


class SuspendedDetectionRule(CleanRule):
    """停牌/退市检测"""

    def apply(self, df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
        if "close" not in df.columns or len(df) < 5:
            return df

        max_flat_days = self._config.get("max_flat_days", 60)

        # 检测连续价格不变的天数
        df = df.copy()
        df["_same"] = (df["close"].diff().abs() < 1e-8).astype(int)

        # 找到连续不变的段
        streak = 0
        drop_indices = []
        for i, same in enumerate(df["_same"].values):
            if same:
                streak += 1
                if streak >= max_flat_days:
                    drop_indices.append(i)
            else:
                streak = 0

        if drop_indices:
            n = len(drop_indices)
            df = df.drop(df.index[drop_indices])
            report.removed_rows += n
            report.flagged_suspended += n
            report.details.append(f"Suspended: {n} rows (price flat ≥{max_flat_days}d)")

        df.drop(columns=["_same"], inplace=True, errors="ignore")
        return df


class MissingValueRule(CleanRule):
    """缺失值处理"""

    def apply(self, df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
        max_ffill = self._config.get("max_forward_fill", 5)
        df = df.copy()

        filled = 0
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                continue
            before_na = df[col].isna().sum()
            # 前向填充 (最多 max_ffill 天)
            df[col] = df[col].ffill(limit=max_ffill)
            filled += max(0, before_na - df[col].isna().sum())

        # 仍有 NA 的行 → 丢弃
        before = len(df)
        df = df.dropna(subset=["close"])
        after = len(df)

        report.filled_values += filled
        report.removed_rows += (before - after)
        if before > after:
            report.details.append(f"MissingValue: {before-after} rows removed (NaN after fill)")
        return df


class FinancialValidationRule(CleanRule):
    """基本面数据合理性验证"""

    def apply(self, df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
        """验证财务因子列的合理性"""
        df = df.copy()
        capped = 0

        checks = {
            "fund_roe": (-1.0, 1.0),            # ROE in [-100%, 100%]
            "fund_gross_margin": (0.0, 1.0),    # 毛利率 in [0%, 100%]
            "fund_net_margin": (-1.0, 1.0),     # 净利率 in [-100%, 100%]
            "fund_de_ratio": (0.0, 20.0),       # D/E in [0, 20]
            "val_pe_ttm": (0.0, 1000.0),        # PE in (0, 1000]
            "val_pb": (0.0, 50.0),              # PB in (0, 50]
        }

        for col, (lo, hi) in checks.items():
            if col not in df.columns:
                continue
            mask_lo = df[col] < lo
            mask_hi = df[col] > hi
            if mask_lo.any():
                df.loc[mask_lo, col] = lo
                capped += mask_lo.sum()
            if mask_hi.any():
                df.loc[mask_hi, col] = hi
                capped += mask_hi.sum()

        if capped > 0:
            report.capped_outliers += capped
            report.details.append(f"FinancialValidation: {capped} values clamped")

        return df


class WinsorizeRule(CleanRule):
    """特征缩尾处理"""

    def apply(self, df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
        """对所有数值特征做 1%/99% 缩尾"""
        lower = self._config.get("lower_pct", 0.01)
        upper = self._config.get("upper_pct", 0.99)

        df = df.copy()
        capped = 0

        # 只处理特征列，跳过 symbol/month/target
        skip = {"symbol", "month", "name", "date", "ts_code", "ret_fwd_20d"}
        for col in df.columns:
            if col in skip or not np.issubdtype(df[col].dtype, np.number):
                continue
            lo = df[col].quantile(lower)
            hi = df[col].quantile(upper)
            n_lo = (df[col] < lo).sum()
            n_hi = (df[col] > hi).sum()
            if n_lo > 0 or n_hi > 0:
                df[col] = df[col].clip(lo, hi)
                capped += n_lo + n_hi

        report.capped_outliers += capped
        if capped > 0:
            report.details.append(f"Winsorize: {capped} values capped [{lower:.0%}, {upper:.0%}]")

        return df


# ── Rule registry ──

RULE_CLASSES: Dict[str, type] = {
    "ohlcv_integrity": OHLCVIntegrityRule,
    "outlier_detection": OutlierDetectionRule,
    "suspended_detection": SuspendedDetectionRule,
    "missing_value": MissingValueRule,
    "financial_validation": FinancialValidationRule,
    "winsorize": WinsorizeRule,
}


class DataCleaner:
    """
    数据清洗器。

    从 config/settings.yaml → data_cleaning 段加载规则。
    支持两种清洗模式:
      - clean_ohlcv(df) — 清洗原始 OHLCV 数据
      - clean_features(df) — 清洗构建好的特征 DataFrame
    """

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"

        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        clean_cfg = cfg.get("data_cleaning", {})
        self._ohlcv_rules: List[CleanRule] = []
        self._feature_rules: List[CleanRule] = []

        for rule_name, rule_cls in RULE_CLASSES.items():
            rule_config = clean_cfg.get(rule_name, {})
            if not rule_config.get("enabled", True):
                continue

            rule = rule_cls(rule_name, rule_config)
            # OHLCV 规则 vs 特征规则
            if rule_name in ("ohlcv_integrity", "outlier_detection",
                             "suspended_detection", "missing_value"):
                self._ohlcv_rules.append(rule)
            if rule_name in ("financial_validation", "winsorize"):
                self._feature_rules.append(rule)

    def clean_ohlcv(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, CleanReport]:
        """清洗原始 OHLCV 数据"""
        report = CleanReport(total_rows=len(df))
        for rule in self._ohlcv_rules:
            try:
                df = rule.apply(df, report)
            except Exception as e:
                report.details.append(f"Rule '{rule.name}' error: {e}")
        return df, report

    def clean_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, CleanReport]:
        """清洗构建好的特征 DataFrame"""
        report = CleanReport(total_rows=len(df))
        for rule in self._feature_rules:
            try:
                df = rule.apply(df, report)
            except Exception as e:
                report.details.append(f"Rule '{rule.name}' error: {e}")
        return df, report

    def clean_all(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, CleanReport]:
        """完整清洗: OHLCV + 特征"""
        df, report1 = self.clean_ohlcv(df)
        df, report2 = self.clean_features(df)

        # 合并报告
        report1.details.extend(report2.details)
        report1.capped_outliers += report2.capped_outliers
        report1.removed_rows += report2.removed_rows
        report1.filled_values += report2.filled_values
        return df, report1

    @property
    def rule_count(self) -> int:
        return len(self._ohlcv_rules) + len(self._feature_rules)
