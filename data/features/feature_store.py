"""
Point-in-Time 特征存储

设计:
  var/store/features/YYYY-MM-DD.parquet  — 每个 as-of 交易日一个 Parquet 文件
  var/store/features/YYYY-MM.parquet     — 兼容的月末快照
  每行一只股票, 每列一个因子, 用 as-of 当时已知的数据计算

关键约束:
  - 计算 2020-01-15 的特征时, 绝不使用 2020-01-16 之后的数据
  - 日频价量特征按 as-of 日期更新, 低频数据取 as-of 前最新披露值
  - 前视偏差零容忍

用法:
  builder = FeatureStoreBuilder(alpha_factors())
  builder.build_month("2020-01")
  builder.build_all("2015-01", "2026-05")
"""
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

from data.storage.datahub import get_datahub
from data.market.symbol_utils import to_ts_code
from signals.expression import Factor, alpha_factors


HUB = get_datahub()
FEATURES_DIR = HUB.features_dir()
FEATURES_DIR.mkdir(parents=True, exist_ok=True)
FEATURE_METADATA_STEMS = frozenset({"scan_meta", "buffett_scan"})


def feature_key_to_date(key: str) -> pd.Timestamp | None:
    """Map a feature file stem to its PIT as-of date."""
    text = str(key or "").strip()
    if not text:
        return None
    try:
        if len(text) == 7:
            return pd.Timestamp(text + "-01") + pd.offsets.MonthEnd(0)
        return pd.Timestamp(text)
    except Exception:
        return None


def feature_date_key(as_of: str | pd.Timestamp) -> str:
    return pd.Timestamp(as_of).strftime("%Y-%m-%d")


def feature_month_key(as_of: str | pd.Timestamp) -> str:
    return pd.Timestamp(as_of).to_period("M").strftime("%Y-%m")


def iter_feature_files(directory: Path | None = None) -> list[Path]:
    """List PIT feature parquet files, excluding metadata sidecars."""
    root = directory or FEATURES_DIR
    if not root.exists():
        return []
    return sorted(path for path in root.glob("*.parquet") if path.stem not in FEATURE_METADATA_STEMS)


def latest_feature_file(directory: Path | None = None, as_of: str | pd.Timestamp | None = None) -> Path | None:
    files = iter_feature_files(directory)
    if as_of is not None:
        cutoff = pd.Timestamp(as_of).normalize()
        files = [
            path
            for path in files
            if (feature_key_to_date(path.stem) is not None and feature_key_to_date(path.stem).normalize() <= cutoff)
        ]
    return files[-1] if files else None


def write_feature_slice(
    df: pd.DataFrame,
    key: str,
    *,
    directory: Path | None = None,
    hub=None,
) -> Path:
    """Write a PIT feature slice with normalized date metadata."""
    as_of = feature_key_to_date(key) or pd.Timestamp(key)
    out = df.copy()
    out["as_of_date"] = feature_date_key(as_of)
    if "month" not in out.columns:
        out["month"] = feature_month_key(as_of)
    root = directory or FEATURES_DIR
    path = root / f"{key}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    if hub is not None:
        hub.write_parquet(out, path)
    else:
        out.to_parquet(path, index=False)
    return path


def _read_feature_file(path: Path, hub=None) -> pd.DataFrame:
    store = hub or HUB
    df = store.read_parquet(path, default=pd.DataFrame())
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    inferred_as_of = feature_key_to_date(path.stem)
    if "as_of_date" not in out.columns:
        if inferred_as_of is not None:
            out["as_of_date"] = feature_date_key(inferred_as_of)
    else:
        parsed = pd.to_datetime(out["as_of_date"], errors="coerce")
        if inferred_as_of is not None:
            parsed = parsed.fillna(inferred_as_of)
        out["as_of_date"] = parsed.dt.strftime("%Y-%m-%d")
    if "month" not in out.columns:
        if "as_of_date" in out.columns:
            out["month"] = pd.to_datetime(out["as_of_date"], errors="coerce").dt.to_period("M").astype(str)
        else:
            out["month"] = path.stem
    return out


def load_feature_panel(
    files: list[Path] | None = None,
    hub=None,
    directory: Path | None = None,
    as_of: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Load and concatenate PIT feature slices."""
    selected = files if files is not None else iter_feature_files(directory)
    if as_of is not None:
        cutoff = pd.Timestamp(as_of).normalize()
        selected = [
            path
            for path in selected
            if (feature_key_to_date(path.stem) is not None and feature_key_to_date(path.stem).normalize() <= cutoff)
        ]
    frames = [_read_feature_file(path, hub=hub) for path in selected]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        raise RuntimeError(f"No features found in {FEATURES_DIR}")
    return pd.concat(frames, ignore_index=True)


def latest_feature_frame(hub=None, as_of: str | pd.Timestamp | None = None) -> pd.DataFrame:
    """Load the latest PIT feature slice, or an empty frame when absent."""
    latest = latest_feature_file(as_of=as_of)
    if latest is None:
        return pd.DataFrame()
    return _read_feature_file(latest, hub=hub)


def feature_time_key_column(df: pd.DataFrame) -> str:
    """Return the preferred temporal key column for feature rows."""
    return "as_of_date" if "as_of_date" in df.columns else "month"


def feature_period_key(values) -> pd.Series:
    """Normalize feature row timestamps into monthly CV buckets."""
    series = pd.Series(values)
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.notna().any():
        return parsed.dt.to_period("M").astype(str)
    return series.astype(str).str.slice(0, 7)


class FeatureStoreBuilder:
    """逐月构建 PIT 特征"""

    _MAX_CACHE_SIZE = 128

    def __init__(self, factors: Optional[Dict[str, Factor]] = None):
        self.factors = factors or alpha_factors()
        self._price_cache: Dict[str, pd.DataFrame] = {}
        self._cache_order: list[str] = []

    def _cache_put(self, key: str, df: pd.DataFrame):
        if len(self._price_cache) >= self._MAX_CACHE_SIZE:
            oldest = self._cache_order.pop(0)
            self._price_cache.pop(oldest, None)
        self._price_cache[key] = df
        self._cache_order.append(key)

    def _cache_get(self, key: str) -> Optional[pd.DataFrame]:
        return self._price_cache.get(key)

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
        from data.ingestion.fetcher import get_stock_daily

        month_dt = pd.Timestamp(month)
        # 该月最后一个交易日
        month_end = month_dt + pd.offsets.MonthEnd(0)

        rows = []
        for sym in symbols:
            # 拉取该股票的历史日线 (截断到 month_end)
            df = self._cache_get(sym)
            if df is None:
                try:
                    df = get_stock_daily(sym)
                    if df is None or len(df) == 0:
                        continue
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date").sort_index()
                    df = df[df.index >= start_date]
                    self._cache_put(sym, df)
                except Exception:
                    continue
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
        pq_path = HUB.feature_path(month)
        HUB.write_parquet(result, pq_path)
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
        pq = HUB.feature_path(month)
        if pq.exists():
            return HUB.read_parquet(pq)
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
    adds derived factors. PIT-safe: only uses data before the feature key.

    Returns enriched DataFrame with new factor columns.
    """
    from data.storage.dimensions import get_registry

    as_of_date = feature_key_to_date(month) or pd.Timestamp(month)
    reg = get_registry()

    # ── Moneyflow factors ──
    if reg.get("moneyflow_monthly") and reg.get("moneyflow_monthly").is_available:
        try:
            mf_files = HUB.list_dimension_snapshots("moneyflow_monthly")

            # Find latest moneyflow date ON OR BEFORE month_end
            mf_df = None
            for pq in reversed(mf_files):
                try:
                    dt = pd.Timestamp(pq.stem)
                except:
                    continue
                if dt <= as_of_date:
                    mf_df = HUB.read_parquet(pq)
                    break

            if mf_df is not None and len(mf_df) > 0:
                for sym in symbols:
                    ts_code = to_ts_code(sym)
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
                        sell_total = sell_lg + sell_elg
                        df.loc[mask, "mf_smart_ratio"] = (buy_lg + buy_elg) / sell_total if sell_total > 0 else 50.0
        except Exception as e:
            pass  # Non-critical enrichment

    # ── Holder factors ──
    if reg.get("holder_number") and reg.get("holder_number").is_available:
        try:
            holders_dir = HUB.store_dir("stock") / "holders"
            for sym in symbols:
                hf_path = holders_dir / f"{sym}.parquet"
                if not hf_path.exists():
                    continue
                hf_df = HUB.read_parquet(hf_path)
                if "end_date" not in hf_df.columns or len(hf_df) < 2:
                    continue
                hf_df["end_date"] = pd.to_datetime(hf_df["end_date"], errors="coerce")
                hf_df = hf_df[hf_df["end_date"] <= as_of_date]
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
    macro_sources = [("pmi", "今值"), ("money_supply", "M2_yoy"), ("shibor", "3M-定价"), ("cpi", "今值")]
    if any((reg.get(f"macro_{name}") and reg.get(f"macro_{name}").is_available) for name, _ in macro_sources):
        try:
            macro_dir = HUB.store_dir("macro")
            for name, col_map in macro_sources:
                dim = reg.get(f"macro_{name}")
                if dim is not None and not dim.is_available:
                    continue
                mf_path = macro_dir / f"{name}.parquet"
                if not mf_path.exists():
                    continue
                md = HUB.read_parquet(mf_path)
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
                md = md[md[date_col] <= as_of_date]
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
