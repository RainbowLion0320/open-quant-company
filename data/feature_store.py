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


# ══════════════════════════════════════════════════════════
# 新数据维度集成 (Phase 4.2)
# ══════════════════════════════════════════════════════════

def enrich_from_registry(
    df: pd.DataFrame,
    month: str,
    symbols: List[str],
) -> pd.DataFrame:
    """
    Enrich a feature DataFrame with additional data dimensions from the data registry.

    Reads cached Parquet files for moneyflow, holders, macro and
    adds derived factors. PIT-safe: only uses data before `month`.

    Returns enriched DataFrame with new factor columns.
    """
    from data.data_registry import get_registry

    month_dt = pd.Timestamp(month)
    month_end = month_dt + pd.offsets.MonthEnd(0)  # Last day of month
    reg = get_registry()

    # ── Moneyflow factors ──
    if reg.get("moneyflow_monthly") and reg.get("moneyflow_monthly").is_available:
        try:
            mf_dir = get_store_dir("stock") / "moneyflow" / "monthly"
            mf_files = sorted(mf_dir.glob("*.parquet"))

            # Find latest moneyflow date ON OR BEFORE month_end
            mf_df = None
            for pq in reversed(mf_files):
                try:
                    dt = pd.Timestamp(pq.stem)
                except:
                    continue
                if dt <= month_end:
                    mf_df = pd.read_parquet(pq)
                    break

            if mf_df is not None and len(mf_df) > 0:
                for sym in symbols:
                    ts_code = _to_ts_code_n(sym)
                    row_match = mf_df[mf_df["ts_code"] == ts_code]
                    if len(row_match) > 0:
                        row = row_match.iloc[0]
                        mask = df["symbol"] == sym
                        buy_lg = float(row.get("buy_lg_amount", 0) or 0)
                        sell_lg = float(row.get("sell_lg_amount", 0) or 0)
                        buy_elg = float(row.get("buy_elg_amount", 0) or 0)
                        sell_elg = float(row.get("sell_elg_amount", 0) or 0)
                        net_mf = float(row.get("net_mf_amount", 0) or 0)

                        total_abs = abs(buy_lg) + abs(sell_lg) + abs(buy_elg) + abs(sell_elg) + 1
                        df.loc[mask, "mf_net_amount"] = net_mf
                        df.loc[mask, "mf_inst_net"] = buy_lg + buy_elg - sell_lg - sell_elg
                        df.loc[mask, "mf_smart_ratio"] = (buy_lg + buy_elg) / max(sell_lg + sell_elg, 1)
        except Exception as e:
            pass  # Non-critical enrichment

    # ── Holder factors ──
    if reg.get("holder_number") and reg.get("holder_number").is_available:
        try:
            holders_dir = get_store_dir("stock") / "holders"
            for sym in symbols:
                hf_path = holders_dir / f"{sym}.parquet"
                if not hf_path.exists():
                    continue
                hf_df = pd.read_parquet(hf_path)
                if "end_date" not in hf_df.columns or len(hf_df) < 2:
                    continue
                hf_df["end_date"] = pd.to_datetime(hf_df["end_date"], errors="coerce")
                hf_df = hf_df[hf_df["end_date"] <= month_end]
                if len(hf_df) < 2:
                    continue
                cur = int(hf_df.iloc[-1].get("holder_num", 0) or 0)
                prev = int(hf_df.iloc[-2].get("holder_num", 0) or 0)
                if prev > 0:
                    mask = df["symbol"] == sym
                    df.loc[mask, "holder_change_pct"] = (cur - prev) / prev
                    df.loc[mask, "holder_concentration"] = 1e8 / max(cur, 1)
        except Exception:
            pass

    # ── Macro factors ──
    if reg.get("macro_pmi") and reg.get("macro_pmi").is_available:
        try:
            macro_dir = get_store_dir("macro")
            for name, col_map in [("pmi", "今值"), ("money_supply", "M2_yoy"),
                                   ("shibor", "3M-定价"), ("cpi", "今值")]:
                mf_path = macro_dir / f"{name}.parquet"
                if not mf_path.exists():
                    continue
                md = pd.read_parquet(mf_path)
                # Find date column
                date_col = None
                for c in md.columns:
                    if "date" in c.lower() or "日期" in c:
                        date_col = c
                        break
                if date_col is None:
                    date_col = md.columns[1] if len(md.columns) > 1 else md.columns[0]

                md[date_col] = pd.to_datetime(md[date_col], errors="coerce")
                md = md.dropna(subset=[date_col])  # Remove NaT rows BEFORE date filter
                md = md[md[date_col] <= month_end]
                if len(md) == 0:
                    continue

                latest = md.iloc[-1]
                if name == "shibor":
                    # "3M-定价" might be in columns
                    sh_candidates = [c for c in latest.index if "3M" in str(c) and "定价" in str(c)]
                    if sh_candidates:
                        val = float(latest[sh_candidates[0]] or 0)
                        df["macro_shibor_3m"] = val
                    # Also try "O/N-定价" for ON
                    on_candidates = [c for c in latest.index if "O/N" in str(c) and "定价" in str(c)]
                    if on_candidates:
                        df["macro_shibor_on"] = float(latest[on_candidates[0]] or 0)
                elif col_map and col_map in latest.index:
                    val = float(latest[col_map] or 0)
                    df[f"macro_{name}"] = val
                else:
                    # Find the first numeric value column
                    for c in latest.index:
                        if c != date_col:
                            try:
                                v = float(latest[c] or 0)
                                if not np.isnan(v):
                                    df[f"macro_{name}"] = v
                            except:
                                pass
                            break
        except Exception:
            pass

    return df


def _to_ts_code_n(symbol: str) -> str:
    """Convert 000001 → 000001.SZ"""
    if "." in symbol:
        return symbol
    code = symbol.zfill(6)
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    return ""
