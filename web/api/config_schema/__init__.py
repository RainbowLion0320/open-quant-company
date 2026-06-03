"""Editable settings schema package."""

from web.api.config_schema.schema import (  # noqa: F401
    SETTINGS_GROUPS,
    SETTINGS_SECTIONS,
    build_settings_sections,
    get_settings_schema,
    validate_settings_section,
)
