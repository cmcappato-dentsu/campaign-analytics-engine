import numpy as np
import pandas as pd


def remove_summary_rows(df):

    df = df.copy()

    if "campaign" in df.columns:

        df = df[
            ~df["campaign"]
            .astype("string")
            .str.startswith(
                "Total:",
                na=False
            )
        ]

    return df


def remove_invalid_campaigns(df):

    df = df.copy()

    df = df[
        df["campaign"].notna() &
        (
            df["campaign"]
            .astype("string")
            .str.strip()
            != "--"
        )
    ]

    return df


def clean_dates(df):

    df = df.copy()

    values = df["date"].astype("string").str.strip()
    iso_mask = values.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)

    parsed_dates = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    parsed_dates.loc[iso_mask] = pd.to_datetime(
        values.loc[iso_mask],
        format="%Y-%m-%d",
        errors="coerce",
    )
    parsed_dates.loc[~iso_mask] = pd.to_datetime(
        values.loc[~iso_mask],
        errors="coerce",
        dayfirst=True,
    )

    df["date"] = parsed_dates

    return df


def clean_numeric_columns(df):

    df = df.copy()

    numeric_columns = [
        "budget",
        "clicks",
        "impressions",
        "conversions",
        "conversion_value",
        "spend",
        "impression_share",
        "lost_is_rank",
        "lost_is_budget",
    ]

    for column in numeric_columns:

        if column not in df.columns:
            continue

        values = df[column].astype("string").str.strip()
        values = values.replace(["--", "—", "", "nan", "None"], np.nan)

        # Los reportes de performance pueden exportar cantidades con
        # separadores de miles (por ejemplo, "2,877" o "181,709.52").
        values = values.str.replace(",", "", regex=False)
        values = values.str.replace("%", "", regex=False)

        df[column] = pd.to_numeric(
            values,
            errors="coerce"
        )

    return df


def clean_report(df):

    df = df.copy()

    df = remove_summary_rows(df)

    df = remove_invalid_campaigns(df)

    df = clean_dates(df)

    df = clean_numeric_columns(df)

    return df.reset_index(drop=True)


def clean_google_ads_report(df):
    """Compatibilidad para el nombre histórico del limpiador."""

    return clean_report(df)
