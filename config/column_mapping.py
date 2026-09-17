"""Compatibilidad para el antiguo punto de entrada de aliases."""

from src.sources.google_ads import (
    COLUMN_ALIASES,
    normalize_column_name,
    rename_columns_to_canonical,
)


def build_alias_lookup() -> dict:
    """Construye el lookup de aliases de Google Ads por compatibilidad."""

    return {
        normalize_column_name(alias): canonical
        for canonical, aliases in COLUMN_ALIASES.items()
        for alias in aliases
    }
