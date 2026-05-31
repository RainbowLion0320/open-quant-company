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
