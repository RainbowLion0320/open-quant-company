"""
Point-in-Time 特征存储

设计:
  data/store/features/YYYY-MM.parquet  — 每月一个 Parquet 文件
  每行一只股票, 每列一个因子, 用当时已知的数据计算

关键约束:
  - 计算 2020-01 的特征时, 绝不使用 2020-02 之后的价格数据
  - 逐月滚动构建, 前视偏差零容忍

用法:
  builder = FeatureStoreBuilder(alpha_factors())
  builder.build_month("2020-01")
  builder.build_all("2015-01", "2026-05")
"""
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd
import numpy as np

from data.db import get_store_dir
from signals.expression import Factor, alpha_factors


FEATURES_DIR = get_store_dir() / "features"
FEATURES_DIR.mkdir(parents=True, exist_ok=True)


class FeatureStoreBuilder:
    """逐月构建 PIT 特征"""

    def __init__(self, factors: Optional[Dict[str, Factor]] = None):
        self.factors = factors or alpha_factors()
        self._price_cache: Dict[str, pd.DataFrame] = {}

    def build_month(
        self,
        month: str,          # "YYYY-MM"
        symbols: List[str],
        start_date: str = "2015-01-01",
    ) -> Optional[pd.DataFrame]:
        """
        构建单月特征表。

        只使用 month 之前(含)的价格数据, 确保 PIT 正确性。
        """
        from data.fetcher import get_stock_daily

        month_dt = pd.Timestamp(month)
        # 该月最后一个交易日
        month_end = month_dt + pd.offsets.MonthEnd(0)

        rows = []
        for sym in symbols:
            # 拉取该股票的历史日线 (截断到 month_end)
            if sym not in self._price_cache:
                try:
                    df = get_stock_daily(sym)
                    if df is None or len(df) == 0:
                        continue
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date").sort_index()
                    df = df[df.index >= start_date]
                    self._price_cache[sym] = df
                except Exception:
                    continue

            df = self._price_cache[sym]
            # PIT 约束: 只用 month_end 及之前的数据
            df_pit = df[df.index <= month_end]
            if len(df_pit) < 60:  # 至少需要60天数据
                continue

            last_idx = len(df_pit) - 1
            row = {"symbol": sym}
            for name, factor in self.factors.items():
                val = factor.compute(df_pit, last_idx)
                row[name] = val if not pd.isna(val) else None

            rows.append(row)

        if not rows:
            return None

        result = pd.DataFrame(rows)
        # 保存
        pq_path = FEATURES_DIR / f"{month}.parquet"
        result.to_parquet(pq_path, index=False)
        return result

    def build_all(
        self,
        start_month: str,
        end_month: str,
        symbols: List[str],
    ) -> List[str]:
        """批量构建所有月份的特征"""
        months = pd.date_range(start_month, end_month, freq="MS")
        built = []
        for m in months:
            key = m.strftime("%Y-%m")
            pq_path = FEATURES_DIR / f"{key}.parquet"
            if pq_path.exists():
                print(f"  {key}: skip (exists)")
                continue
            df = self.build_month(key, symbols)
            if df is not None:
                print(f"  {key}: {len(df)} stocks, {len(self.factors)} factors")
                built.append(key)
            else:
                print(f"  {key}: no data")
        return built

    @staticmethod
    def load_month(month: str) -> Optional[pd.DataFrame]:
        """加载单月特征"""
        pq = FEATURES_DIR / f"{month}.parquet"
        if pq.exists():
            return pd.read_parquet(pq)
        return None


class TimeSeriesSplitter:
    """
    时间序列交叉验证 — 滚动窗口分割

    训练窗口逐年滚动, 测试窗口为训练后一年。
    杜绝前视偏差: 每个 split 中 test 的时间 > train 的时间。
    """

    def __init__(
        self,
        train_months: int = 60,   # 训练期月数 (5年)
        test_months: int = 12,     # 测试期月数 (1年)
        step_months: int = 12,     # 步长
        min_train_months: int = 36,
    ):
        self.train_months = train_months
        self.test_months = test_months
        self.step_months = step_months
        self.min_train_months = min_train_months

    def split(self, months: List[str]) -> List[tuple]:
        """生成 (train_months, test_months) 对"""
        splits = []
        all_months = sorted(months)
        n = len(all_months)

        start = self.train_months  # 至少需要 train_months 个月才能开始
        while start + self.test_months <= n:
            train = all_months[start - self.train_months : start]
            test = all_months[start : start + self.test_months]
            splits.append((train, test))
            start += self.step_months

        return splits

    def load_split(self, split: tuple) -> tuple:
        """加载一个 split 的训练和测试数据"""
        train_months, test_months = split
        train_dfs = []
        test_dfs = []
        for m in train_months:
            df = FeatureStoreBuilder.load_month(m)
            if df is not None:
                train_dfs.append(df)
        for m in test_months:
            df = FeatureStoreBuilder.load_month(m)
            if df is not None:
                test_dfs.append(df)
        train = pd.concat(train_dfs, ignore_index=True) if train_dfs else None
        test = pd.concat(test_dfs, ignore_index=True) if test_dfs else None
        return train, test
