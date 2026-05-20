"""
db_health_check.py — 全库数据健康扫描

每周六运行一次，按逻辑表分组扫描所有 Parquet：
- 缺失值比例 (overall + per-column)
- 异常值检测 (IQR × 3 边界)
- 数据新鲜度 (最新日期距今天数)
- 文件大小

输出: data/store/db_health.parquet
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.datahub import get_datahub

HUB = get_datahub()
STORE = HUB.store_root


def _missing_pct(df: pd.DataFrame) -> dict:
    cols = {}
    for c in df.columns:
        pct = float(df[c].isna().mean() * 100)
        if pct > 0:
            cols[c] = round(pct, 2)
    overall = float(df.isna().mean().mean() * 100) if len(df.columns) > 0 else 100.0
    return {"overall_pct": round(overall, 2), "per_column": cols}


def _outlier_count(df: pd.DataFrame) -> dict:
    total = 0
    per_col = {}
    for c in df.select_dtypes(include=[np.number]).columns:
        col = df[c].dropna()
        if len(col) < 10:
            continue
        q1, q3 = float(col.quantile(0.25)), float(col.quantile(0.75))
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
        cnt = int(((col < lo) | (col > hi)).sum())
        if cnt > 0:
            per_col[c] = cnt
            total += cnt
    return {"total": total, "per_column": per_col}


def _freshness_days(df: pd.DataFrame) -> Optional[int]:
    for dc in df.columns:
        if dc.lower() not in ("date", "trade_date", "ann_date", "end_date", "ts", "quarter"):
            continue
        try:
            s = pd.to_datetime(df[dc], errors="coerce").dropna()
            if len(s) == 0:
                continue
            return (date.today() - s.max().date()).days
        except Exception:
            continue
    return None


def _find_date_col(df: pd.DataFrame) -> Optional[str]:
    """Find a date-like column in the DataFrame."""
    for dc in df.columns:
        if dc.lower() in ("date", "trade_date", "ann_date", "end_date", "ts", "quarter"):
            try:
                s = pd.to_datetime(df[dc], errors="coerce")
                if s.notna().sum() > 0:
                    return dc
            except Exception:
                continue
    return None


def _time_breakdown(df: pd.DataFrame) -> Optional[dict]:
    """
    If the DataFrame has a date column, compute missing/outlier stats
    per time period: 近1年, 近5年, 近10年, 近20年, 20年前.

    Returns a JSON-serializable dict, or None if no date column.
    """
    date_col = _find_date_col(df)
    if date_col is None:
        return None

    today = pd.Timestamp(date.today())
    cuts = {
        "近1年": today - pd.DateOffset(years=1),
        "近5年": today - pd.DateOffset(years=5),
        "近10年": today - pd.DateOffset(years=10),
        "近20年": today - pd.DateOffset(years=20),
        "20年前": None,  # everything before 20 years
    }

    result = {}
    numeric_cols = list(df.select_dtypes(include=[np.number]).columns)

    for label in ["近1年", "近5年", "近10年", "近20年", "20年前"]:
        lo = cuts.get(label)
        hi = None
        if label == "20年前":
            hi = cuts["近20年"]
        else:
            # Find the next smaller period's cut as the upper bound
            keys = list(cuts.keys())
            idx = keys.index(label)
            if idx > 0:
                hi = cuts[keys[idx - 1]]

        # Filter rows
        dates = pd.to_datetime(df[date_col], errors="coerce")
        if lo is None:
            mask = dates < hi
        elif hi is None:
            mask = dates >= lo
        else:
            mask = (dates >= lo) & (dates < hi)

        sub = df[mask]
        n_rows = len(sub)
        if n_rows == 0:
            result[label] = {"rows": 0, "missing_pct": 0, "missing_cols": {}, "outliers": {}}
            continue

        # Missing per column
        missing_cols = {}
        total_missing = 0
        for c in numeric_cols:
            if c not in sub.columns:
                continue
            pct = float(sub[c].isna().mean() * 100)
            if pct > 0:
                missing_cols[c] = round(pct, 1)
                total_missing += pct
        avg_missing = round(total_missing / max(len(numeric_cols), 1), 1)

        # Outliers per column
        outlier_cols = {}
        for c in numeric_cols:
            if c not in sub.columns:
                continue
            col = sub[c].dropna()
            if len(col) < 10:
                continue
            q1, q3 = float(col.quantile(0.25)), float(col.quantile(0.75))
            iqr = q3 - q1
            if iqr == 0:
                continue
            lo_bound, hi_bound = q1 - 3 * iqr, q3 + 3 * iqr
            cnt = int(((col < lo_bound) | (col > hi_bound)).sum())
            if cnt > 0:
                outlier_cols[c] = cnt

        result[label] = {
            "rows": n_rows,
            "missing_pct": avg_missing,
            "missing_cols": missing_cols,
            "outliers": outlier_cols,
        }

    return result


def _scan_single(label: str, path: Path, source: str = "") -> dict:
    """Scan one parquet file."""
    size_mb = round(path.stat().st_size / 1024 / 1024, 3)
    try:
        df = HUB.read_parquet(path)
        missing = _missing_pct(df)
        outliers = _outlier_count(df)
        freshness = _freshness_days(df)
        tb = _time_breakdown(df)
        # Extract 10y split from time breakdown
        miss_10y = 0.0
        miss_10y_plus = 0.0
        out_10y = 0
        out_10y_plus = 0
        if tb:
            for period, info in tb.items():
                if period == "20年前":
                    miss_10y_plus += info.get("missing_pct", 0)
                    out_10y_plus += sum(info.get("outliers", {}).values())
                elif period in ("近1年","近5年","近10年","近20年"):
                    miss_10y += info.get("missing_pct", 0)
                    out_10y += sum(info.get("outliers", {}).values())
            miss_10y = round(miss_10y / max(len([k for k in tb if k != "20年前"]), 1), 2)
        return {
            "table": label,
            "source": source,
            "files": 1,
            "rows": len(df),
            "columns": len(df.columns),
            "size_mb": size_mb,
            "missing_pct": missing["overall_pct"],
            "missing_pct_10y": miss_10y,
            "missing_pct_10y_plus": miss_10y_plus,
            "missing_cols": json.dumps(missing["per_column"], ensure_ascii=False),
            "outlier_count": outliers["total"],
            "outlier_count_10y": out_10y,
            "outlier_count_10y_plus": out_10y_plus,
            "outlier_cols": json.dumps(outliers["per_column"], ensure_ascii=False),
            "freshness_days": freshness,
            "time_breakdown": json.dumps(tb, ensure_ascii=False) if tb else "{}",
            "error": None,
        }
    except Exception as e:
        return {
            "table": label,
            "source": source,
            "files": 1,
            "rows": 0,
            "columns": 0,
            "size_mb": size_mb,
            "missing_pct": 100.0,
            "missing_pct_10y": 0,
            "missing_pct_10y_plus": 100.0,
            "missing_cols": "{}",
            "outlier_count": 0,
            "outlier_count_10y": 0,
            "outlier_count_10y_plus": 0,
            "outlier_cols": "{}",
            "freshness_days": None,
            "time_breakdown": "{}",
            "error": str(e),
        }


def _scan_many(label: str, paths: list[Path], max_sample: int = 50, source: str = "") -> dict:
    """Scan multiple files, sample if too many."""
    if not paths:
        return {
            "table": label, "source": source, "files": 0, "rows": 0, "columns": 0,
            "size_mb": 0, "missing_pct": 0, "missing_cols": "{}",
            "missing_pct_10y": 0, "missing_pct_10y_plus": 0,
            "outlier_count": 0, "outlier_count_10y": 0, "outlier_count_10y_plus": 0,
            "outlier_cols": "{}", "freshness_days": None, "time_breakdown": "{}",
            "error": "no files",
        }

    total_size = sum(f.stat().st_size for f in sorted(paths))

    total_rows = 0
    total_missing = 0.0
    total_outliers = 0
    missing_cols_agg = {}
    outlier_cols_agg = {}
    min_freshness = None
    cols = 0
    errors = 0

    if len(paths) <= max_sample:
        sample = sorted(paths)
    else:
        # Prefer recently updated files over lexicographic first symbols/months.
        sample = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[:max_sample]
        sample = sorted(sample)
    for f in sample:
        try:
            df = HUB.read_parquet(f)
            total_rows += len(df)
            cols = max(cols, len(df.columns))
            m = _missing_pct(df)
            total_missing += m["overall_pct"]
            for k, v in m["per_column"].items():
                missing_cols_agg[k] = max(missing_cols_agg.get(k, 0), v)
            o = _outlier_count(df)
            total_outliers += o["total"]
            for k, v in o["per_column"].items():
                outlier_cols_agg[k] = outlier_cols_agg.get(k, 0) + v
            fday = _freshness_days(df)
            if fday is not None:
                min_freshness = fday if min_freshness is None else min(min_freshness, fday)
        except Exception:
            errors += 1

    n = len(sample)
    # Only report missing > 1% (aggregated)
    missing_cols_agg = {k: v for k, v in missing_cols_agg.items() if v > 1}
    outlier_cols_agg = {k: v for k, v in outlier_cols_agg.items() if v > 0}

    return {
        "table": label,
        "source": source,
        "files": len(paths),
        "rows": total_rows,
        "columns": cols,
        "size_mb": round(total_size / 1024 / 1024, 2),
        "missing_pct": round(total_missing / max(n, 1), 2),
        "missing_cols": json.dumps(missing_cols_agg, ensure_ascii=False),
        "missing_pct_10y": 0,
        "missing_pct_10y_plus": 0,
        "outlier_count": total_outliers,
        "outlier_count_10y": 0,
        "outlier_count_10y_plus": 0,
        "outlier_cols": json.dumps(outlier_cols_agg, ensure_ascii=False),
        "freshness_days": min_freshness,
        "time_breakdown": "{}",
        "error": f"{errors} read errors" if errors else None,
    }


def run_health_check(output_path: Optional[Path] = None) -> pd.DataFrame:
    if output_path is None:
        output_path = STORE / "db_health.parquet"

    records = []
    now = datetime.now().isoformat()

    # ── Table metadata (label_zh live here, not in frontend) ──
    # format: (source, label_zh, repairable)
    TABLE_META = {
        # Macro — CPI/PPI/PMI via Tushare (AKShare Jin10 dead since 2025-09)
        "macro_cpi": ("Tushare", "居民消费价格指数", True),
        "macro_ppi": ("Tushare", "工业生产者出厂价格", True),
        "macro_pmi": ("Tushare", "制造业采购经理指数", True),
        # Macro — still AKShare
        "macro_gdp": ("Tushare", "国内生产总值", True),
        "macro_lpr": ("Tushare", "贷款基础利率", True),
        "macro_money_supply": ("AKShare", "货币供应量 M0/M1/M2", True),
        "macro_shibor": ("AKShare", "上海银行间拆放利率", True),
        # Bonds
        "bond_treasury_yields": ("AKShare", "国债收益率曲线 (中美)", True),
        # Signals — computed, not repairable
        "signals_buffett": ("Computed (策略生成)", "巴菲特价值信号", False),
        "signals_buffett_scan": ("Computed (策略生成)", "巴菲特全量扫描", False),
        "signals_multifactor": ("Computed (策略生成)", "多因子打分信号", False),
        "signals_ml_lgbm": ("Computed (策略生成)", "LightGBM 机器学习信号", False),
        "signals_cybernetic": ("Computed (策略生成)", "控制论自适应信号", False),
        # Paper — simulated, not repairable
        "paper_trades": ("PaperBroker (模拟)", "模拟交易记录", False),
        "paper_nav": ("PaperBroker (模拟)", "模拟交易净值", False),
        "paper_state": ("PaperBroker (模拟)", "模拟账户状态", False),
        # System — manual import, not repairable
        "system_deepseek_usage": ("DeepSeek API", "DeepSeek Token 用量", False),
        # Per-symbol — all API-sourced, repairable
        "stock_holders": ("Tushare", "股东户数", True),
        "stock_holdertrade": ("Tushare", "股东增减持", True),
        "stock_moneyflow_daily": ("AKShare (近120日)", "日频资金流向", True),
        "stock_moneyflow_tushare_daily": ("Tushare", "日频资金流向 (全市场)", True),
        "stock_moneyflow_monthly": ("Tushare (全历史)", "月频资金流向", True),
        "stock_broker_recommend": ("Tushare", "券商月度金股", True),
        "stock_limit_list": ("Tushare", "涨跌停统计", True),
        "stock_top_list": ("Tushare", "龙虎榜", True),
        "stock_research_report": ("Tushare", "券商研报", True),
        "stock_dividend": ("Tushare", "分红送股", True),
        "share_float": ("Tushare", "限售股解禁", True),
        "repurchase": ("Tushare", "股票回购", True),
        # Funds / futures — Tushare Free extension dimensions
        "fund_daily": ("Tushare", "基金日线", True),
        "fund_portfolio": ("Tushare", "基金持仓", True),
        "fund_nav": ("Tushare", "基金净值", True),
        "futures_daily": ("Tushare", "期货日线", True),
        # Daily OHLCV
        "stock_daily": ("AKShare", "日线行情 OHLCV", True),
        # Features aggregate
        "features_all": ("Computed (多源融合)", "PIT 特征切片 (全量)", False),
        # Cache (derived)
        "cache_api_calls": ("AKShare Cache (可重建)", "API 响应缓存 (MD5)", False),
    }

    def _meta(table_name: str) -> tuple[str, str, bool]:
        if table_name.startswith("features_"):
            month = table_name.removeprefix("features_")
            return ("Computed (多源融合)", f"PIT 特征切片 {month}", False)
        return TABLE_META.get(table_name, ("", "", False))

    # ── Macro (single files) ──
    for name in ["cpi", "gdp", "lpr", "money_supply", "pmi", "ppi", "shibor"]:
        p = STORE / "macro" / f"{name}.parquet"
        if p.exists():
            records.append(_scan_single(f"macro_{name}", p))

    # ── Bonds ──
    tb = STORE / "bond" / "treasury_yields.parquet"
    if tb.exists():
        records.append(_scan_single("bond_treasury_yields", tb))

    # ── Features (all, as aggregate) ──
    feat_dir = STORE / "features"
    if feat_dir.exists():
        feat_files = sorted(feat_dir.glob("*.parquet"))
        if feat_files:
            records.append(_scan_many("features_all", feat_files, max_sample=20, source="Computed"))
        # Also keep 3 recent individual entries for per-month detail
        for f in feat_files[-3:]:
            records.append(_scan_single(f"features_{f.stem}", f, source="Computed"))

    # ── Signals ──
    for name in ["buffett", "buffett_scan", "multifactor", "ml_lgbm", "cybernetic"]:
        p = STORE / "signals" / f"{name}.parquet"
        if p.exists():
            records.append(_scan_single(f"signals_{name}", p))

    # ── Paper ──
    for name in ["trades", "nav", "state"]:
        p = STORE / "paper" / f"{name}.parquet"
        if p.exists():
            records.append(_scan_single(f"paper_{name}", p))

    # ── DeepSeek ──
    ds = STORE / "deepseek" / "daily_usage.parquet"
    if ds.exists():
        records.append(_scan_single("system_deepseek_usage", ds))

    # ── Per-symbol tables (aggregate) ──
    def _add_many(label: str, rel_glob: str, max_s: int) -> None:
        pdir = STORE / Path(rel_glob).parent
        pattern = Path(rel_glob).name
        if pdir.exists():
            paths = sorted(pdir.glob(pattern))
            if paths:
                records.append(_scan_many(label, paths, max_sample=max_s))

    for label, glob_pattern, max_s in [
        ("stock_daily", "daily/*.parquet", 30),
        ("stock_holders", "holders/*.parquet", 30),
        ("stock_holdertrade", "holdertrade/*.parquet", 30),
        ("stock_moneyflow_daily", "moneyflow/*.parquet", 30),
        ("stock_moneyflow_tushare_daily", "moneyflow/daily/*.parquet", 30),
        ("stock_moneyflow_monthly", "moneyflow/monthly/*.parquet", 12),
        ("stock_broker_recommend", "broker_recommend/*.parquet", 12),
        ("stock_limit_list", "limit_list/*.parquet", 12),
        ("stock_top_list", "top_list/*.parquet", 12),
        ("stock_research_report", "research_report/*.parquet", 6),
    ]:
        _add_many(label, f"stock/{glob_pattern}", max_s)

    for label, rel_glob, max_s in [
        ("fund_daily", "fund/daily/*.parquet", 12),
        ("fund_portfolio", "fund/portfolio/*.parquet", 8),
        ("fund_nav", "fund/nav/*.parquet", 12),
        ("futures_daily", "futures/daily/*.parquet", 12),
    ]:
        _add_many(label, rel_glob, max_s)

    # ── Single file per-symbol tables ──
    for label, p in [
        ("share_float", STORE / "stock" / "share_float" / "all.parquet"),
        ("repurchase", STORE / "stock" / "repurchase" / "all.parquet"),
        ("stock_dividend", STORE / "stock" / "dividend" / "all_dividends.parquet"),
    ]:
        if p.exists():
            records.append(_scan_single(label, p))

    # ── data/cache/api/ (AKShare API response cache) ──
    api_cache = STORE.parent / "cache" / "api"
    if api_cache.exists():
        paths = sorted(api_cache.glob("*.parquet"))
        if paths:
            records.append(_scan_many("cache_api_calls", paths, max_sample=50, source="AKShare Cache"))

    # ── Inject source + label_zh + repairable from TABLE_META ──
    for r in records:
        src, zh, repairable = _meta(r["table"])
        r["source"] = src
        r["label_zh"] = zh
        r["repairable"] = repairable

    # ── Summary ──
    n = len(records)
    total_size = sum(r["size_mb"] for r in records)
    avg_missing = round(sum(r["missing_pct"] for r in records) / max(n, 1), 2)
    total_outliers = sum(r["outlier_count"] for r in records)

    summary = [{
        "table": "__SUMMARY__",
        "source": "",
        "label_zh": "",
        "repairable": False,
        "files": 0,
        "rows": 0,
        "columns": n,
        "size_mb": round(total_size, 2),
        "missing_pct": avg_missing,
        "missing_cols": "{}",
        "missing_pct_10y": 0,
        "missing_pct_10y_plus": 0,
        "outlier_count": total_outliers,
        "outlier_count_10y": 0,
        "outlier_count_10y_plus": 0,
        "outlier_cols": "{}",
        "freshness_days": None,
        "time_breakdown": "{}",
        "error": None,
    }]

    for r in records:
        r["checked_at"] = now
    for s in summary:
        s["checked_at"] = now

    result = pd.DataFrame(summary + records)
    HUB.write_parquet(result, output_path)
    print(f"Health check done: {n} logical tables, avg missing {avg_missing}%, saved to {output_path}")
    return result


if __name__ == "__main__":
    run_health_check()
