"""
DataContract + SchemaMigration — schema enforcement and versioning per dimension.

Every dimension in the DataRegistry can declare a DataContract that defines:
  - Expected columns and dtypes
  - Primary key columns
  - Frequency and SLA
  - PIT (point-in-time) rules
  - Schema version

On write, the contract validates incoming data. On read, it checks compatibility
and can coerce/migrate stale schemas.

Stored as JSON in data/store/_contracts/{dimension}.json.

Usage:
    from data.contract import DataContract, load_contract

    contract = load_contract("ohlcv_daily")
    issues = contract.validate(df)
    if issues:
        for i in issues:
            print(i)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from data.datahub import get_datahub


# ── Contract Violation ──


@dataclass
class ContractViolation:
    dimension: str
    severity: str  # "error" | "warning"
    rule: str      # "missing_column" | "dtype_mismatch" | "null_pk" | "duplicate_pk" | "schema_version"
    detail: str


# ── Schema Migration ──


@dataclass
class SchemaMigration:
    """Records a schema change for a dimension."""
    dimension: str
    from_version: int
    to_version: int
    description: str = ""
    applied_at: str = ""
    # How to handle existing data written with the old schema:
    #   "strict": reject reads (data must be re-fetched)
    #   "coerce": add missing columns as null, cast dtypes
    #   "drop": drop extra columns not in the new schema
    compat: str = "coerce"
    # Optional: columns added/removed/renamed
    added_columns: dict[str, str] = field(default_factory=dict)    # name → dtype
    removed_columns: list[str] = field(default_factory=list)
    renamed_columns: dict[str, str] = field(default_factory=dict)  # old → new


# ── DataContract ──


# Known dtype mappings for validation
_DTYPE_MAP: dict[str, type | str] = {
    "int64": "int64", "int32": "int32", "int": "int64",
    "float64": "float64", "float": "float64", "double": "float64",
    "object": "object", "str": "object", "string": "object",
    "bool": "bool",
    "datetime64[ns]": "datetime64[ns]", "datetime": "datetime64[ns]",
    "date": "object",
    "category": "category",
}


@dataclass
class DataContract:
    """Schema and quality contract for one data dimension."""

    dimension: str
    schema_version: int = 1
    columns: dict[str, str] = field(default_factory=dict)    # name → dtype
    primary_key: list[str] = field(default_factory=list)
    freq: str = "daily"
    sla_days: int = 5
    pit_rule: str = "none"  # "as_of_date" | "latest" | "none"
    owner: str = ""
    description: str = ""
    migrations: list[SchemaMigration] = field(default_factory=list)

    # ── Validation ──

    def validate(self, df: pd.DataFrame) -> list[ContractViolation]:
        """Validate a DataFrame against this contract. Returns all violations."""
        issues: list[ContractViolation] = []
        dim = self.dimension

        if df is None or df.empty:
            issues.append(ContractViolation(dim, "warning", "empty_data", "DataFrame is empty"))
            return issues

        # Check required columns
        for col, expected_dtype in self.columns.items():
            if col not in df.columns:
                issues.append(ContractViolation(
                    dim, "error", "missing_column",
                    f"Required column '{col}' ({expected_dtype}) is missing",
                ))
            else:
                actual = str(df[col].dtype)
                if not self._dtype_compatible(actual, expected_dtype):
                    issues.append(ContractViolation(
                        dim, "warning", "dtype_mismatch",
                        f"Column '{col}': expected {expected_dtype}, got {actual}",
                    ))

        # Check primary key
        if self.primary_key:
            pk_cols = [c for c in self.primary_key if c in df.columns]
            if pk_cols:
                null_mask = df[pk_cols].isnull().any(axis=1)
                if null_mask.any():
                    issues.append(ContractViolation(
                        dim, "error", "null_pk",
                        f"Primary key {pk_cols} has {null_mask.sum()} null rows",
                    ))
                dup_mask = df.duplicated(subset=pk_cols, keep=False)
                if dup_mask.any():
                    issues.append(ContractViolation(
                        dim, "warning", "duplicate_pk",
                        f"Primary key {pk_cols} has {dup_mask.sum()} duplicate rows",
                    ))

        # Check extra columns
        extra = set(df.columns) - set(self.columns.keys())
        if extra:
            issues.append(ContractViolation(
                dim, "warning", "extra_columns",
                f"Unexpected columns: {', '.join(sorted(extra))}",
            ))

        return issues

    def is_valid(self, df: pd.DataFrame) -> bool:
        """True if no error-level violations exist."""
        return not any(v.severity == "error" for v in self.validate(df))

    def _dtype_compatible(self, actual: str, expected: str) -> bool:
        """Check if actual pandas dtype is compatible with the expected dtype."""
        actual = actual.lower()
        expected = expected.lower()

        if actual == expected:
            return True
        # Common compatible pairs
        compat_pairs = {
            ("int64", "int32"), ("int32", "int64"),
            ("float64", "int64"), ("float64", "int32"),
            ("object", "str"), ("object", "string"),
            ("datetime64[ns]", "datetime64[ns, utc]"),
        }
        return (actual, expected) in compat_pairs or (expected, actual) in compat_pairs

    # ── Migration ──

    def migrate(self, df: pd.DataFrame, from_version: int) -> pd.DataFrame:
        """Apply schema migrations to bring df from from_version to current."""
        result = df.copy()
        applicable = [m for m in self.migrations
                      if m.from_version >= from_version and m.to_version <= self.schema_version]
        applicable.sort(key=lambda m: m.from_version)

        for migration in applicable:
            if migration.compat == "strict":
                raise ValueError(
                    f"Schema migration {migration.from_version}→{migration.to_version} "
                    f"for {self.dimension} requires re-fetch (strict mode)"
                )
            result = self._apply_migration(result, migration)

        return result

    def _apply_migration(self, df: pd.DataFrame, migration: SchemaMigration) -> pd.DataFrame:
        result = df.copy()

        # Add missing columns
        for col, dtype in migration.added_columns.items():
            if col not in result.columns:
                result[col] = pd.Series(dtype="float64" if "float" in dtype else "object")

        # Remove columns
        for col in migration.removed_columns:
            if col in result.columns:
                result.drop(columns=[col], inplace=True)

        # Rename columns
        result.rename(columns=migration.renamed_columns, inplace=True)

        return result

    def add_migration(self, to_version: int, description: str = "",
                      compat: str = "coerce", **kwargs):
        """Record a new schema migration."""
        m = SchemaMigration(
            dimension=self.dimension,
            from_version=self.schema_version,
            to_version=to_version,
            description=description,
            applied_at=datetime.now().isoformat(),
            compat=compat,
            **kwargs,
        )
        self.migrations.append(m)
        self.schema_version = to_version

    # ── Persistence ──

    def save(self, store_dir: Path | None = None):
        """Save contract to data/store/_contracts/{dimension}.json."""
        if store_dir is None:
            hub = get_datahub()
            store_dir = hub.store_root / "_contracts"
        store_dir.mkdir(parents=True, exist_ok=True)

        path = store_dir / f"{self.dimension}.json"
        data = {
            "dimension": self.dimension,
            "schema_version": self.schema_version,
            "columns": self.columns,
            "primary_key": self.primary_key,
            "freq": self.freq,
            "sla_days": self.sla_days,
            "pit_rule": self.pit_rule,
            "owner": self.owner,
            "description": self.description,
            "migrations": [
                {
                    "from_version": m.from_version,
                    "to_version": m.to_version,
                    "description": m.description,
                    "applied_at": m.applied_at,
                    "compat": m.compat,
                    "added_columns": m.added_columns,
                    "removed_columns": m.removed_columns,
                    "renamed_columns": m.renamed_columns,
                }
                for m in self.migrations
            ],
            "updated_at": datetime.now().isoformat(),
        }
        hub = get_datahub()
        hub.write_json(data, path, indent=2)

    @classmethod
    def load(cls, dimension: str, store_dir: Path | None = None) -> "DataContract | None":
        """Load contract from store. Returns None if not found."""
        if store_dir is None:
            hub = get_datahub()
            store_dir = hub.store_root / "_contracts"
        path = store_dir / f"{dimension}.json"
        if not path.exists():
            return None
        hub = get_datahub()
        data = hub.read_json(path)
        if not data:
            return None

        migrations = [
            SchemaMigration(
                dimension=dimension,
                from_version=m["from_version"],
                to_version=m["to_version"],
                description=m.get("description", ""),
                applied_at=m.get("applied_at", ""),
                compat=m.get("compat", "coerce"),
                added_columns=m.get("added_columns", {}),
                removed_columns=m.get("removed_columns", []),
                renamed_columns=m.get("renamed_columns", {}),
            )
            for m in data.get("migrations", [])
        ]

        return cls(
            dimension=dimension,
            schema_version=data.get("schema_version", 1),
            columns=data.get("columns", {}),
            primary_key=data.get("primary_key", []),
            freq=data.get("freq", "daily"),
            sla_days=data.get("sla_days", 5),
            pit_rule=data.get("pit_rule", "none"),
            owner=data.get("owner", ""),
            description=data.get("description", ""),
            migrations=migrations,
        )

    def __repr__(self) -> str:
        return (f"<DataContract {self.dimension} v{self.schema_version} "
                f"cols={len(self.columns)} pk={self.primary_key}>")


# ── Auto-generate contracts from DataRegistry ──


def derive_contracts_from_registry() -> dict[str, DataContract]:
    """Generate default DataContracts from the DataRegistry dimensions.

    These are best-effort defaults. Explicit contracts saved to _contracts/
    override these auto-derived ones.
    """
    from data.data_registry import get_registry

    registry = get_registry()
    contracts: dict[str, DataContract] = {}

    # Common column sets by dimension type
    _known_columns: dict[str, dict[str, str]] = {
        "ohlcv_daily": {
            "date": "object", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64",
        },
        "financial_summary": {
            "symbol": "object", "date": "object", "report_date": "object",
            "revenue": "float64", "net_profit": "float64",
            "total_assets": "float64", "total_equity": "float64",
            "roe": "float64", "eps": "float64", "bps": "float64",
        },
        "fina_indicator": {
            "ts_code": "object", "ann_date": "object", "end_date": "object",
            "roe": "float64", "roa": "float64", "eps": "float64",
            "bps": "float64", "grossprofit_margin": "float64",
            "netprofit_margin": "float64", "debt_to_assets": "float64",
        },
        "valuation_daily": {
            "date": "object", "pe": "float64", "pb": "float64", "ps": "float64",
            "total_mv": "float64", "circ_mv": "float64",
        },
        "adj_factor": {
            "date": "object", "adj_factor": "float64",
        },
        "holder_number": {
            "ts_code": "object", "ann_date": "object", "end_date": "object",
            "holder_num": "float64",
        },
        "moneyflow_daily": {
            "date": "object", "main_net_inflow": "float64",
            "super_large_net_inflow": "float64", "large_net_inflow": "float64",
            "medium_net_inflow": "float64", "small_net_inflow": "float64",
        },
    }

    for key, dim in registry.all.items():
        if not dim.enabled or dim.status == "planned":
            continue

        columns = _known_columns.get(key, {})
        pk = []
        if "date" in columns or "trade_date" in columns:
            pk = ["symbol", "date"] if "symbol" in columns else ["date"]
            if dim.freq in ("monthly", "quarterly") and "report_date" in columns:
                pk = ["symbol", "report_date"] if "symbol" in columns else ["report_date"]

        contracts[key] = DataContract(
            dimension=key,
            schema_version=1,
            columns=columns,
            primary_key=pk,
            freq=dim.freq,
            sla_days=dim.freshness_sla_days or 5,
            pit_rule="as_of_date" if key.startswith("ohlcv") else "none",
            owner=dim.source or dim.asset,
            description=dim.description or dim.label,
        )

    return contracts


# ── Contract store helpers ──


def load_contract(dimension: str) -> DataContract | None:
    """Load an explicit contract, falling back to auto-derived."""
    contract = DataContract.load(dimension)
    if contract is not None:
        return contract

    derived = derive_contracts_from_registry()
    return derived.get(dimension)


def save_contract(contract: DataContract):
    """Save a contract to the store."""
    contract.save()


def list_contracts() -> list[DataContract]:
    """List all contracts (explicit + derived)."""
    derived = derive_contracts_from_registry()

    # Overlay explicit contracts
    hub = get_datahub()
    contracts_dir = hub.store_root / "_contracts"
    if contracts_dir.exists():
        for f in sorted(contracts_dir.glob("*.json")):
            dim = f.stem
            explicit = DataContract.load(dim)
            if explicit:
                derived[dim] = explicit

    return list(derived.values())
