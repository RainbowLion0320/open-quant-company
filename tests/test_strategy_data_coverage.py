from research.strategy_catalog import StrategyCatalogItem


def _item(
    name: str,
    strategy_type: str,
    data_requirements: list[str],
    *,
    layer: str = "candidate_alpha",
) -> StrategyCatalogItem:
    return StrategyCatalogItem(
        name=name,
        label=name.title(),
        strategy_type=strategy_type,
        layer=layer,
        lifecycle="candidate",
        config_key=f"strategies.{name}",
        data_requirements=data_requirements,
        asset_scope=["stock"],
        required_asset_dimensions=data_requirements,
    )


def test_strategy_data_coverage_matrix_compares_declared_inputs_with_type_expectations():
    from research.strategy_data_coverage import build_strategy_data_coverage

    payload = build_strategy_data_coverage(
        items=[
            _item("trend", "timing", ["stock_daily"]),
            _item("quality", "selection", ["financials", "valuation_daily"]),
        ],
        evidence_loader=lambda name: {"exists": False, "artifact": {}},
    )

    rows = {row["strategy"]: row for row in payload["rows"]}
    assert payload["summary"]["strategy_count"] == 2
    assert payload["summary"]["required_gap_count"] == 1
    assert payload["families"][0]["key"] == "price"
    assert payload["assets"][0]["key"] == "stock"

    trend = rows["trend"]
    assert trend["cells"]["price"]["status"] == "declared"
    assert trend["cells"]["volume"]["status"] == "declared"
    assert trend["cells"]["moneyflow"]["status"] == "optional_missing"
    assert trend["missing_required_families"] == []
    assert trend["observed_status"] == "missing_evidence"

    quality = rows["quality"]
    assert quality["cells"]["financial"]["status"] == "declared"
    assert quality["cells"]["valuation"]["status"] == "declared"
    assert quality["cells"]["price"]["status"] == "required_missing"
    assert quality["missing_required_families"] == ["price"]


def test_strategy_data_coverage_reports_asset_scope_gaps():
    from research.strategy_data_coverage import build_strategy_data_coverage

    payload = build_strategy_data_coverage(
        items=[
            StrategyCatalogItem(
                name="cross_asset_allocator",
                label="Cross Asset",
                strategy_type="portfolio",
                layer="asset_allocation",
                lifecycle="candidate",
                config_key="allocator",
                data_requirements=["stock_daily", "fund_daily", "bond_treasury_yields"],
                asset_scope=["stock", "etf", "bond", "futures", "crypto", "cash"],
                required_asset_dimensions=[
                    "stock_daily",
                    "fund_daily",
                    "bond_treasury_yields",
                    "futures_daily",
                    "crypto_daily",
                ],
                blockers=["crypto_data_stale_until_fresh_source"],
            )
        ],
        evidence_loader=lambda name: {"exists": False, "artifact": {}},
    )

    row = payload["rows"][0]
    assert row["asset_scope"] == ["stock", "etf", "bond", "futures", "crypto", "cash"]
    assert row["missing_required_assets"] == []
    assert row["blockers"] == ["crypto_data_stale_until_fresh_source"]
    assert payload["summary"]["asset_gap_count"] == 0


def test_strategy_data_coverage_reads_observed_dimensions_from_strategy_evidence():
    from research.strategy_data_coverage import build_strategy_data_coverage

    payload = build_strategy_data_coverage(
        items=[_item("sector_alpha", "sector_rotation", ["stock_daily", "sector"])],
        evidence_loader=lambda name: {
            "exists": True,
            "artifact": {
                "data_coverage": {
                    "observed_dimensions": ["stock_daily", "sector", "moneyflow"],
                }
            },
        },
    )

    row = payload["rows"][0]
    assert row["observed_status"] == "measured"
    assert row["observed_dimensions"] == ["moneyflow", "sector", "stock_daily"]
    assert row["observed_families"] == ["price", "volume", "sector", "moneyflow"]
    assert row["cells"]["sector"]["observed"] is True


def test_strategy_data_coverage_cli_outputs_matrix(monkeypatch, tmp_path, capsys):
    from data.storage.datahub import reset_datahub
    from astrolabe_cli.main import run_cli

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    code = run_cli(["strategy", "data-coverage", "--json"])
    captured = capsys.readouterr().out

    assert code == 0
    assert '"command": "strategy data-coverage"' in captured
    assert '"rows"' in captured
    assert (tmp_path / "var" / "artifacts" / "strategy" / "data_coverage_latest.json").exists()
    reset_datahub()
