"""Config center schema assembly and validation."""

from __future__ import annotations

import copy
from typing import Any

from core.settings import get_dotted, get_settings
from web.api.config_schema.groups import GROUP_BY_KEY, SETTINGS_GROUPS
from web.api.config_schema.sections import BASE_SECTIONS
from web.api.config_schema.strategy_sections import build_strategy_sections


def build_settings_sections(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = config if config is not None else get_settings()
    sections = copy.deepcopy(BASE_SECTIONS) + build_strategy_sections(cfg or {})
    sections.sort(key=lambda item: (GROUP_BY_KEY.get(item.get("group", ""), {}).get("order", 999), item.get("order", 9999), item["key"]))
    return sections


SETTINGS_SECTIONS: list[dict[str, Any]] = build_settings_sections()


def _group_summaries(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for group in SETTINGS_GROUPS:
        group_sections = [section for section in sections if section.get("group") == group["key"]]
        if not group_sections:
            continue
        summaries.append(
            {
                **group,
                "sections": [section["key"] for section in group_sections],
                "section_count": len(group_sections),
                "field_count": sum(len(section.get("fields", [])) for section in group_sections),
            }
        )
    return summaries


def get_settings_schema() -> dict[str, Any]:
    """Return the full grouped schema for the config center."""
    sections = build_settings_sections()
    groups = _group_summaries(sections)
    return {
        "groups": groups,
        "sections": sections,
        "total_groups": len(groups),
        "total_sections": len(sections),
        "total_fields": sum(len(s["fields"]) for s in sections),
    }


def _schema_data_for_patch(section: str, schema: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    if schema["key"] == section:
        return data
    if schema["key"].startswith(section + "."):
        suffix = schema["key"][len(section) + 1 :]
        return get_dotted(data, suffix, {}) or {}
    return data


def _validate_type(field: dict[str, Any], value: Any) -> tuple[bool, Any, str]:
    field_type = field.get("type", "float")
    if field_type == "bool":
        return (isinstance(value, bool), value, f"{field['key']}: expected bool, got {type(value).__name__}")
    if field_type == "int":
        if isinstance(value, bool):
            return (False, value, f"{field['key']}: expected int, got bool")
        try:
            return (True, int(value), "")
        except (ValueError, TypeError):
            return (False, value, f"{field['key']}: expected int, got {type(value).__name__}")
    if field_type == "float":
        if isinstance(value, bool):
            return (False, value, f"{field['key']}: expected float, got bool")
        try:
            return (True, float(value), "")
        except (ValueError, TypeError):
            return (False, value, f"{field['key']}: expected float, got {type(value).__name__}")
    if field_type in {"string", "select"}:
        return (isinstance(value, str), value, f"{field['key']}: expected string, got {type(value).__name__}")
    return (True, value, "")


def validate_settings_section(section: str, data: dict[str, Any]) -> list[str]:
    """Validate one config section payload against the editable settings schema."""
    matching_schemas = [
        schema
        for schema in build_settings_sections()
        if schema["key"] == section or schema["key"].startswith(section + ".")
    ]
    if not matching_schemas:
        return []

    errors: list[str] = []
    for schema in matching_schemas:
        schema_data = _schema_data_for_patch(section, schema, data)
        for field in schema["fields"]:
            key = field["key"]
            val = get_dotted(schema_data, key)
            if val is None:
                continue

            valid, typed_val, error = _validate_type(field, val)
            if not valid:
                errors.append(error)
                continue

            options = field.get("options") or []
            if options:
                allowed = {item.get("value") if isinstance(item, dict) else item for item in options}
                if typed_val not in allowed:
                    errors.append(f"{key}: {typed_val} not in options ({sorted(allowed)})")

            fmin = field.get("min")
            fmax = field.get("max")
            if fmin is not None and typed_val < fmin:
                errors.append(f"{key}: {typed_val} < min ({fmin})")
            if fmax is not None and typed_val > fmax:
                errors.append(f"{key}: {typed_val} > max ({fmax})")

    return errors
