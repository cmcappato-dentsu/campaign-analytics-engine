from pathlib import Path

import pandas as pd

from config.column_mapping import (
    rename_columns_to_canonical
)

from config.constants import (
    DEFAULT_HEADER_SKIPROWS
)


def load_google_ads_report(
    file_path: str,
    skiprows: int = DEFAULT_HEADER_SKIPROWS
) -> pd.DataFrame:
    """
    Carga un reporte de Google Ads desde CSV o Excel
    y transforma sus columnas al schema canónico.
    """

    file_path = Path(file_path)

    if not file_path.exists():

        raise FileNotFoundError(
            f"No se encontró el archivo: {file_path}"
        )

    suffix = file_path.suffix.lower()

    if suffix == ".csv":

        df = pd.read_csv(
            file_path,
            skiprows=skiprows
        )

    elif suffix in [".xlsx", ".xls"]:

        df = pd.read_excel(
            file_path,
            skiprows=skiprows
        )

    else:

        raise ValueError(
            "Formato no soportado. "
            "Utilizar CSV o Excel."
        )

    df = rename_columns_to_canonical(df)

    return df