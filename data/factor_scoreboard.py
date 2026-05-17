"""
Factor Scoreboard — 因子有效性历史追踪

存储: data/models/factor_scoreboard.parquet
每次 factor_hypothesis 运行后追加，支持查询哪些因子长期有效。
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from data.datahub import get_datahub

HUB = get_datahub()
SCOREBOARD_PATH = HUB.model_path("factor_scoreboard")

COLUMNS = [
    "name", "formula", "ic", "ic_std", "icir", "oos_ic",
    "round_num", "passed", "timestamp",
]


def load() -> pd.DataFrame:
    """Load existing scoreboard."""
    if SCOREBOARD_PATH.exists():
        return HUB.read_parquet(SCOREBOARD_PATH)
    return pd.DataFrame(columns=COLUMNS)


def record(candidates: List[dict]) -> None:
    """Append factor evaluation results to scoreboard."""
    df = load()
    now = datetime.now().isoformat()
    rows = []
    for c in candidates:
        rows.append({
            "name": c.get("name", ""),
            "formula": c.get("formula", ""),
            "ic": c.get("ic", 0),
            "ic_std": c.get("ic_std", 0),
            "icir": c.get("icir", 0),
            "oos_ic": c.get("oos_ic", 0),
            "round_num": c.get("round_num", 0),
            "passed": c.get("passed_oos", False),
            "timestamp": now,
        })
    new = pd.DataFrame(rows, columns=COLUMNS)
    df = pd.concat([df, new], ignore_index=True)
    HUB.write_parquet(df, SCOREBOARD_PATH)


def top_factors(min_icir: float = 0.2, min_tests: int = 2) -> pd.DataFrame:
    """Return factors that consistently pass, sorted by mean ICIR."""
    df = load()
    if len(df) < 2:
        return df
    # Group by factor name, compute average stats
    grouped = df.groupby("name").agg(
        mean_ic=("ic", "mean"),
        mean_icir=("icir", "mean"),
        mean_oos=("oos_ic", "mean"),
        pass_rate=("passed", "mean"),
        tests=("name", "count"),
    ).reset_index()
    # Filter
    valid = grouped[(grouped["mean_icir"] >= min_icir) & (grouped["tests"] >= min_tests)]
    return valid.sort_values("mean_icir", ascending=False)


def summary() -> str:
    """Human-readable scoreboard summary."""
    df = load()
    if len(df) == 0:
        return "Scoreboard empty"
    lines = [f"Factor Scoreboard: {len(df)} records, {df['name'].nunique()} unique factors"]
    passed = df[df["passed"] == True]
    lines.append(f"  Passed: {len(passed)} ({len(passed)/max(len(df),1)*100:.0f}%)")
    if len(passed):
        best = passed.loc[passed["icir"].idxmax()]
        lines.append(f"  Best: {best['name']} (ICIR={best['icir']:.2f}, OOS_IC={best['oos_ic']:.4f})")
    return "\n".join(lines)
