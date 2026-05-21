#!/usr/bin/env python3
"""
Ingest DeepSeek usage CSV exports into DataHub Parquet store.

The DeepSeek platform exports two CSV files when clicking "导出":
  - amount-YYYY-M.csv: per-day per-model token counts by type
  - cost-YYYY-M.csv:   per-day per-model cost in CNY

This script pivots both into a unified daily summary:

  utc_date | model | input_cache_miss | input_cache_hit | output_tokens |
  request_count | cost_cny | total_tokens

Usage:
  python scripts/ingest_deepseek_usage.py ~/Downloads/usage_data_2026_5.zip
  python scripts/ingest_deepseek_usage.py /path/to/export/dir/
"""

import sys
import zipfile
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

# ── Allow both direct CSV dir and zip
PROJECT_ROOT = Path(__file__).resolve().parent.parent
from data.datahub import get_datahub


def find_csv(path: Path) -> tuple[Path, Path]:
    """Locate amount-*csv and cost-*csv from a dir or zip."""
    if path.suffix == ".zip":
        tmp = tempfile.mkdtemp(prefix="deepseek_usage_")
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        path = Path(tmp)

    amounts = sorted(path.glob("amount-*.csv"))
    costs = sorted(path.glob("cost-*.csv"))
    if not amounts or not costs:
        raise FileNotFoundError(f"No amount-*.csv / cost-*.csv found in {path}")
    return amounts[-1], costs[-1]


def ingest(source: Path) -> pd.DataFrame:
    hub = get_datahub()

    amt_path, cst_path = find_csv(source)
    amount = pd.read_csv(amt_path)
    cost = pd.read_csv(cst_path)

    # Normalize columns
    amount.columns = [c.strip().lstrip("\ufeff") for c in amount.columns]
    cost.columns = [c.strip().lstrip("\ufeff") for c in cost.columns]

    # Pivot amount: each type → column
    amt_pivot = amount.pivot_table(
        index=["utc_date", "model"],
        columns="type",
        values="amount",
        aggfunc="sum",
    ).reset_index()
    # Rename columns
    rename = {
        "input_cache_miss_tokens": "input_cache_miss",
        "input_cache_hit_tokens": "input_cache_hit",
        "output_tokens": "output_tokens",
        "request_count": "requests",
    }
    amt_pivot.rename(columns={k: v for k, v in rename.items() if k in amt_pivot.columns}, inplace=True)

    # Merge cost
    cost_clean = cost[["utc_date", "model", "cost"]].rename(columns={"cost": "cost_cny"})
    df = amt_pivot.merge(cost_clean, on=["utc_date", "model"], how="left")
    df["cost_cny"] = df["cost_cny"].fillna(0)

    # Derived
    df["utc_date"] = pd.to_datetime(df["utc_date"]).dt.strftime("%Y-%m-%d")
    for col in ["input_cache_miss", "input_cache_hit", "output_tokens", "requests", "cost_cny"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64" if col != "cost_cny" else "float64")

    # Total tokens (excluding cache_hit since it's free)
    df["total_tokens"] = df["input_cache_miss"] + df["output_tokens"]

    # Sort
    df = df.sort_values(["utc_date", "model"]).reset_index(drop=True)

    # Store
    out = hub.store_dir("deepseek") / "daily_usage.parquet"
    hub.write_parquet(df, out)
    print(f"Written {len(df)} rows to {out}")
    print(df.tail(10).to_string(index=False))
    return df


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads"
    ingest(src)
