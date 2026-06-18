"""
ConfigAuditLedger — append-only audit trail for config/settings.yaml changes.

Every PUT/PATCH to the settings API records a ConfigAuditEntry:
who (source_ip), what (section + diff), and when.

Storage: var/store/_audit/config_changes.parquet (via DataHub)

Usage:
    from data.ops.audit import ConfigAuditLedger

    ledger = ConfigAuditLedger()
    change_id = ledger.record(
        section="risk_control",
        method="PATCH",
        old_data={"max_pct": 0.25},
        new_data={"max_pct": 0.30},
        source_ip="127.0.0.1",
    )
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from data.storage.datahub import get_datahub
from data.ops.ledger_store import ParquetLedgerStore


@dataclass
class ConfigAuditEntry:
    """A single config change record."""

    change_id: str
    timestamp: str
    section: str       # top-level section or "*" for full config
    method: str        # "PUT" | "PATCH"
    old_keys: list[str]
    new_keys: list[str]
    changed_keys: list[str]
    source_ip: str
    user_agent: str = ""

    def to_row(self) -> dict:
        return {
            "change_id": self.change_id,
            "timestamp": self.timestamp,
            "section": self.section,
            "method": self.method,
            "old_keys": ",".join(self.old_keys),
            "new_keys": ",".join(self.new_keys),
            "changed_keys": ",".join(self.changed_keys),
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
        }

    @classmethod
    def from_row(cls, row: dict) -> "ConfigAuditEntry":
        def _split(val) -> list[str]:
            s = str(row.get(val, ""))
            return [k for k in s.split(",") if k]

        return cls(
            change_id=str(row.get("change_id", "")),
            timestamp=str(row.get("timestamp", "")),
            section=str(row.get("section", "")),
            method=str(row.get("method", "")),
            old_keys=_split("old_keys"),
            new_keys=_split("new_keys"),
            changed_keys=_split("changed_keys"),
            source_ip=str(row.get("source_ip", "")),
            user_agent=str(row.get("user_agent", "")),
        )


class ConfigAuditLedger:
    """Append-only audit ledger for config changes."""

    def __init__(self, store_dir: Path | None = None):
        self._hub = get_datahub()
        self._store = store_dir or (self._hub.store_root / "_audit")
        self._ledger = ParquetLedgerStore(self._store, "config_changes.parquet")
        self._file = self._ledger.file

    def record(
        self,
        section: str = "*",
        method: str = "PUT",
        old_data: dict | None = None,
        new_data: dict | None = None,
        source_ip: str = "",
        user_agent: str = "",
    ) -> str:
        """Record a config change. Returns change_id."""
        old = old_data or {}
        new = new_data or {}
        old_keys = sorted(old.keys())
        new_keys = sorted(new.keys())

        # Determine which keys changed
        all_keys = set(old_keys) | set(new_keys)
        changed = []
        for k in sorted(all_keys):
            old_v = old.get(k)
            new_v = new.get(k)
            if old_v != new_v:
                changed.append(k)

        change_id = f"cfg_{uuid.uuid4().hex[:12]}"
        entry = ConfigAuditEntry(
            change_id=change_id,
            timestamp=datetime.now().isoformat(),
            section=section,
            method=method,
            old_keys=old_keys,
            new_keys=new_keys,
            changed_keys=changed,
            source_ip=source_ip,
            user_agent=user_agent,
        )
        self._append(entry)
        return change_id

    def _append(self, entry: ConfigAuditEntry):
        self._ledger.append_row(entry.to_row())

    def _all(self) -> pd.DataFrame:
        return self._ledger.read_all()

    def _write_all(self, df: pd.DataFrame):
        self._ledger.write_all(df)

    # ── Queries ──

    def history(
        self,
        section: str = "",
        limit: int = 50,
    ) -> list[ConfigAuditEntry]:
        """Query audit history, optionally filtered by section."""
        df = self._all()
        if df.empty:
            return []

        if section:
            df = df[df["section"] == section]

        df = df.sort_values("timestamp", ascending=False).head(limit)
        return [ConfigAuditEntry.from_row(row.to_dict()) for _, row in df.iterrows()]

    def last_change(self, section: str = "") -> ConfigAuditEntry | None:
        """Most recent config change, optionally filtered by section."""
        df = self._all()
        if df.empty:
            return None
        if section:
            df = df[df["section"] == section]
        if df.empty:
            return None
        latest = df.sort_values("timestamp", ascending=False).iloc[0]
        return ConfigAuditEntry.from_row(latest.to_dict())

    def summary(self) -> dict:
        """Aggregated audit stats."""
        df = self._all()
        if df.empty:
            return {"total_changes": 0, "last_change_at": None, "sections_touched": []}

        sections = (
            sorted(df["section"].unique().tolist())
            if "section" in df.columns
            else []
        )
        return {
            "total_changes": len(df),
            "last_change_at": str(df["timestamp"].max()) if "timestamp" in df.columns else None,
            "sections_touched": sections,
        }

    def clear(self):
        """Remove all audit records (for testing)."""
        self._ledger.clear()
