"""
DataContract + SchemaMigration — schema enforcement and versioning per dimension.

Every dimension in the DataRegistry can declare a DataContract that defines:
  - Expected columns and dtypes
  - Primary key columns
  - Frequency and SLA
  - PIT (point-in-time) rules
  - Schema version

On write and read, the contract validates data against the current schema.
Stored data written with an older schema version must be re-fetched.

Stored as JSON in var/store/_contracts/{dimension}.json.

Usage:
    from data.quality.contract import DataContract, load_contract

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

from data.storage.datahub import get_datahub


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
    price_mode: str = ""
    adjustment_source: str = ""
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
        """Return data only when it already matches the current schema version."""
        if from_version != self.schema_version:
            raise ValueError(
                f"Stored schema v{from_version} for {self.dimension} does not match "
                f"current schema v{self.schema_version}; re-fetch required"
            )
        return df.copy()

    def add_migration(self, to_version: int, description: str = "", **kwargs):
        """Record a new schema migration."""
        m = SchemaMigration(
            dimension=self.dimension,
            from_version=self.schema_version,
            to_version=to_version,
            description=description,
            applied_at=datetime.now().isoformat(),
            **kwargs,
        )
        self.migrations.append(m)
        self.schema_version = to_version

    # ── Persistence ──

    def save(self, store_dir: Path | None = None):
        """Save contract to var/store/_contracts/{dimension}.json."""
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
            "price_mode": self.price_mode,
            "adjustment_source": self.adjustment_source,
            "migrations": [
                {
                    "from_version": m.from_version,
                    "to_version": m.to_version,
                    "description": m.description,
                    "applied_at": m.applied_at,
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
            price_mode=data.get("price_mode", ""),
            adjustment_source=data.get("adjustment_source", ""),
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
    from data.storage.dimensions import get_registry

    registry = get_registry()
    contracts: dict[str, DataContract] = {}

    # Common column sets by dimension type
    _known_columns: dict[str, dict[str, str]] = {
        "ohlcv_daily": {
            "date": "object", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64",
        },
        "ohlcv_daily_raw": {
            "date": "object", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64",
        },
        "ohlcv_daily_hfq": {
            "date": "object", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64",
        },
        "financial_summary": {
            "报告期": "object", "净利润": "object", "净利润同比增长率": "object",
            "营业总收入": "object", "营业总收入同比增长率": "object",
            "基本每股收益": "object", "每股净资产": "object",
            "销售净利率": "object", "销售毛利率": "object",
            "净资产收益率": "object",
        },
        "fina_indicator": {
            "ts_code": "object", "ann_date": "object", "end_date": "object",
            "roe": "float64", "roa": "float64", "eps": "float64",
            "bps": "float64", "grossprofit_margin": "float64",
            "netprofit_margin": "float64", "debt_to_assets": "float64",
        },
        "valuation_daily": {
            "ts_code": "object", "trade_date": "datetime64[ns]", "close": "float64",
            "pe": "float64", "pe_ttm": "float64", "pb": "float64",
            "ps": "float64", "ps_ttm": "float64", "total_mv": "float64",
            "circ_mv": "float64",
        },
        "adj_factor": {
            "ts_code": "object", "trade_date": "object", "adj_factor": "float64",
        },
        "corporate_actions": {
            "symbol": "object", "ex_date": "datetime64[ns]",
            "cash_dividend_per_share": "float64", "share_multiplier": "float64",
        },
        "holder_number": {
            "ts_code": "object", "ann_date": "object", "end_date": "object",
            "holder_num": "float64",
        },
        "moneyflow_daily": {
            "日期": "datetime64[ns]", "收盘价": "float64", "涨跌幅": "float64",
            "主力净流入-净额": "float64", "主力净流入-净占比": "float64",
            "超大单净流入-净额": "float64", "超大单净流入-净占比": "float64",
            "大单净流入-净额": "float64", "大单净流入-净占比": "float64",
            "中单净流入-净额": "float64", "中单净流入-净占比": "float64",
            "小单净流入-净额": "float64", "小单净流入-净占比": "float64",
        },
        # P2-13: Multi-asset dimensions
        "fund_daily": {
            "date": "object", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64",
            "amount": "float64",
        },
        "bond_treasury_yields": {
            "date": "object",
            "中国国债收益率2年": "float64", "中国国债收益率5年": "float64",
            "中国国债收益率10年": "float64", "中国国债收益率30年": "float64",
            "中国国债收益率3月": "float64", "中国国债收益率1年": "float64",
            "美国国债收益率2年": "float64", "美国国债收益率5年": "float64",
            "美国国债收益率10年": "float64", "美国国债收益率30年": "float64",
        },
        "futures_daily": {
            "date": "object", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64",
            "open_interest": "float64",
        },
        # P2: Sector / Industry dimensions
        "sector_sw_daily": {
            "ts_code": "object", "trade_date": "datetime64[ns]",
            "open": "float64", "high": "float64", "low": "float64",
            "close": "float64", "vol": "float64", "amount": "float64",
            "pct_chg": "float64",
        },
        "sector_membership": {
            "symbol": "object", "sector_code": "object",
            "sector_name": "object", "sector_level": "int64",
        },
        "sector_performance_snapshot": {
            "sector_code": "object", "sector_name": "object", "date": "object",
            "return_1d": "float64", "return_5d": "float64",
            "return_20d": "float64", "return_60d": "float64",
            "volatility": "float64", "member_count": "int64",
            "latest_date": "object", "data_source": "object",
        },
        "sector_signal_snapshot": {
            "sector": "object", "sector_code": "object", "date": "object", "strategy": "object",
            "total": "int64", "buy_count": "int64", "buy_ratio": "float64",
            "avg_score": "float64", "top_symbol": "object",
        },
        "sector_exposure_snapshot": {
            "sector": "object", "date": "object",
            "weight": "float64", "market_value": "float64",
            "position_count": "int64",
        },
    }

    for key, dim in registry.all.items():
        if not dim.enabled or dim.status == "planned":
            continue

        columns = _known_columns.get(key, {})
        pk = []
        date_key = next(
            (c for c in ("date", "trade_date", "ex_date", "ann_date", "end_date", "报告期", "日期") if c in columns),
            "",
        )
        symbol_key = next((c for c in ("symbol", "ts_code") if c in columns), "")
        if date_key:
            pk = [symbol_key, date_key] if symbol_key else [date_key]
            if dim.freq in ("monthly", "quarterly") and "report_date" in columns:
                pk = [symbol_key, "report_date"] if symbol_key else ["report_date"]

        price_mode = ""
        adjustment_source = ""
        if key == "ohlcv_daily":
            price_mode = "qfq"
            adjustment_source = "provider_adjusted"
        elif key == "ohlcv_daily_raw":
            price_mode = "raw"
            adjustment_source = "raw"
        elif key == "ohlcv_daily_hfq":
            price_mode = "hfq"
            adjustment_source = "adj_factor"

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
            price_mode=price_mode,
            adjustment_source=adjustment_source,
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
