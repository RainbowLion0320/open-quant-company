import yaml


def _get_dotted(data: dict, dotted_key: str):
    current = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def test_settings_schema_fields_exist_in_canonical_settings():
    from web.api.settings_schema import SETTINGS_SECTIONS

    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8")) or {}
    missing: list[str] = []

    for section in SETTINGS_SECTIONS:
        section_data, section_exists = _get_dotted(cfg, section["key"])
        if not section_exists:
            missing.append(section["key"])
            continue
        for field in section["fields"]:
            _, field_exists = _get_dotted(section_data, field["key"])
            if not field_exists:
                missing.append(f"{section['key']}.{field['key']}")

    assert missing == []


def test_settings_yaml_does_not_contain_top_level_dotted_sections():
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8")) or {}

    assert [key for key in cfg if "." in str(key)] == []
