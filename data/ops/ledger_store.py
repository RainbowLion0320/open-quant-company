"""Shared parquet-backed ledger storage for ops modules."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.storage.datahub import get_datahub


class ParquetLedgerStore:
    def __init__(self, store_dir: Path, filename: str):
        self._hub = get_datahub()
        self._store = store_dir
        self._store.mkdir(parents=True, exist_ok=True)
        self.file = self._store / filename

    def append_row(self, row: dict) -> None:
        df = self.read_all()
        row_df = pd.DataFrame([row])
        if df is not None and not df.empty:
            df = pd.concat([df, row_df], ignore_index=True)
        else:
            df = row_df
        self.write_all(df)

    def read_all(self) -> pd.DataFrame:
        return self._hub.read_parquet(self.file, default=pd.DataFrame())

    def write_all(self, df: pd.DataFrame) -> None:
        self._hub.write_parquet(df, self.file)

    def clear(self) -> None:
        if self.file.exists():
            self.file.unlink()
