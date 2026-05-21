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

from data.datahub import get_datahub
from data.data_registry import HealthTableMeta, get_registry

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
        if str(dc).lower() not in ("date", "trade_date", "ann_date", "end_date", "ts", "quarter", "utc_date", "month") and str(dc) not in ("日期", "报告期"):
            continue
        try:
            s = pd.to_datetime(df[dc], errors="coerce").dropna()
            if len(s) == 0:
                continue
            return (date.today() - s.max().date()).days
        except Exception:
            continue
    return None


def _manifest_for_file(path: Path) -> dict:
    manifest = HUB.manifest_for(path)
    if not manifest:
        return {
            "manifest_files": 0, "manifest_updated_at": "",
            "schema_hash": "", "file_sha256": "",
        }
    return {
        "manifest_files": 1,
        "manifest_updated_at": str(manifest.get("updated_at", "") or ""),
        "schema_hash": str(manifest.get("schema_hash", "") or ""),
        "file_sha256": str(manifest.get("file_sha256", "") or ""),
    }


def _manifest_for_many(paths: list[Path]) -> dict:
    manifest = HUB.read_manifest()
    if manifest.empty or "path" not in manifest.columns or not paths:
        return {
            "manifest_files": 0, "manifest_updated_at": "",
            "schema_hash": "", "file_sha256": "",
        }
    rel_paths = set()
    for path in paths:
        try:
            rel_paths.add(str(path.resolve().relative_to(HUB.project_root)))
        except ValueError:
            rel_paths.add(str(path.resolve()))
    rows = manifest[manifest["path"].isin(rel_paths)]
    if rows.empty:
        return {
            "manifest_files": 0, "manifest_updated_at": "",
            "schema_hash": "", "file_sha256": "",
        }
    hashes = sorted({str(v) for v in rows.get("schema_hash", []) if str(v)})
    return {
        "manifest_files": int(len(rows)),
        "manifest_updated_at": str(rows["updated_at"].max()) if "updated_at" in rows.columns else "",
        "schema_hash": hashes[0] if len(hashes) == 1 else ("mixed" if hashes else ""),
        "file_sha256": "",
    }


def _find_date_col(df: pd.DataFrame) -> Optional[str]:
    """Find a date-like column in the DataFrame."""
    for dc in df.columns:
        if str(dc).lower() in ("date", "trade_date", "ann_date", "end_date", "ts", "quarter", "utc_date", "month") or str(dc) in ("日期", "报告期"):
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
            **_manifest_for_file(path),
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
            **_manifest_for_file(path),
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
            "manifest_files": 0, "manifest_updated_at": "", "schema_hash": "", "file_sha256": "",
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
        **_manifest_for_many(paths),
    }


def run_health_check(output_path: Optional[Path] = None) -> pd.DataFrame:
    if output_path is None:
        output_path = STORE / "db_health.parquet"

    records = []
    now = datetime.now().isoformat()

    def _repairable_tables() -> set[str]:
        try:
            from scripts.repair_table import REPAIR_MAP
            return set(REPAIR_MAP)
        except Exception:
            return set()

    meta_map = get_registry().health_metadata(repairable_tables=_repairable_tables())

    def _meta(table_name: str) -> HealthTableMeta:
        if table_name.startswith("features_"):
            month = table_name.removeprefix("features_")
            return HealthTableMeta("features_all", "Computed (多源融合)", f"PIT 特征切片 {month}", partition_key="month")
        return meta_map.get(table_name, HealthTableMeta(table_name, "", ""))

    def _scan_dimension(dim) -> None:
        if not dim.cache:
            return
        table = dim.health_table
        root = HUB.dimension_root(dim.key)
        if "{" not in dim.cache:
            if root.exists() and root.is_file():
                records.append(_scan_single(table, root))
            else:
                records.append(_scan_many(table, [], max_sample=dim.health_max_sample))
            return
        paths = sorted(root.glob("*.parquet")) if root.exists() else []
        records.append(_scan_many(table, paths, max_sample=dim.health_max_sample))

    # ── Registry dimensions (source/path/label/SLA live in data_registry) ──
    for dim in get_registry().get_enabled():
        if dim.health_enabled:
            _scan_dimension(dim)

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

    # ── data/cache/api/ (AKShare API response cache) ──
    api_cache = STORE.parent / "cache" / "api"
    if api_cache.exists():
        paths = sorted(api_cache.glob("*.parquet"))
        if paths:
            records.append(_scan_many("cache_api_calls", paths, max_sample=50, source="AKShare Cache"))

    def _freshness_status(row: dict, sla: Optional[int]) -> str:
        if int(row.get("files") or 0) == 0:
            return "missing"
        if row.get("error"):
            return "error"
        days = row.get("freshness_days")
        if days is None or pd.isna(days):
            return "unknown"
        if sla is None:
            return "untracked"
        return "fresh" if int(days) <= int(sla) else "stale"

    # ── Inject source/label/SLA/repair metadata from data_registry ──
    for r in records:
        meta = _meta(r["table"])
        r["source"] = meta.source
        r["label_zh"] = meta.label_zh
        r["repairable"] = meta.repairable
        r["registry_key"] = meta.registry_key
        r["freshness_sla_days"] = meta.freshness_sla_days
        r["repair_policy"] = meta.repair_policy
        r["partition_key"] = meta.partition_key
        r["freshness_status"] = _freshness_status(r, meta.freshness_sla_days)

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
        "freshness_sla_days": None,
        "freshness_status": "summary",
        "registry_key": "",
        "partition_key": "",
        "repair_policy": "none",
        "time_breakdown": "{}",
        "error": None,
        "manifest_files": sum(int(r.get("manifest_files") or 0) for r in records),
        "manifest_updated_at": "",
        "schema_hash": "",
        "file_sha256": "",
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
