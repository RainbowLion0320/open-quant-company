import yaml


def test_settings_schema_fields_exist_in_canonical_settings():
    from core.settings import get_dotted
    from web.api.settings_schema import SETTINGS_SECTIONS

    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8")) or {}
    missing: list[str] = []

    for section in SETTINGS_SECTIONS:
        section_data = get_dotted(cfg, section["key"])
        section_exists = section_data is not None
        if not section_exists:
            missing.append(section["key"])
            continue
        for field in section["fields"]:
            if get_dotted(section_data, field["key"]) is None:
                missing.append(f"{section['key']}.{field['key']}")

    assert missing == []


def test_settings_schema_exposes_grouped_strategy_management_model():
    from web.api.settings_schema import get_settings_schema

    schema = get_settings_schema()
    groups = {group["key"]: group for group in schema["groups"]}
    sections = {section["key"]: section for section in schema["sections"]}

    assert "strategy_management" in groups
    assert groups["strategy_management"]["section_count"] > 10
    assert schema["total_groups"] == len(schema["groups"])
    assert all(section.get("group") for section in schema["sections"])

    for key in (
        "strategies.buffett",
        "strategies.trend_following",
        "signal_selection",
        "signal_selection.strategies.multifactor",
        "signals.multifactor",
        "buffett.margin_of_safety",
        "ml",
    ):
        assert sections[key]["group"] == "strategy_management"
        assert sections[key].get("subgroup")
    assert sections["signal_selection"]["subgroup"] == "strategy_global"

    selection_fields = {field["key"] for field in sections["signal_selection.strategies.trend_following"]["fields"]}
    assert {"min_score", "top_pct", "min_buys", "max_buys"} <= selection_fields


def test_settings_schema_exposes_candidate_strategy_core_params():
    from signals.candidates.params import CANDIDATE_PARAM_FIELDS
    from web.api.settings_schema import get_settings_schema

    schema = get_settings_schema()
    sections = {section["key"]: section for section in schema["sections"]}

    expected_required_fields = {
        "trend_following": {
            "min_history_days",
            "short_ma_window",
            "medium_ma_window",
            "long_ma_window",
            "momentum_window",
            "score_weights.trend",
            "score_weights.above_long_ma",
            "score_weights.momentum",
            "trend_score_values.strong",
        },
        "donchian_breakout": {
            "min_history_days",
            "breakout_window",
            "volume_window",
            "volatility_window",
            "score_weights.breakout_proximity",
        },
        "rps_relative_strength": {
            "min_history_days",
            "short_return_window",
            "long_return_window",
            "skip_recent_window",
            "trend_ma_window",
            "score_weights.short_rps",
        },
        "sector_rotation": {
            "min_history_days",
            "short_return_window",
            "long_return_window",
            "score_weights.industry_short",
            "score_weights.stock_inside_industry",
        },
        "quality_value": {
            "recent_period_count",
            "score_weights.roe",
            "score_weights.gross_margin",
            "score_weights.inverse_pe",
            "score_weights.inverse_pb",
        },
        "low_vol_defensive": {
            "min_history_days",
            "volatility_window",
            "drawdown_window",
            "trend_window",
            "liquidity_window",
            "score_weights.inverse_volatility",
        },
        "volume_confirmation": {
            "min_history_days",
            "volume_window",
            "momentum_window",
            "flow_window",
            "score_weights.volume",
        },
        "regime_gated": {
            "min_active_weight",
            "bear_cash_probability_threshold",
            "bear_max_buys",
            "cash_score",
            "regime_weights.bull.trend_following",
            "regime_weights.sideways.quality_value",
            "regime_weights.bear.low_vol_defensive",
        },
    }

    assert set(CANDIDATE_PARAM_FIELDS) == set(expected_required_fields)
    for strategy, required_fields in expected_required_fields.items():
        section = sections[f"strategies.{strategy}.params"]
        assert section["group"] == "strategy_management"
        assert section["strategy_name"] == strategy
        assert section["subgroup"] == "strategy_params"
        field_keys = {field["key"] for field in section["fields"]}
        assert required_fields <= field_keys


def test_settings_schema_validation_covers_bool_and_select_fields():
    from web.api.settings_schema import validate_settings_section

    assert validate_settings_section("strategies.buffett", {"enabled": True, "status": "production"}) == []

    errors = validate_settings_section("strategies.buffett", {"enabled": "yes", "status": "unknown"})
    assert "enabled: expected bool, got str" in errors
    assert any(error.startswith("status: unknown not in options") for error in errors)


def test_settings_yaml_does_not_contain_top_level_dotted_sections():
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8")) or {}

    assert [key for key in cfg if "." in str(key)] == []


def test_settings_schema_validation_is_reusable_outside_routes():
    from web.api.settings_schema import validate_settings_section

    valid = {"min_interval": "4.5", "max_retries": "4"}
    invalid = {"min_interval": 0.1, "max_retries": "many"}

    assert validate_settings_section("data.fetcher", valid) == []

    errors = validate_settings_section("data.fetcher", invalid)
    assert "min_interval: 0.1 < min (0.5)" in errors
    assert "max_retries: expected int, got str" in errors


def test_settings_schema_validation_supports_nested_fields_and_unknown_sections():
    from web.api.settings_schema import validate_settings_section

    assert validate_settings_section("unknown.section", {"x": "bad"}) == []

    errors = validate_settings_section(
        "risk_control",
        {"max_single_position": {"max_pct": 2.0}},
    )
    assert errors == ["max_single_position.max_pct: 2.0 > max (1.0)"]
