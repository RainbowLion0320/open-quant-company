"""
BackfillLedger — append-only ledger for data repair and backfill operations.

Every repair_table.py run records a BackfillEntry: what dimension, what date
range, how many rows, success or failure.  This makes backfill operations
auditable and queryable — you can check when a dimension was last repaired,
whether it succeeded, and how many retries it took.

Storage: var/store/_backfill/ledger.parquet (via DataHub)

Usage:
    from data.ops.backfill import BackfillLedger

    ledger = BackfillLedger()
    run_id = ledger.start("ohlcv_daily", date_start="20200101", date_end="20260522")
    try:
        df = fetch_data(...)
        ledger.complete(run_id, rows_fetched=len(df))
    except Exception as e:
        ledger.fail(run_id, error=str(e))
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from data.storage.datahub import get_datahub


# ── Backfill Entry ──


@dataclass
class BackfillEntry:
    """A single backfill/repair operation record."""

    run_id: str
    dimension: str
    status: str  # "running" | "done" | "failed"
    date_start: str = ""
    date_end: str = ""
    rows_fetched: int = 0
    rows_before: int = 0
    error: str = ""
    retry_count: int = 0
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    triggered_by: str = ""  # "cron" | "manual" | "auto"

    def to_row(self) -> dict:
        return {
            "run_id": self.run_id,
            "dimension": self.dimension,
            "status": self.status,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "rows_fetched": self.rows_fetched,
            "rows_before": self.rows_before,
            "error": self.error,
            "retry_count": self.retry_count,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "triggered_by": self.triggered_by,
        }

    @classmethod
    def from_row(cls, row: dict) -> "BackfillEntry":
        return cls(
            run_id=str(row.get("run_id", "")),
            dimension=str(row.get("dimension", "")),
            status=str(row.get("status", "")),
            date_start=str(row.get("date_start", "")),
            date_end=str(row.get("date_end", "")),
            rows_fetched=int(row.get("rows_fetched", 0)),
            rows_before=int(row.get("rows_before", 0)),
            error=str(row.get("error", "")),
            retry_count=int(row.get("retry_count", 0)),
            started_at=str(row.get("started_at", "")),
            completed_at=str(row.get("completed_at", "")),
            duration_seconds=float(row.get("duration_seconds", 0)),
            triggered_by=str(row.get("triggered_by", "")),
        )


# ── Ledger ──


class BackfillLedger:
    """Append-only ledger for data backfill operations."""

    def __init__(self, store_dir: Path | None = None):
        self._hub = get_datahub()
        self._store = store_dir or (self._hub.store_root / "_backfill")
        self._store.mkdir(parents=True, exist_ok=True)
        self._file = self._store / "ledger.parquet"

    # ── Lifecycle ──

    def start(
        self,
        dimension: str,
        date_start: str = "",
        date_end: str = "",
        triggered_by: str = "manual",
        rows_before: int = 0,
    ) -> str:
        """Begin a backfill operation. Returns a run_id to use with complete/fail."""
        run_id = f"bf_{uuid.uuid4().hex[:12]}"
        entry = BackfillEntry(
            run_id=run_id,
            dimension=dimension,
            status="running",
            date_start=date_start,
            date_end=date_end,
            rows_before=rows_before,
            started_at=datetime.now().isoformat(),
            triggered_by=triggered_by,
        )
        self._append(entry)
        return run_id

    def complete(self, run_id: str, rows_fetched: int = 0):
        """Mark a backfill as successfully completed."""
        self._update(run_id, status="done", rows_fetched=rows_fetched)

    def fail(self, run_id: str, error: str = ""):
        """Mark a backfill as failed."""
        self._update(run_id, status="failed", error=error[:500])

    def _update(self, run_id: str, **fields):
        df = self._all()
        if df.empty or "run_id" not in df.columns:
            return

        mask = df["run_id"] == run_id
        if not mask.any():
            return

        for key, value in fields.items():
            df.loc[mask, key] = value

        started = df.loc[mask, "started_at"].iloc[0] if "started_at" in df.columns else ""
        if started:
            try:
                start_ts = datetime.fromisoformat(str(started))
                elapsed = (datetime.now() - start_ts).total_seconds()
                df.loc[mask, "duration_seconds"] = elapsed
            except (ValueError, TypeError):
                pass

        df.loc[mask, "completed_at"] = datetime.now().isoformat()
        self._write_all(df)

    def _append(self, entry: BackfillEntry):
        df = self._all()
        row = pd.DataFrame([entry.to_row()])
        if df is not None and not df.empty:
            df = pd.concat([df, row], ignore_index=True)
        else:
            df = row
        self._write_all(df)

    def _all(self) -> pd.DataFrame:
        return self._hub.read_parquet(
            self._file,
            default=pd.DataFrame(),
        )

    def _write_all(self, df: pd.DataFrame):
        self._hub.write_parquet(df, self._file)

    # ── Queries ──

    def last_run(self, dimension: str) -> BackfillEntry | None:
        """Most recent backfill for a dimension."""
        df = self._all()
        if df.empty or "dimension" not in df.columns:
            return None
        mask = df["dimension"] == dimension
        if not mask.any():
            return None
        latest = df[mask].sort_values("started_at", ascending=False).iloc[0]
        return BackfillEntry.from_row(latest.to_dict())

    def last_successful(self, dimension: str) -> BackfillEntry | None:
        """Most recent successful backfill for a dimension."""
        df = self._all()
        if df.empty:
            return None
        mask = (df["dimension"] == dimension) & (df["status"] == "done")
        if not mask.any():
            return None
        latest = df[mask].sort_values("started_at", ascending=False).iloc[0]
        return BackfillEntry.from_row(latest.to_dict())

    def history(
        self,
        dimension: str = "",
        limit: int = 20,
        status: str = "",
    ) -> list[BackfillEntry]:
        """Query backfill history, optionally filtered."""
        df = self._all()
        if df.empty:
            return []

        if dimension:
            df = df[df["dimension"] == dimension]
        if status:
            df = df[df["status"] == status]

        df = df.sort_values("started_at", ascending=False).head(limit)
        return [BackfillEntry.from_row(row.to_dict()) for _, row in df.iterrows()]

    def running(self) -> list[BackfillEntry]:
        """All currently-running backfill operations."""
        return self.history(status="running", limit=100)

    def needs_retry(self, dimension: str = "", max_retries: int = 3) -> list[BackfillEntry]:
        """Failed backfills that haven't exceeded max retries."""
        df = self._all()
        if df.empty:
            return []

        mask = (df["status"] == "failed") & (df["retry_count"] < max_retries)
        if dimension:
            mask &= df["dimension"] == dimension
        if not mask.any():
            return []

        df = df[mask].sort_values("started_at", ascending=False)
        return [BackfillEntry.from_row(row.to_dict()) for _, row in df.iterrows()]

    def retry(self, dimension: str, date_start: str = "", date_end: str = "") -> str:
        """Retry a failed backfill. Increments retry_count on the failed entry."""
        last = self.last_run(dimension)
        retry_count = (last.retry_count + 1) if last else 0
        run_id = self.start(
            dimension,
            date_start=date_start or (last.date_start if last else ""),
            date_end=date_end or (last.date_end if last else ""),
            triggered_by="auto",
        )
        # Update retry count in the new entry
        df = self._all()
        mask = df["run_id"] == run_id
        if mask.any():
            df.loc[mask, "retry_count"] = retry_count
            self._write_all(df)
        return run_id

    # ── Summary ──

    def summary(self) -> dict:
        """Aggregated backfill stats."""
        df = self._all()
        if df.empty:
            return {
                "total_runs": 0,
                "done": 0,
                "failed": 0,
                "running": 0,
                "dimensions_repaired": 0,
            }

        dims = df["dimension"].nunique() if "dimension" in df.columns else 0
        return {
            "total_runs": len(df),
            "done": int((df["status"] == "done").sum()),
            "failed": int((df["status"] == "failed").sum()),
            "running": int((df["status"] == "running").sum()),
            "dimensions_repaired": dims,
            "last_run_at": str(df["started_at"].max()) if "started_at" in df.columns else None,
        }

    # ── Clear ──

    def clear(self):
        """Remove all backfill records (for testing)."""
        if self._file.exists():
            self._file.unlink()
