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

STORE = PROJECT_ROOT / "data" / "store"


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
        if dc.lower() not in ("date", "trade_date", "ann_date", "end_date", "ts"):
            continue
        try:
            s = pd.to_datetime(df[dc], errors="coerce").dropna()
            if len(s) == 0:
                continue
            return (date.today() - s.max().date()).days
        except Exception:
            continue
    return None


def _scan_single(label: str, path: Path, source: str = "") -> dict:
    """Scan one parquet file."""
    size_mb = round(path.stat().st_size / 1024 / 1024, 3)
    try:
        df = pd.read_parquet(path)
        missing = _missing_pct(df)
        outliers = _outlier_count(df)
        freshness = _freshness_days(df)
        return {
            "table": label,
            "source": source,
            "files": 1,
            "rows": len(df),
            "columns": len(df.columns),
            "size_mb": size_mb,
            "missing_pct": missing["overall_pct"],
            "missing_cols": json.dumps(missing["per_column"], ensure_ascii=False),
            "outlier_count": outliers["total"],
            "outlier_cols": json.dumps(outliers["per_column"], ensure_ascii=False),
            "freshness_days": freshness,
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
            "missing_cols": "{}",
            "outlier_count": 0,
            "outlier_cols": "{}",
            "freshness_days": None,
            "error": str(e),
        }


def _scan_many(label: str, paths: list[Path], max_sample: int = 50, source: str = "") -> dict:
    """Scan multiple files, sample if too many."""
    if not paths:
        return {
            "table": label, "source": source, "files": 0, "rows": 0, "columns": 0,
            "size_mb": 0, "missing_pct": 0, "missing_cols": "{}",
            "outlier_count": 0, "outlier_cols": "{}",
            "freshness_days": None, "error": "no files",
        }

    total_size = 0
    total_rows = 0
    total_missing = 0.0
    total_outliers = 0
    missing_cols_agg = {}
    outlier_cols_agg = {}
    min_freshness = None
    cols = 0
    errors = 0

    sample = paths if len(paths) <= max_sample else sorted(paths)[:max_sample]
    for f in sample:
        total_size += f.stat().st_size
        try:
            df = pd.read_parquet(f)
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
        "outlier_count": total_outliers,
        "outlier_cols": json.dumps(outlier_cols_agg, ensure_ascii=False),
        "freshness_days": min_freshness,
        "error": f"{errors} read errors" if errors else None,
    }


def run_health_check(output_path: Optional[Path] = None) -> pd.DataFrame:
    if output_path is None:
        output_path = STORE / "db_health.parquet"

    records = []
    now = datetime.now().isoformat()

    # ── Table metadata (label_zh live here, not in frontend) ──
    TABLE_META = {
        # Macro
        "macro_cpi": ("AKShare", "居民消费价格指数"),
        "macro_gdp": ("AKShare", "国内生产总值"),
        "macro_lpr": ("AKShare", "贷款基础利率"),
        "macro_money_supply": ("AKShare", "货币供应量 M0/M1/M2"),
        "macro_pmi": ("AKShare", "制造业采购经理指数"),
        "macro_ppi": ("AKShare", "工业生产者出厂价格"),
        "macro_shibor": ("AKShare", "上海银行间拆放利率"),
        # Bonds
        "bond_treasury_yields": ("AKShare", "国债收益率曲线 (中美)"),
        # Features
        "features_2026-02": ("Computed (多源融合)", "PIT 特征切片 2026-02"),
        "features_2026-03": ("Computed (多源融合)", "PIT 特征切片 2026-03"),
        "features_2026-04": ("Computed (多源融合)", "PIT 特征切片 2026-04"),
        # Signals
        "signals_buffett": ("Computed (策略生成)", "巴菲特价值信号"),
        "signals_buffett_scan": ("Computed (策略生成)", "巴菲特全量扫描"),
        "signals_multifactor": ("Computed (策略生成)", "多因子打分信号"),
        "signals_ml_lgbm": ("Computed (策略生成)", "LightGBM 机器学习信号"),
        "signals_cybernetic": ("Computed (策略生成)", "控制论自适应信号"),
        # Paper
        "paper_trades": ("PaperBroker (模拟)", "模拟交易记录"),
        "paper_nav": ("PaperBroker (模拟)", "模拟交易净值"),
        "paper_state": ("PaperBroker (模拟)", "模拟账户状态"),
        # System
        "system_deepseek_usage": ("DeepSeek API", "DeepSeek Token 用量"),
        # Per-symbol
        "stock_holders": ("Tushare", "股东户数"),
        "stock_holdertrade": ("Tushare", "股东增减持"),
        "stock_moneyflow_daily": ("AKShare (近120日)", "日频资金流向"),
        "stock_moneyflow_monthly": ("Tushare (全历史)", "月频资金流向"),
        "stock_broker_recommend": ("Tushare", "券商月度金股"),
        "stock_limit_list": ("Tushare", "涨跌停统计"),
        "stock_research_report": ("Tushare", "券商研报"),
        "share_float": ("Tushare", "限售股解禁"),
        "repurchase": ("Tushare", "股票回购"),
    }

    def _meta(table_name: str) -> tuple[str, str]:
        return TABLE_META.get(table_name, ("", ""))

    # ── Macro (single files) ──
    for name in ["cpi", "gdp", "lpr", "money_supply", "pmi", "ppi", "shibor"]:
        p = STORE / "macro" / f"{name}.parquet"
        if p.exists():
            records.append(_scan_single(f"macro_{name}", p))

    # ── Bonds ──
    tb = STORE / "bond" / "treasury_yields.parquet"
    if tb.exists():
        records.append(_scan_single("bond_treasury_yields", tb))

    # ── Features (last 3 months) ──
    feat_dir = STORE / "features"
    feat_files = sorted(feat_dir.glob("*.parquet"))[-3:] if feat_dir.exists() else []
    for f in feat_files:
        records.append(_scan_single(f"features_{f.stem}", f))

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
    for label, glob_pattern, max_s in [
        ("stock_holders", "holders/*.parquet", 30),
        ("stock_holdertrade", "holdertrade/*.parquet", 30),
        ("stock_moneyflow_daily", "moneyflow/??????.parquet", 30),
        ("stock_moneyflow_monthly", "moneyflow/monthly/*.parquet", 12),
        ("stock_broker_recommend", "broker_recommend/*.parquet", 12),
        ("stock_limit_list", "limit_list/*.parquet", 12),
        ("stock_research_report", "research_report/*.parquet", 6),
    ]:
        pdir = STORE / "stock" / Path(glob_pattern).parent
        pattern = Path(glob_pattern).name
        if pdir.exists():
            paths = sorted(pdir.glob(pattern))
            if paths:
                records.append(_scan_many(label, paths, max_sample=max_s))

    # ── Single file per-symbol tables ──
    for p in [
        STORE / "stock" / "share_float" / "all.parquet",
        STORE / "stock" / "repurchase" / "all.parquet",
    ]:
        if p.exists():
            records.append(_scan_single(p.parent.name, p))

    # ── Inject source + label_zh from TABLE_META ──
    for r in records:
        src, zh = _meta(r["table"])
        r["source"] = src
        r["label_zh"] = zh

    # ── Summary ──
    n = len(records)
    total_size = sum(r["size_mb"] for r in records)
    avg_missing = round(sum(r["missing_pct"] for r in records) / max(n, 1), 2)
    total_outliers = sum(r["outlier_count"] for r in records)

    summary = [{
        "table": "__SUMMARY__",
        "source": "",
        "label_zh": "",
        "files": 0,
        "rows": 0,
        "columns": n,
        "size_mb": round(total_size, 2),
        "missing_pct": avg_missing,
        "missing_cols": "{}",
        "outlier_count": total_outliers,
        "outlier_cols": "{}",
        "freshness_days": None,
        "error": None,
    }]

    for r in records:
        r["checked_at"] = now
    for s in summary:
        s["checked_at"] = now

    result = pd.DataFrame(summary + records)
    result.to_parquet(output_path, index=False)
    print(f"Health check done: {n} logical tables, avg missing {avg_missing}%, saved to {output_path}")
    return result


if __name__ == "__main__":
    run_health_check()
