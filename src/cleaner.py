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

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
        dayfirst=True
    )

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

        df[column] = df[column].replace(
            ["--", "—", ""],
            np.nan
        )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    return df


def clean_google_ads_report(df):

    df = df.copy()

    df = remove_summary_rows(df)

    df = remove_invalid_campaigns(df)

    df = clean_dates(df)

    df = clean_numeric_columns(df)

    return df.reset_index(drop=True)