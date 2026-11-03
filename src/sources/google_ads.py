"""Adaptador para reportes exportados desde Google Ads."""

import csv
import io
from pathlib import Path
import re
import unicodedata

import pandas as pd

from config.constants import REQUIRED_COLUMNS


SOURCE_ID = "google_ads"
DISPLAY_NAME = "Google Ads"
SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")
DEFAULT_HEADER_SKIPROWS = None


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
    "network": [
        "Red",
        "Network",
        "Network (with search partners)",
        "Red (con asociados de búsqueda)",
    ],
    "bid_strategy": [
        "Estrategia de puja",
        "Bid strategy",
        "Campaign bid strategy type",
        "Tipo de estrategia de oferta de la campaña",
    ],
    "impression_share": [
        "Cuota de impresiones de búsqueda",
        "Search impression share",
    ],
    "top_impression_share": [
        "Porcentaje de impr. (absoluto parte sup.)",
        "Absolute top impression share",
        "% impr. (absoluto parte sup.)",
    ],
    "lost_is_rank": [
        "Cuota de impresiones perdida por ranking",
        "Search lost IS (rank)",
        "% impr. perdidas de la Búsqueda (ranking)",
        "% impr. perdidas de la busqueda (ranking)",
    ],
    "lost_is_budget": [
        "Cuota de impresiones perdida por presupuesto",
        "Search lost IS (budget)",
        "Search budget lost impression share",
        "% impr. perdidas de la Búsqueda (presupuesto)",
        "% impr. perdidas de la busqueda (presupuesto)",
    ],
}


def normalize_column_name(column_name: str) -> str:
    """Normaliza un nombre de columna para compararlo con sus aliases."""

    text = str(column_name).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore"
    ).decode("ascii")


def _build_alias_lookup() -> dict[str, str]:
    """Construye el lookup de encabezados normalizados a columnas canónicas."""

    return {
        normalize_column_name(alias): canonical
        for canonical, aliases in COLUMN_ALIASES.items()
        for alias in aliases
    }


def rename_columns_to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """Mapea los encabezados de la fuente al schema canónico."""

    alias_lookup = _build_alias_lookup()
    rename_map = {
        column: alias_lookup[normalize_column_name(column)]
        for column in df.columns
        if normalize_column_name(column) in alias_lookup
    }
    return df.copy().rename(columns=rename_map)


def _unwrap_nested_row(row: list[str]) -> list[str]:
    """Desenvuelve filas enteras citadas como si fueran un único campo.

    Algunos exportadores envuelven la fila completa entre comillas y duplican
    las internas. En ese caso ``csv`` devuelve un solo campo que, al volver a
    parsearlo, contiene las columnas reales.
    """

    for _ in range(5):
        if len(row) != 1 or "," not in row[0]:
            break

        parsed = next(csv.reader(io.StringIO(row[0])), None)
        if not parsed or len(parsed) <= 1:
            break

        row = parsed

    return row


def _read_csv_rows(path: Path) -> list[list[str]]:
    """Lee un CSV como filas crudas, tolerando comillas anidadas por fila."""

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    except (csv.Error, UnicodeDecodeError) as error:
        raise ValueError(
            "No se pudo leer el CSV. Verificá que sea un archivo de texto válido."
        ) from error

    return [_unwrap_nested_row(row) for row in rows]


def _find_header_index(rows: list[list[str]]) -> int | None:
    """Ubica la primera fila que contiene los encabezados esperados."""

    alias_lookup = _build_alias_lookup()
    best_index = None
    best_score = 0

    for index, row in enumerate(rows):
        normalized = [normalize_column_name(cell) for cell in row if str(cell).strip()]
        if not normalized:
            continue

        canonical_columns = {
            alias_lookup[cell] for cell in normalized if cell in alias_lookup
        }
        score = len(canonical_columns)

        # El encabezado real debe distinguir fecha y campaña.
        if {"date", "campaign"}.issubset(canonical_columns):
            return index

        if score > best_score:
            best_index = index
            best_score = score

    if best_score >= 2:
        return best_index

    return None


def _rows_to_frame(rows: list[list[str]], header_index: int) -> pd.DataFrame:
    """Convierte filas crudas en un DataFrame usando la fila de encabezados."""

    columns = [str(column).strip() for column in rows[header_index]]
    data = [
        row
        for row in rows[header_index + 1:]
        if any(str(cell).strip() for cell in row)
    ]

    width = len(columns)
    normalized_data = [
        list(row[:width]) + [None] * max(0, width - len(row))
        for row in data
    ]

    return pd.DataFrame(normalized_data, columns=columns)


def load_report(
    file_path: str,
    skiprows: int | None = DEFAULT_HEADER_SKIPROWS,
) -> pd.DataFrame:
    """Carga y normaliza un reporte de esta fuente.

    Si ``skiprows`` es ``None`` (valor por defecto), la fila de encabezados se
    detecta automáticamente. Un valor explícito se respeta por compatibilidad.
    """

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows = _read_csv_rows(path)
    elif suffix in {".xlsx", ".xls"}:
        raw = pd.read_excel(path, header=None, dtype=object)
        rows = raw.where(pd.notna(raw), None).values.tolist()
    else:
        raise ValueError(
            "Formato no soportado para esta fuente. Utilizar CSV o Excel."
        )

    header_index = skiprows if skiprows is not None else _find_header_index(rows)
    if header_index is None or header_index >= len(rows):
        raise ValueError(
            "No se pudo identificar la fila de encabezados del reporte. "
            "Verificá que el archivo incluya las columnas de fecha y campaña."
        )

    df = _rows_to_frame(rows, header_index)
    df = rename_columns_to_canonical(df)

    # Fallback: si la columna de red no mapeó por nombre exacto, buscar por aproximación
    if "network" not in df.columns:
        for column in df.columns:
            normalized = normalize_column_name(column)
            if "network" in normalized or normalized == "red" or normalized.startswith("red "):
                df = df.rename(columns={column: "network"})
                break

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in df.columns
    ]
    if missing_columns:
        raise ValueError(
            "El reporte no contiene las columnas obligatorias: "
            + ", ".join(missing_columns)
        )
    return df
