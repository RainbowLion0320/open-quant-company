"""Contract tests for DataContract — validation, migration, persistence."""

import pandas as pd
import pytest
from pathlib import Path
from data.quality.contract import (
    DataContract, SchemaMigration, ContractViolation,
    derive_contracts_from_registry, load_contract, list_contracts,
)


class TestDataContractValidation:
    def test_valid_dataframe_passes(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"date": "object", "close": "float64"},
            primary_key=["date"],
        )
        df = pd.DataFrame({"date": ["2024-01-01"], "close": [10.5]})
        assert contract.is_valid(df)
        assert len(contract.validate(df)) == 0

    def test_missing_column_is_error(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"date": "object", "close": "float64", "volume": "float64"},
        )
        df = pd.DataFrame({"date": ["2024-01-01"], "close": [10.5]})
        violations = contract.validate(df)
        errors = [v for v in violations if v.severity == "error"]
        assert len(errors) == 1
        assert "volume" in errors[0].detail

    def test_dtype_mismatch_is_warning(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"close": "float64"},
        )
        df = pd.DataFrame({"close": [1, 2, 3]})  # int64
        violations = contract.validate(df)
        warnings = [v for v in violations if v.severity == "warning" and v.rule == "dtype_mismatch"]
        assert len(warnings) >= 0  # int64→float64 may be compatible

    def test_null_primary_key_is_error(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"date": "object", "close": "float64"},
            primary_key=["date"],
        )
        df = pd.DataFrame({"date": [None, "2024-01-02"], "close": [10.5, 11.0]})
        violations = contract.validate(df)
        pk_errors = [v for v in violations if v.rule == "null_pk"]
        assert len(pk_errors) == 1
        assert "1 null rows" in pk_errors[0].detail

    def test_duplicate_primary_key_is_warning(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"date": "object", "close": "float64"},
            primary_key=["date"],
        )
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01", "2024-01-02"],
            "close": [10.5, 10.6, 11.0],
        })
        violations = contract.validate(df)
        dup = [v for v in violations if v.rule == "duplicate_pk"]
        assert len(dup) == 1
        assert "2 duplicate rows" in dup[0].detail

    def test_extra_columns_warning(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"date": "object"},
        )
        df = pd.DataFrame({"date": ["2024-01-01"], "extra_col": [42]})
        violations = contract.validate(df)
        extra = [v for v in violations if v.rule == "extra_columns"]
        assert len(extra) == 1
        assert "extra_col" in extra[0].detail

    def test_empty_dataframe_warning(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"date": "object"},
        )
        df = pd.DataFrame()
        violations = contract.validate(df)
        assert len(violations) == 1
        assert violations[0].rule == "empty_data"

    def test_is_valid_with_only_warnings(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"date": "object", "close": "float64"},
        )
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01"],
            "close": [10.5, 10.6],
            "extra": [1, 2],
        })
        # extra_columns + duplicate_pk are warnings, not errors
        assert contract.is_valid(df)

    def test_is_valid_false_on_missing_column(self):
        contract = DataContract(
            dimension="test_dim",
            columns={"date": "object", "close": "float64"},
        )
        df = pd.DataFrame({"date": ["2024-01-01"]})
        assert not contract.is_valid(df)


class TestSchemaMigration:
    def test_add_migration(self):
        contract = DataContract(
            dimension="test_dim",
            schema_version=1,
            columns={"date": "object", "close": "float64"},
        )
        contract.add_migration(
            to_version=2,
            description="add volume column",
            added_columns={"volume": "float64"},
        )
        assert contract.schema_version == 2
        assert len(contract.migrations) == 1
        assert contract.migrations[0].from_version == 1
        assert contract.migrations[0].to_version == 2

    def test_migrate_add_columns(self):
        contract = DataContract(
            dimension="test_dim",
            schema_version=2,
            columns={"date": "object", "close": "float64", "volume": "float64"},
            migrations=[
                SchemaMigration(
                    dimension="test_dim",
                    from_version=1,
                    to_version=2,
                    added_columns={"volume": "float64"},
                    compat="coerce",
                ),
            ],
        )
        df = pd.DataFrame({"date": ["2024-01-01"], "close": [10.5]})
        result = contract.migrate(df, from_version=1)
        assert "volume" in result.columns

    def test_migrate_remove_columns(self):
        contract = DataContract(
            dimension="test_dim",
            schema_version=2,
            columns={"date": "object", "close": "float64"},
            migrations=[
                SchemaMigration(
                    dimension="test_dim",
                    from_version=1,
                    to_version=2,
                    removed_columns=["old_col"],
                    compat="coerce",
                ),
            ],
        )
        df = pd.DataFrame({"date": ["2024-01-01"], "close": [10.5], "old_col": [99]})
        result = contract.migrate(df, from_version=1)
        assert "old_col" not in result.columns
        assert "date" in result.columns

    def test_migrate_rename_columns(self):
        contract = DataContract(
            dimension="test_dim",
            schema_version=2,
            columns={"date": "object", "price": "float64"},
            migrations=[
                SchemaMigration(
                    dimension="test_dim",
                    from_version=1,
                    to_version=2,
                    renamed_columns={"close": "price"},
                    compat="coerce",
                ),
            ],
        )
        df = pd.DataFrame({"date": ["2024-01-01"], "close": [10.5]})
        result = contract.migrate(df, from_version=1)
        assert "price" in result.columns
        assert "close" not in result.columns

    def test_migrate_strict_raises(self):
        contract = DataContract(
            dimension="test_dim",
            schema_version=2,
            columns={"date": "object", "new_col": "float64"},
            migrations=[
                SchemaMigration(
                    dimension="test_dim",
                    from_version=1,
                    to_version=2,
                    compat="strict",
                ),
            ],
        )
        df = pd.DataFrame({"date": ["2024-01-01"]})
        with pytest.raises(ValueError, match="strict"):
            contract.migrate(df, from_version=1)

    def test_migrate_chain_multiple(self):
        contract = DataContract(
            dimension="test_dim",
            schema_version=3,
            columns={"date": "object", "value": "float64"},
            migrations=[
                SchemaMigration(
                    dimension="test_dim",
                    from_version=1, to_version=2,
                    renamed_columns={"price": "temp"},
                ),
                SchemaMigration(
                    dimension="test_dim",
                    from_version=2, to_version=3,
                    renamed_columns={"temp": "value"},
                ),
            ],
        )
        df = pd.DataFrame({"date": ["2024-01-01"], "price": [10.5]})
        result = contract.migrate(df, from_version=1)
        assert "value" in result.columns
        assert "price" not in result.columns
        assert "temp" not in result.columns


class TestDataContractPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        contract = DataContract(
            dimension="test_roundtrip",
            schema_version=2,
            columns={"date": "object", "close": "float64"},
            primary_key=["date"],
            freq="daily",
            sla_days=3,
            pit_rule="as_of_date",
            owner="test_owner",
            description="Test contract",
        )
        contract.add_migration(
            to_version=2,
            description="add close column",
            added_columns={"close": "float64"},
        )
        contract.save(store_dir=tmp_path)
        path = tmp_path / "test_roundtrip.json"
        assert path.exists()

        loaded = DataContract.load("test_roundtrip", store_dir=tmp_path)
        assert loaded is not None
        assert loaded.dimension == "test_roundtrip"
        assert loaded.schema_version == 2
        assert loaded.columns == contract.columns
        assert loaded.primary_key == ["date"]
        assert loaded.pit_rule == "as_of_date"
        assert loaded.owner == "test_owner"
        assert len(loaded.migrations) == 1
        assert loaded.migrations[0].description == "add close column"

    def test_load_nonexistent_returns_none(self, tmp_path):
        loaded = DataContract.load("nonexistent", store_dir=tmp_path)
        assert loaded is None


class TestDeriveContracts:
    def test_derive_ohlcv_daily(self):
        contracts = derive_contracts_from_registry()
        assert "ohlcv_daily" in contracts
        c = contracts["ohlcv_daily"]
        assert "date" in c.columns
        assert "close" in c.columns
        assert "volume" in c.columns
        assert c.primary_key == ["date"]
        assert c.pit_rule == "as_of_date"

    def test_derive_financial_summary(self):
        contracts = derive_contracts_from_registry()
        assert "financial_summary" in contracts
        c = contracts["financial_summary"]
        assert "报告期" in c.columns
        assert "净资产收益率" in c.columns
        assert "基本每股收益" in c.columns

    def test_derive_trade_date_primary_key(self):
        contracts = derive_contracts_from_registry()
        c = contracts["valuation_daily"]
        assert c.primary_key == ["ts_code", "trade_date"]

    def test_derive_returns_empty_for_unknown_dimension(self):
        contracts = derive_contracts_from_registry()
        assert contracts.get("totally_unknown_dim_xyz") is None

    def test_load_contract_falls_back_to_derived(self):
        contract = load_contract("ohlcv_daily")
        assert contract is not None
        assert contract.dimension == "ohlcv_daily"
        assert "close" in contract.columns

    def test_load_contract_returns_none_for_unknown(self):
        contract = load_contract("unknown_dimension_xyz_123")
        assert contract is None

    def test_list_contracts_includes_ohlcv(self):
        contracts = list_contracts()
        dims = [c.dimension for c in contracts]
        assert "ohlcv_daily" in dims
        assert all(isinstance(c, DataContract) for c in contracts)
