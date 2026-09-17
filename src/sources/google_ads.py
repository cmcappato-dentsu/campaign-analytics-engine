"""Adaptador para reportes exportados desde Google Ads."""

from pathlib import Path
import unicodedata

import pandas as pd

from config.constants import REQUIRED_COLUMNS


SOURCE_ID = "google_ads"
DISPLAY_NAME = "Google Ads"
SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")
DEFAULT_HEADER_SKIPROWS = 2


COLUMN_ALIASES = {
    "date": ["Día", "Day", "Date"],
    "campaign": ["Campaña", "Campaign"],
    "campaign_status": ["Estado de la campaña", "Campaign state", "Campaign status"],
    "budget": ["Presupuesto", "Budget"],
    "budget_name": ["Nombre del presupuesto", "Budget name"],
    "budget_type": ["Tipo de presupuesto", "Budget type"],
    "currency": ["Código de moneda", "Currency code"],
    "status": ["Estado", "Status"],
    "status_reasons": ["Motivos del estado", "Status reasons"],
    "clicks": ["Clics", "Clicks"],
    "impressions": ["Impr.", "Impr", "Impressions"],
    "conversions": ["Conversiones", "Conversions"],
    "conversion_value": ["Valor de conv.", "Conv. value", "Conversion value"],
    "spend": ["Costo", "Cost"],
    "network": ["Red", "Network", "Network (with search partners)"],
    "bid_strategy": [
        "Estrategia de puja",
        "Bid strategy",
        "Campaign bid strategy type",
    ],
    "impression_share": [
        "Cuota de impresiones de búsqueda",
        "Search impression share",
    ],
    "lost_is_rank": [
        "Cuota de impresiones perdida por ranking",
        "Search lost IS (rank)",
    ],
    "lost_is_budget": [
        "Cuota de impresiones perdida por presupuesto",
        "Search lost IS (budget)",
    ],
}


def normalize_column_name(column_name: str) -> str:
    """Normaliza un nombre de columna para compararlo con sus aliases."""

    text = str(column_name).strip().lower()
    return unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore"
    ).decode("ascii")


def rename_columns_to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """Mapea los encabezados de la fuente al schema canónico."""

    alias_lookup = {
        normalize_column_name(alias): canonical
        for canonical, aliases in COLUMN_ALIASES.items()
        for alias in aliases
    }
    rename_map = {
        column: alias_lookup[normalize_column_name(column)]
        for column in df.columns
        if normalize_column_name(column) in alias_lookup
    }
    return df.copy().rename(columns=rename_map)


def load_report(
    file_path: str,
    skiprows: int = DEFAULT_HEADER_SKIPROWS,
) -> pd.DataFrame:
    """Carga y normaliza un reporte de esta fuente."""

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path, skiprows=skiprows, encoding="utf-8-sig")
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, skiprows=skiprows)
    else:
        raise ValueError(
            "Formato no soportado para esta fuente. Utilizar CSV o Excel."
        )

    df = rename_columns_to_canonical(df)
    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in df.columns
    ]
    if missing_columns:
        raise ValueError(
            "El reporte no contiene las columnas obligatorias: "
            + ", ".join(missing_columns)
        )
    return df
